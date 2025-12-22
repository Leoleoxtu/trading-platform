#!/usr/bin/env python3
"""
Replayer CLI - Main Entry Point

Replay/Backfill tool to republish raw events from MinIO to Kafka
with replay metadata flags for reproducibility testing.
"""

import argparse
import logging
import sys
import os
import json
import uuid
import hashlib
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from kafka import KafkaProducer
from kafka.errors import KafkaError
import jsonschema
from jsonschema import Draft202012Validator


# Configure logging
def setup_logging(log_level: str):
    """Setup structured logging."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"replayer","message":%(message)s}',
        datefmt='%Y-%m-%dT%H:%M:%SZ'
    )
    return logging.getLogger(__name__)


class ReplayStats:
    """Track replay statistics."""
    def __init__(self):
        self.files_found = 0
        self.files_processed = 0
        self.messages_published = 0
        self.errors = 0
        self.skipped = 0
        self.start_time = time.time()
    
    def duration(self) -> float:
        """Get duration in seconds."""
        return time.time() - self.start_time
    
    def rate(self) -> float:
        """Get messages per second rate."""
        duration = self.duration()
        return self.messages_published / duration if duration > 0 else 0.0
    
    def to_dict(self) -> Dict:
        """Convert stats to dictionary."""
        return {
            'files_found': self.files_found,
            'files_processed': self.files_processed,
            'messages_published': self.messages_published,
            'errors': self.errors,
            'skipped': self.skipped,
            'duration_seconds': round(self.duration(), 2),
            'rate_messages_per_sec': round(self.rate(), 2)
        }


class Replayer:
    """Main replayer class."""
    
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.logger = setup_logging(args.log_level)
        self.stats = ReplayStats()
        self.replay_id = args.replay_id or str(uuid.uuid4())
        
        # Initialize clients
        self.s3_client = self._init_s3_client()
        self.kafka_producer = self._init_kafka_producer() if not args.dry_run else None
        
        # Load schema
        self.raw_event_schema = self._load_schema()
        
        self.logger.info(json.dumps({
            'event': 'replayer_initialized',
            'replay_id': self.replay_id,
            'source': args.source,
            'dry_run': args.dry_run
        }))
    
    def _init_s3_client(self):
        """Initialize MinIO S3 client."""
        endpoint = os.getenv('MINIO_ENDPOINT', 'http://minio:9000')
        access_key = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
        secret_key = os.getenv('MINIO_SECRET_KEY', 'minioadmin123')
        
        return boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
    
    def _init_kafka_producer(self):
        """Initialize Kafka producer."""
        bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'redpanda:9092')
        
        return KafkaProducer(
            bootstrap_servers=bootstrap_servers.split(','),
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            compression_type='snappy',
            acks='all',
            retries=3,
            max_in_flight_requests_per_connection=5
        )
    
    def _load_schema(self) -> dict:
        """Load RawEvent v1 schema."""
        schema_path = '/app/schemas/raw_event.v1.json'
        if os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
                return json.load(f)
        else:
            self.logger.warning(json.dumps({'event': 'schema_not_found', 'path': schema_path}))
            return {}
    
    def _validate_event(self, event: dict) -> bool:
        """Validate event against schema."""
        if not self.raw_event_schema:
            return True
        
        try:
            validator = Draft202012Validator(self.raw_event_schema)
            validator.validate(event)
            return True
        except jsonschema.ValidationError as e:
            self.logger.error(json.dumps({
                'error': 'Schema validation failed',
                'path': list(e.absolute_path),
                'message': e.message
            }))
            return False
    
    def _calculate_hash(self, content: str) -> str:
        """Calculate SHA-256 hash."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _generate_date_list(self) -> List[str]:
        """Generate list of dates in YYYY-MM-DD format."""
        if self.args.date:
            return [self.args.date]
        
        # Generate date range from date_from to date_to
        start = datetime.strptime(self.args.date_from, '%Y-%m-%d')
        end = datetime.strptime(self.args.date_to, '%Y-%m-%d')
        
        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        
        return dates
    
    def _list_objects(self) -> List[str]:
        """List objects in MinIO for the specified source and date range."""
        bucket = os.getenv('MINIO_BUCKET_RAW', 'raw-events')
        dates = self._generate_date_list()
        
        all_objects = []
        
        for date in dates:
            prefix = f"source={self.args.source}/dt={date}/"
            
            try:
                paginator = self.s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
                
                for page in pages:
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            all_objects.append(obj['Key'])
                            
                            if self.args.limit and len(all_objects) >= self.args.limit:
                                return all_objects
                
                self.logger.info(json.dumps({
                    'event': 'objects_listed',
                    'date': date,
                    'prefix': prefix,
                    'count': len([o for o in all_objects if f"dt={date}/" in o])
                }))
            
            except ClientError as e:
                self.logger.error(json.dumps({
                    'error': 'list_objects_failed',
                    'date': date,
                    'prefix': prefix,
                    'message': str(e)
                }))
        
        return all_objects
    
    def _download_object(self, key: str) -> Optional[dict]:
        """Download and parse raw JSON from MinIO."""
        bucket = os.getenv('MINIO_BUCKET_RAW', 'raw-events')
        
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            return json.loads(content)
        except Exception as e:
            self.logger.error(json.dumps({
                'error': 'download_failed',
                'key': key,
                'message': str(e)
            }))
            return None
    
    def _extract_event_id_from_key(self, key: str) -> Optional[str]:
        """Extract event_id (UUID) from S3 key path."""
        # Expected format: source=<source>/dt=<date>/<event_id>.json
        filename = key.split('/')[-1]
        event_id = filename.replace('.json', '')
        
        # Validate it's a UUID
        try:
            uuid.UUID(event_id)
            return event_id
        except ValueError:
            return None
    
    def _reconstruct_raw_event(self, key: str, raw_content: dict) -> dict:
        """Reconstruct a RawEvent v1 message with replay metadata."""
        event_id = self._extract_event_id_from_key(key)
        if not event_id:
            event_id = str(uuid.uuid4())
        
        # Extract source_type from key
        source_type = self.args.source
        
        # Build raw_uri
        bucket = os.getenv('MINIO_BUCKET_RAW', 'raw-events')
        raw_uri = f"s3://{bucket}/{key}"
        
        # Calculate raw_hash
        raw_hash = self._calculate_hash(json.dumps(raw_content, sort_keys=True))
        
        # Extract timestamps if available from raw content
        event_time_utc = None
        if isinstance(raw_content, dict):
            # Try common timestamp fields
            for field in ['published', 'created_utc', 'timestamp', 'pubDate', 'created_at']:
                if field in raw_content and raw_content[field]:
                    try:
                        # Handle various timestamp formats
                        ts = raw_content[field]
                        if isinstance(ts, (int, float)):
                            event_time_utc = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                        elif isinstance(ts, str):
                            event_time_utc = ts
                        break
                    except:
                        pass
        
        # Get source_name from raw content or use source_type
        source_name = raw_content.get('source', source_type) if isinstance(raw_content, dict) else source_type
        
        # Initialize replay metadata
        replay_metadata = {}
        
        # Add original metadata if present
        if isinstance(raw_content, dict) and 'metadata' in raw_content:
            original_metadata = raw_content.get('metadata', {})
            replay_metadata.update(original_metadata)
        
        # Build replay flags (applied last to ensure they are preserved)
        replay_flags = {
            'is_replay': True,
            'replay_id': self.replay_id,
            'replay_reason': self.args.replay_reason,
            'replay_source_prefix': f"raw-events/source={source_type}/",
            'replay_published_at_utc': datetime.now(timezone.utc).isoformat()
        }
        replay_metadata.update(replay_flags)
        
        # Construct RawEvent v1
        raw_event = {
            'schema_version': 'raw_event.v1',
            'event_id': event_id,
            'source_type': source_type,
            'source_name': source_name,
            'captured_at_utc': datetime.now(timezone.utc).isoformat(),
            'event_time_utc': event_time_utc,
            'raw_uri': raw_uri,
            'raw_hash': raw_hash,
            'content_type': 'application/json',
            'priority': 'MEDIUM',
            'correlation_id': str(uuid.uuid4()),
            'metadata': replay_metadata
        }
        
        return raw_event
    
    def _publish_event(self, event: dict) -> bool:
        """Publish event to Kafka."""
        if self.args.dry_run:
            return True
        
        topic = os.getenv('KAFKA_TOPIC_RAW', 'raw.events.v1')
        
        try:
            future = self.kafka_producer.send(topic, value=event)
            future.get(timeout=10)
            return True
        except KafkaError as e:
            self.logger.error(json.dumps({
                'error': 'kafka_publish_failed',
                'event_id': event.get('event_id'),
                'message': str(e)
            }))
            return False
    
    def _apply_rate_limit(self):
        """Apply rate limiting if configured."""
        if self.args.rate and self.args.rate > 0:
            time.sleep(1.0 / self.args.rate)
    
    def run(self) -> int:
        """Execute the replay process."""
        try:
            self.logger.info(json.dumps({
                'event': 'replay_started',
                'replay_id': self.replay_id,
                'source': self.args.source,
                'dry_run': self.args.dry_run
            }))
            
            # List objects
            objects = self._list_objects()
            self.stats.files_found = len(objects)
            
            self.logger.info(json.dumps({
                'event': 'objects_found',
                'count': len(objects)
            }))
            
            if len(objects) == 0:
                self.logger.warning(json.dumps({'event': 'no_objects_found'}))
                return 0
            
            # Process each object
            for key in objects:
                try:
                    # Download raw content
                    raw_content = self._download_object(key)
                    if raw_content is None:
                        self.stats.errors += 1
                        continue
                    
                    # Reconstruct RawEvent v1
                    raw_event = self._reconstruct_raw_event(key, raw_content)
                    
                    # Validate
                    if not self._validate_event(raw_event):
                        self.stats.errors += 1
                        continue
                    
                    # Publish
                    if self._publish_event(raw_event):
                        self.stats.messages_published += 1
                        
                        if self.stats.messages_published % 100 == 0:
                            self.logger.info(json.dumps({
                                'event': 'progress',
                                'messages_published': self.stats.messages_published,
                                'files_found': self.stats.files_found
                            }))
                    else:
                        self.stats.errors += 1
                    
                    self.stats.files_processed += 1
                    
                    # Apply rate limit
                    self._apply_rate_limit()
                
                except Exception as e:
                    self.logger.error(json.dumps({
                        'error': 'processing_failed',
                        'key': key,
                        'message': str(e)
                    }))
                    self.stats.errors += 1
            
            # Close Kafka producer
            if self.kafka_producer:
                self.kafka_producer.flush()
                self.kafka_producer.close()
            
            # Print summary
            self._print_summary()
            
            return 0 if self.stats.errors == 0 else 1
        
        except Exception as e:
            self.logger.error(json.dumps({
                'error': 'replay_failed',
                'message': str(e)
            }))
            return 1
    
    def _print_summary(self):
        """Print replay summary."""
        summary = self.stats.to_dict()
        
        print("\n" + "="*60)
        print("REPLAY SUMMARY")
        print("="*60)
        print(f"Replay ID:            {self.replay_id}")
        print(f"Source:               {self.args.source}")
        print(f"Dry Run:              {self.args.dry_run}")
        print(f"Files Found:          {summary['files_found']}")
        print(f"Files Processed:      {summary['files_processed']}")
        print(f"Messages Published:   {summary['messages_published']}")
        print(f"Errors:               {summary['errors']}")
        print(f"Duration:             {summary['duration_seconds']} seconds")
        print(f"Rate:                 {summary['rate_messages_per_sec']} messages/sec")
        print("="*60)
        
        self.logger.info(json.dumps({
            'event': 'replay_completed',
            'summary': summary
        }))


def str_to_bool(value: str) -> bool:
    """Convert string to boolean."""
    return value.lower() in ['true', '1', 'yes']


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Replay/Backfill tool - Republish raw events from MinIO to Kafka'
    )
    
    # Required arguments
    parser.add_argument(
        '--source',
        required=True,
        help='Source type to replay (e.g., rss, reddit, finnhub, market)'
    )
    
    # Date arguments (mutually exclusive groups)
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument(
        '--date',
        help='Single date to replay (YYYY-MM-DD format)'
    )
    date_group.add_argument(
        '--date-from',
        dest='date_from',
        help='Start date for range replay (YYYY-MM-DD format)'
    )
    
    parser.add_argument(
        '--date-to',
        dest='date_to',
        help='End date for range replay (YYYY-MM-DD format), required with --date-from'
    )
    
    # Optional arguments
    parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of files to process'
    )
    
    parser.add_argument(
        '--rate',
        type=int,
        default=50,
        help='Rate limit in messages per second (default: 50)'
    )
    
    parser.add_argument(
        '--dry-run',
        type=str_to_bool,
        default=True,
        help='Dry run mode - list files without publishing (default: true)'
    )
    
    parser.add_argument(
        '--log-level',
        dest='log_level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Log level (default: INFO)'
    )
    
    parser.add_argument(
        '--replay-reason',
        dest='replay_reason',
        default='backfill',
        help='Reason for replay (default: backfill)'
    )
    
    parser.add_argument(
        '--replay-id',
        dest='replay_id',
        help='Custom replay ID (default: auto-generated UUID)'
    )
    
    parser.add_argument(
        '--compare',
        action='store_true',
        help='Enable comparison mode (compare outputs after replay)'
    )
    
    args = parser.parse_args()
    
    # Validate date range arguments
    if args.date_from and not args.date_to:
        parser.error('--date-to is required when using --date-from')
    if args.date_to and not args.date_from:
        parser.error('--date-from is required when using --date-to')
    
    # Run replayer
    replayer = Replayer(args)
    exit_code = replayer.run()
    
    # Run comparison if requested
    if args.compare and exit_code == 0:
        print("\n⚠️  Comparison mode not yet implemented")
        print("   Comparison reports will be available in future versions")
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
