#!/usr/bin/env python3
"""
Reddit Ingestor Service

Polls Reddit submissions and comments via PRAW, stores raw content in MinIO, 
and publishes RawEvent v1 messages to Kafka.
"""

import os
import sys
import json
import logging
import hashlib
import uuid
import time
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set
from threading import Thread, Event
from http.server import HTTPServer, BaseHTTPRequestHandler

import praw
import boto3
from botocore.exceptions import ClientError
from kafka import KafkaProducer
from kafka.errors import KafkaError
import jsonschema
from jsonschema import Draft202012Validator
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"reddit-ingestor","message":%(message)s}',
    datefmt='%Y-%m-%dT%H:%M:%SZ'
)
logger = logging.getLogger(__name__)

# Configuration from environment
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'redpanda:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC_RAW', 'raw.events.v1')
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'http://minio:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin123')
MINIO_BUCKET_RAW = os.getenv('MINIO_BUCKET_RAW', 'raw-events')
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID', '')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET', '')
REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'trading-platform-ingestor/1.0')
REDDIT_SUBREDDITS = os.getenv('REDDIT_SUBREDDITS', 'wallstreetbets,stocks')
REDDIT_MODE = os.getenv('REDDIT_MODE', 'submissions')  # submissions / comments / both
REDDIT_POLL_SECONDS = int(os.getenv('REDDIT_POLL_SECONDS', '60'))
REDDIT_LIMIT_PER_POLL = int(os.getenv('REDDIT_LIMIT_PER_POLL', '50'))
HEALTH_PORT = int(os.getenv('HEALTH_PORT', '8000'))
DEDUP_STATE_FILE = os.getenv('DEDUP_STATE_FILE', '/data/seen_items.json')
PRIORITY = os.getenv('REDDIT_PRIORITY', 'MEDIUM')

# Global state
shutdown_event = Event()
is_healthy = False
seen_items: Set[str] = set()
last_success_timestamp = time.time()
last_kafka_check = time.time()
last_minio_check = time.time()

# Prometheus metrics
metrics_items_fetched = Counter(
    'reddit_ingestor_items_fetched_total', 
    'Total items fetched from Reddit',
    ['kind']
)
metrics_raw_events_published = Counter(
    'reddit_ingestor_raw_events_published_total', 
    'Total raw events published to Kafka'
)
metrics_raw_events_failed = Counter(
    'reddit_ingestor_raw_events_failed_total', 
    'Total raw events that failed to publish',
    ['reason']
)
metrics_dedup_hits = Counter(
    'reddit_ingestor_dedup_hits_total', 
    'Total deduplicated items'
)
metrics_poll_duration = Histogram(
    'reddit_ingestor_poll_duration_seconds', 
    'Duration of Reddit polling'
)
metrics_minio_put_duration = Histogram(
    'reddit_ingestor_minio_put_duration_seconds', 
    'Duration of MinIO put operations'
)
metrics_kafka_produce_duration = Histogram(
    'reddit_ingestor_kafka_produce_duration_seconds', 
    'Duration of Kafka produce operations'
)
metrics_last_success = Gauge(
    'reddit_ingestor_last_success_timestamp', 
    'Timestamp of last successful poll'
)


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for health checks."""
    
    def do_GET(self):
        if self.path == '/health':
            # Check if service is healthy
            # Consider healthy if loop is running and recent checks succeeded
            kafka_ok = time.time() - last_kafka_check < 300  # 5 min
            minio_ok = time.time() - last_minio_check < 300  # 5 min
            
            if is_healthy and kafka_ok and minio_ok:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {
                    'status': 'healthy',
                    'service': 'reddit-ingestor',
                    'subreddits': REDDIT_SUBREDDITS.split(','),
                    'mode': REDDIT_MODE,
                    'seen_items': len(seen_items)
                }
                self.wfile.write(json.dumps(response).encode())
            else:
                self.send_response(503)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'unhealthy'}).encode())
        elif self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(generate_latest())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def load_schema(schema_path: str) -> dict:
    """Load JSON schema from file."""
    with open(schema_path, 'r') as f:
        return json.load(f)


def validate_event(event: dict, schema: dict) -> bool:
    """Validate event against schema."""
    try:
        validator = Draft202012Validator(schema)
        validator.validate(event)
        return True
    except jsonschema.ValidationError as e:
        logger.error(json.dumps({
            'error': 'Schema validation failed',
            'path': list(e.absolute_path),
            'message': e.message
        }))
        return False


def calculate_hash(content: str) -> str:
    """Calculate SHA-256 hash of content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def load_seen_items() -> Set[str]:
    """Load seen items from persistent storage."""
    state_file = Path(DEDUP_STATE_FILE)
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                data = json.load(f)
                logger.info(json.dumps({
                    'message': f'Loaded {len(data)} seen items from state file'
                }))
                return set(data)
        except Exception as e:
            logger.warning(json.dumps({
                'message': 'Failed to load seen items',
                'error': str(e)
            }))
    return set()


def save_seen_items(items: Set[str]):
    """Save seen items to persistent storage."""
    state_file = Path(DEDUP_STATE_FILE)
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(state_file, 'w') as f:
            json.dump(list(items), f)
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Failed to save seen items',
            'error': str(e)
        }))


def create_s3_client():
    """Create MinIO S3 client."""
    return boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY
    )


def upload_to_minio(s3_client, key: str, content: str, content_type: str) -> str:
    """Upload content to MinIO and return S3 URI."""
    global last_minio_check
    try:
        start_time = time.time()
        s3_client.put_object(
            Bucket=MINIO_BUCKET_RAW,
            Key=key,
            Body=content.encode('utf-8'),
            ContentType=content_type
        )
        metrics_minio_put_duration.observe(time.time() - start_time)
        last_minio_check = time.time()
        
        s3_uri = f"s3://{MINIO_BUCKET_RAW}/{key}"
        logger.info(json.dumps({
            'message': 'Uploaded to MinIO',
            'uri': s3_uri,
            'size': len(content)
        }))
        return s3_uri
    except ClientError as e:
        logger.error(json.dumps({
            'message': 'Failed to upload to MinIO',
            'key': key,
            'error': str(e)
        }))
        raise


def create_kafka_producer() -> KafkaProducer:
    """Create Kafka producer."""
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(','),
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        acks='all',
        retries=3,
        max_in_flight_requests_per_connection=1
    )


def process_reddit_submission(
    submission,
    subreddit_name: str,
    s3_client,
    producer: KafkaProducer,
    schema: dict
) -> bool:
    """Process a single Reddit submission."""
    global seen_items, last_kafka_check
    
    metrics_items_fetched.labels(kind='submission').inc()
    
    # Create dedup key
    reddit_id = submission.id
    dedup_key = f"reddit:submission:{reddit_id}"
    
    # Check if already seen
    if dedup_key in seen_items:
        logger.debug(json.dumps({
            'message': 'Item already seen, skipping',
            'reddit_id': reddit_id,
            'kind': 'submission'
        }))
        metrics_dedup_hits.inc()
        return False
    
    try:
        # Generate IDs
        event_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        captured_at = datetime.now(timezone.utc).isoformat()
        
        # Parse event time from Reddit
        event_time = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).isoformat()
        
        # Create raw content
        raw_content = {
            'kind': 'submission',
            'id': reddit_id,
            'permalink': f"https://reddit.com{submission.permalink}",
            'url': submission.url,
            'title': submission.title,
            'selftext': submission.selftext if hasattr(submission, 'selftext') else '',
            'author': str(submission.author) if submission.author else '[deleted]',
            'created_utc': submission.created_utc,
            'subreddit': subreddit_name,
            'score': submission.score,
            'num_comments': submission.num_comments,
            'retrieved_at_utc': captured_at,
            'source': {
                'source_type': 'reddit',
                'source_name': subreddit_name
            }
        }
        
        raw_json = json.dumps(raw_content, indent=2)
        raw_hash = calculate_hash(raw_json)
        
        # Create S3 key with partitioning
        date_partition = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        s3_key = f"source=reddit/dt={date_partition}/{event_id}.json"
        
        # Upload to MinIO
        s3_uri = upload_to_minio(s3_client, s3_key, raw_json, 'application/json')
        
        # Create RawEvent
        raw_event = {
            'schema_version': 'raw_event.v1',
            'event_id': event_id,
            'source_type': 'reddit',
            'source_name': subreddit_name,
            'captured_at_utc': captured_at,
            'event_time_utc': event_time,
            'raw_uri': s3_uri,
            'raw_hash': raw_hash,
            'content_type': 'application/json',
            'priority': PRIORITY,
            'correlation_id': correlation_id,
            'metadata': {
                'subreddit': subreddit_name,
                'kind': 'submission',
                'reddit_id': reddit_id,
                'permalink': f"https://reddit.com{submission.permalink}",
                'title': submission.title
            }
        }
        
        # Validate against schema
        if not validate_event(raw_event, schema):
            logger.error(json.dumps({
                'message': 'Event validation failed',
                'event_id': event_id
            }))
            metrics_raw_events_failed.labels(reason='schema').inc()
            return False
        
        # Publish to Kafka
        start_time = time.time()
        future = producer.send(KAFKA_TOPIC, value=raw_event)
        future.get(timeout=10)
        metrics_kafka_produce_duration.observe(time.time() - start_time)
        metrics_raw_events_published.inc()
        last_kafka_check = time.time()
        
        logger.info(json.dumps({
            'message': 'Published RawEvent',
            'event_id': event_id,
            'correlation_id': correlation_id,
            'reddit_id': reddit_id,
            'kind': 'submission',
            'topic': KAFKA_TOPIC
        }))
        
        # Mark as seen
        seen_items.add(dedup_key)
        
        return True
        
    except KafkaError as e:
        logger.error(json.dumps({
            'message': 'Failed to publish to Kafka',
            'reddit_id': reddit_id,
            'error': str(e)
        }))
        metrics_raw_events_failed.labels(reason='kafka').inc()
        return False
    except ClientError as e:
        logger.error(json.dumps({
            'message': 'Failed to upload to MinIO',
            'reddit_id': reddit_id,
            'error': str(e)
        }))
        metrics_raw_events_failed.labels(reason='minio').inc()
        return False
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Failed to process Reddit submission',
            'reddit_id': reddit_id,
            'error': str(e)
        }))
        metrics_raw_events_failed.labels(reason='api').inc()
        return False


def process_reddit_comment(
    comment,
    subreddit_name: str,
    s3_client,
    producer: KafkaProducer,
    schema: dict
) -> bool:
    """Process a single Reddit comment."""
    global seen_items, last_kafka_check
    
    metrics_items_fetched.labels(kind='comment').inc()
    
    # Create dedup key
    reddit_id = comment.id
    dedup_key = f"reddit:comment:{reddit_id}"
    
    # Check if already seen
    if dedup_key in seen_items:
        logger.debug(json.dumps({
            'message': 'Item already seen, skipping',
            'reddit_id': reddit_id,
            'kind': 'comment'
        }))
        metrics_dedup_hits.inc()
        return False
    
    try:
        # Generate IDs
        event_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        captured_at = datetime.now(timezone.utc).isoformat()
        
        # Parse event time from Reddit
        event_time = datetime.fromtimestamp(comment.created_utc, tz=timezone.utc).isoformat()
        
        # Create raw content
        raw_content = {
            'kind': 'comment',
            'id': reddit_id,
            'permalink': f"https://reddit.com{comment.permalink}",
            'body': comment.body,
            'author': str(comment.author) if comment.author else '[deleted]',
            'created_utc': comment.created_utc,
            'subreddit': subreddit_name,
            'score': comment.score,
            'retrieved_at_utc': captured_at,
            'source': {
                'source_type': 'reddit',
                'source_name': subreddit_name
            }
        }
        
        raw_json = json.dumps(raw_content, indent=2)
        raw_hash = calculate_hash(raw_json)
        
        # Create S3 key with partitioning
        date_partition = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        s3_key = f"source=reddit/dt={date_partition}/{event_id}.json"
        
        # Upload to MinIO
        s3_uri = upload_to_minio(s3_client, s3_key, raw_json, 'application/json')
        
        # Create RawEvent
        raw_event = {
            'schema_version': 'raw_event.v1',
            'event_id': event_id,
            'source_type': 'reddit',
            'source_name': subreddit_name,
            'captured_at_utc': captured_at,
            'event_time_utc': event_time,
            'raw_uri': s3_uri,
            'raw_hash': raw_hash,
            'content_type': 'application/json',
            'priority': PRIORITY,
            'correlation_id': correlation_id,
            'metadata': {
                'subreddit': subreddit_name,
                'kind': 'comment',
                'reddit_id': reddit_id,
                'permalink': f"https://reddit.com{comment.permalink}"
            }
        }
        
        # Validate against schema
        if not validate_event(raw_event, schema):
            logger.error(json.dumps({
                'message': 'Event validation failed',
                'event_id': event_id
            }))
            metrics_raw_events_failed.labels(reason='schema').inc()
            return False
        
        # Publish to Kafka
        start_time = time.time()
        future = producer.send(KAFKA_TOPIC, value=raw_event)
        future.get(timeout=10)
        metrics_kafka_produce_duration.observe(time.time() - start_time)
        metrics_raw_events_published.inc()
        last_kafka_check = time.time()
        
        logger.info(json.dumps({
            'message': 'Published RawEvent',
            'event_id': event_id,
            'correlation_id': correlation_id,
            'reddit_id': reddit_id,
            'kind': 'comment',
            'topic': KAFKA_TOPIC
        }))
        
        # Mark as seen
        seen_items.add(dedup_key)
        
        return True
        
    except KafkaError as e:
        logger.error(json.dumps({
            'message': 'Failed to publish to Kafka',
            'reddit_id': reddit_id,
            'error': str(e)
        }))
        metrics_raw_events_failed.labels(reason='kafka').inc()
        return False
    except ClientError as e:
        logger.error(json.dumps({
            'message': 'Failed to upload to MinIO',
            'reddit_id': reddit_id,
            'error': str(e)
        }))
        metrics_raw_events_failed.labels(reason='minio').inc()
        return False
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Failed to process Reddit comment',
            'reddit_id': reddit_id,
            'error': str(e)
        }))
        metrics_raw_events_failed.labels(reason='api').inc()
        return False


def poll_subreddit(
    reddit: praw.Reddit,
    subreddit_name: str,
    s3_client,
    producer: KafkaProducer,
    schema: dict
):
    """Poll a single subreddit."""
    try:
        logger.info(json.dumps({
            'message': 'Polling subreddit',
            'subreddit': subreddit_name,
            'mode': REDDIT_MODE,
            'limit': REDDIT_LIMIT_PER_POLL
        }))
        
        start_time = time.time()
        subreddit = reddit.subreddit(subreddit_name)
        
        processed_submissions = 0
        processed_comments = 0
        
        # Process submissions
        if REDDIT_MODE in ['submissions', 'both']:
            try:
                for submission in subreddit.new(limit=REDDIT_LIMIT_PER_POLL):
                    if shutdown_event.is_set():
                        break
                    if process_reddit_submission(submission, subreddit_name, s3_client, producer, schema):
                        processed_submissions += 1
            except Exception as e:
                logger.error(json.dumps({
                    'message': 'Failed to fetch submissions',
                    'subreddit': subreddit_name,
                    'error': str(e)
                }))
                metrics_raw_events_failed.labels(reason='api').inc()
        
        # Process comments
        if REDDIT_MODE in ['comments', 'both']:
            try:
                for comment in subreddit.comments(limit=REDDIT_LIMIT_PER_POLL):
                    if shutdown_event.is_set():
                        break
                    if process_reddit_comment(comment, subreddit_name, s3_client, producer, schema):
                        processed_comments += 1
            except Exception as e:
                logger.error(json.dumps({
                    'message': 'Failed to fetch comments',
                    'subreddit': subreddit_name,
                    'error': str(e)
                }))
                metrics_raw_events_failed.labels(reason='api').inc()
        
        metrics_poll_duration.observe(time.time() - start_time)
        
        logger.info(json.dumps({
            'message': 'Subreddit poll complete',
            'subreddit': subreddit_name,
            'processed_submissions': processed_submissions,
            'processed_comments': processed_comments
        }))
        
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Failed to poll subreddit',
            'subreddit': subreddit_name,
            'error': str(e)
        }))
        metrics_raw_events_failed.labels(reason='api').inc()


def polling_loop():
    """Main polling loop."""
    global is_healthy, seen_items, last_success_timestamp
    
    # Validate configuration
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        logger.error(json.dumps({
            'message': 'Reddit credentials not configured. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables.'
        }))
        sys.exit(1)
    
    if not REDDIT_USER_AGENT:
        logger.error(json.dumps({
            'message': 'REDDIT_USER_AGENT not configured. This is required by Reddit API.'
        }))
        sys.exit(1)
    
    # Load seen items
    seen_items = load_seen_items()
    
    # Parse subreddit list
    subreddits = [s.strip() for s in REDDIT_SUBREDDITS.split(',') if s.strip()]
    if not subreddits:
        logger.warning(json.dumps({
            'message': 'No subreddits configured, using default'
        }))
        subreddits = ['wallstreetbets']
    
    logger.info(json.dumps({
        'message': 'Starting Reddit ingestor',
        'subreddits': subreddits,
        'mode': REDDIT_MODE,
        'poll_interval': REDDIT_POLL_SECONDS,
        'limit_per_poll': REDDIT_LIMIT_PER_POLL
    }))
    
    # Load schema
    schema = load_schema('/app/schemas/raw_event.v1.json')
    
    # Create Reddit client
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT
    )
    
    # Create MinIO and Kafka clients
    s3_client = create_s3_client()
    producer = create_kafka_producer()
    
    is_healthy = True
    
    try:
        while not shutdown_event.is_set():
            start_time = time.time()
            
            # Poll all subreddits
            for subreddit_name in subreddits:
                if shutdown_event.is_set():
                    break
                
                poll_subreddit(reddit, subreddit_name, s3_client, producer, schema)
            
            # Save seen items periodically
            save_seen_items(seen_items)
            
            # Update last success timestamp
            last_success_timestamp = time.time()
            metrics_last_success.set(last_success_timestamp)
            
            # Wait for next poll
            elapsed = time.time() - start_time
            sleep_time = max(0, REDDIT_POLL_SECONDS - elapsed)
            
            logger.info(json.dumps({
                'message': 'Poll cycle complete',
                'elapsed_seconds': round(elapsed, 2),
                'next_poll_in': round(sleep_time, 2)
            }))
            
            shutdown_event.wait(timeout=sleep_time)
            
    except KeyboardInterrupt:
        logger.info(json.dumps({'message': 'Received interrupt signal'}))
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Polling loop error',
            'error': str(e)
        }))
        is_healthy = False
        raise
    finally:
        producer.close()
        save_seen_items(seen_items)
        logger.info(json.dumps({'message': 'Reddit ingestor stopped'}))


def run_health_server():
    """Run health check HTTP server."""
    server = HTTPServer(('0.0.0.0', HEALTH_PORT), HealthHandler)
    logger.info(json.dumps({
        'message': 'Health server started',
        'port': HEALTH_PORT
    }))
    
    while not shutdown_event.is_set():
        server.handle_request()


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(json.dumps({
        'message': 'Received shutdown signal',
        'signal': signum
    }))
    shutdown_event.set()


def main():
    """Main entry point."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start health server in background
    health_thread = Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    # Run polling loop
    try:
        polling_loop()
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Fatal error',
            'error': str(e)
        }))
        sys.exit(1)


if __name__ == '__main__':
    main()
