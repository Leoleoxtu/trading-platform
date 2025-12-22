#!/usr/bin/env python3
"""
RSS Ingestor Service

Polls RSS feeds, stores raw content in MinIO, and publishes RawEvent v1 messages to Kafka.
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

import feedparser
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
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"rss-ingestor","message":%(message)s}',
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
RSS_FEEDS = os.getenv('RSS_FEEDS', '')
RSS_POLL_SECONDS = int(os.getenv('RSS_POLL_SECONDS', '60'))
HEALTH_PORT = int(os.getenv('HEALTH_PORT', '8000'))
DEDUP_STATE_FILE = os.getenv('DEDUP_STATE_FILE', '/data/seen_items.json')

# Global state
# Note: These globals are safe as polling_loop runs in a single thread
# and health_server only reads them
shutdown_event = Event()
is_healthy = False
seen_items: Set[str] = set()
last_success_timestamp = time.time()  # Initialize to current time to avoid large initial value

# Prometheus metrics
metrics_items_fetched = Counter('rss_ingestor_items_fetched_total', 'Total items fetched from RSS feeds')
metrics_raw_events_published = Counter('rss_ingestor_raw_events_published_total', 'Total raw events published to Kafka')
metrics_raw_events_failed = Counter('rss_ingestor_raw_events_failed_total', 'Total raw events that failed to publish')
metrics_dedup_hits = Counter('rss_ingestor_dedup_hits_total', 'Total deduplicated items')
metrics_poll_duration = Histogram('rss_ingestor_poll_duration_seconds', 'Duration of RSS feed polling')
metrics_minio_put_duration = Histogram('rss_ingestor_minio_put_duration_seconds', 'Duration of MinIO put operations')
metrics_kafka_produce_duration = Histogram('rss_ingestor_kafka_produce_duration_seconds', 'Duration of Kafka produce operations')
metrics_last_success = Gauge('rss_ingestor_last_success_timestamp', 'Timestamp of last successful poll')


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for health checks."""
    
    def do_GET(self):
        if self.path == '/health':
            if is_healthy:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {
                    'status': 'healthy',
                    'service': 'rss-ingestor',
                    'feeds_count': len(RSS_FEEDS.split(',')) if RSS_FEEDS else 0,
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
    try:
        start_time = time.time()
        s3_client.put_object(
            Bucket=MINIO_BUCKET_RAW,
            Key=key,
            Body=content.encode('utf-8'),
            ContentType=content_type
        )
        metrics_minio_put_duration.observe(time.time() - start_time)
        
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


def process_rss_item(
    item: feedparser.FeedParserDict,
    feed_url: str,
    feed_name: str,
    s3_client,
    producer: KafkaProducer,
    schema: dict
) -> bool:
    """Process a single RSS item."""
    global seen_items
    
    metrics_items_fetched.inc()
    
    # Create dedup key from URL and published date
    item_url = item.get('link', '')
    item_published = item.get('published', item.get('updated', ''))
    dedup_key = f"{item_url}|{item_published}"
    
    # Check if already seen
    if dedup_key in seen_items:
        logger.debug(json.dumps({
            'message': 'Item already seen, skipping',
            'url': item_url
        }))
        metrics_dedup_hits.inc()
        return False
    
    try:
        # Generate IDs
        event_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        captured_at = datetime.now(timezone.utc).isoformat()
        
        # Parse event time
        event_time = None
        if item_published:
            try:
                parsed_time = feedparser._parse_date(item_published)
                if parsed_time:
                    event_time = datetime(*parsed_time[:6], tzinfo=timezone.utc).isoformat()
            except:
                pass
        
        # Create raw content
        raw_content = {
            'url': item_url,
            'title': item.get('title', ''),
            'summary': item.get('summary', item.get('description', '')),
            'published': item_published,
            'author': item.get('author', ''),
            'tags': [tag.get('term', '') for tag in item.get('tags', [])],
            'feed_url': feed_url,
            'feed_name': feed_name,
            'raw_entry': {k: str(v) for k, v in item.items() if k not in ['tags', 'links']}
        }
        
        raw_json = json.dumps(raw_content, indent=2)
        raw_hash = calculate_hash(raw_json)
        
        # Create S3 key with partitioning
        date_partition = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        s3_key = f"source=rss/dt={date_partition}/{event_id}.json"
        
        # Upload to MinIO
        s3_uri = upload_to_minio(s3_client, s3_key, raw_json, 'application/json')
        
        # Create RawEvent
        raw_event = {
            'schema_version': 'raw_event.v1',
            'event_id': event_id,
            'source_type': 'rss',
            'source_name': feed_name,
            'captured_at_utc': captured_at,
            'event_time_utc': event_time,
            'raw_uri': s3_uri,
            'raw_hash': raw_hash,
            'content_type': 'application/json',
            'priority': 'MEDIUM',
            'correlation_id': correlation_id,
            'metadata': {
                'feed_url': feed_url,
                'article_url': item_url,
                'title': item.get('title', '')
            }
        }
        
        # Validate against schema
        if not validate_event(raw_event, schema):
            logger.error(json.dumps({
                'message': 'Event validation failed',
                'event_id': event_id
            }))
            metrics_raw_events_failed.inc()
            return False
        
        # Publish to Kafka
        start_time = time.time()
        future = producer.send(KAFKA_TOPIC, value=raw_event)
        future.get(timeout=10)  # Wait for confirmation
        metrics_kafka_produce_duration.observe(time.time() - start_time)
        metrics_raw_events_published.inc()
        
        logger.info(json.dumps({
            'message': 'Published RawEvent',
            'event_id': event_id,
            'correlation_id': correlation_id,
            'url': item_url,
            'topic': KAFKA_TOPIC
        }))
        
        # Mark as seen
        seen_items.add(dedup_key)
        
        return True
        
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Failed to process RSS item',
            'url': item_url,
            'error': str(e)
        }))
        metrics_raw_events_failed.inc()
        return False


def poll_feed(
    feed_url: str,
    feed_name: str,
    s3_client,
    producer: KafkaProducer,
    schema: dict
):
    """Poll a single RSS feed."""
    try:
        logger.info(json.dumps({
            'message': 'Polling RSS feed',
            'feed_url': feed_url,
            'feed_name': feed_name
        }))
        
        start_time = time.time()
        feed = feedparser.parse(feed_url)
        metrics_poll_duration.observe(time.time() - start_time)
        
        if feed.bozo:
            logger.warning(json.dumps({
                'message': 'Feed parsing had issues',
                'feed_url': feed_url,
                'exception': str(feed.bozo_exception)
            }))
        
        processed = 0
        for item in feed.entries:
            if shutdown_event.is_set():
                break
            if process_rss_item(item, feed_url, feed_name, s3_client, producer, schema):
                processed += 1
        
        logger.info(json.dumps({
            'message': 'Feed poll complete',
            'feed_url': feed_url,
            'total_items': len(feed.entries),
            'processed': processed
        }))
        
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Failed to poll feed',
            'feed_url': feed_url,
            'error': str(e)
        }))
        metrics_raw_events_failed.inc()


def polling_loop():
    """Main polling loop."""
    global is_healthy, seen_items, last_success_timestamp
    
    # Load seen items
    seen_items = load_seen_items()
    
    # Parse feed list
    feed_urls = [f.strip() for f in RSS_FEEDS.split(',') if f.strip()]
    if not feed_urls:
        logger.warning(json.dumps({
            'message': 'No RSS feeds configured, using default example feed'
        }))
        feed_urls = ['https://feeds.feedburner.com/TechCrunch/']
    
    logger.info(json.dumps({
        'message': 'Starting RSS ingestor',
        'feeds': feed_urls,
        'poll_interval': RSS_POLL_SECONDS
    }))
    
    # Load schema
    schema = load_schema('/app/schemas/raw_event.v1.json')
    
    # Create clients
    s3_client = create_s3_client()
    producer = create_kafka_producer()
    
    is_healthy = True
    
    try:
        while not shutdown_event.is_set():
            start_time = time.time()
            
            # Poll all feeds
            for feed_url in feed_urls:
                if shutdown_event.is_set():
                    break
                
                feed_name = feed_url.split('//')[1].split('/')[0] if '//' in feed_url else feed_url
                poll_feed(feed_url, feed_name, s3_client, producer, schema)
            
            # Save seen items periodically
            save_seen_items(seen_items)
            
            # Update last success timestamp
            last_success_timestamp = time.time()
            metrics_last_success.set(last_success_timestamp)
            
            # Wait for next poll
            elapsed = time.time() - start_time
            sleep_time = max(0, RSS_POLL_SECONDS - elapsed)
            
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
        logger.info(json.dumps({'message': 'RSS ingestor stopped'}))


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
