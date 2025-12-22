#!/usr/bin/env python3
"""
Normalizer Service

Consumes raw events from Kafka, downloads raw content from MinIO,
normalizes the data, and publishes normalized events.
Includes deduplication and DLQ error handling.
"""

import os
import sys
import json
import logging
import hashlib
import sqlite3
import signal
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread, Event
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Dict

import boto3
from botocore.exceptions import ClientError
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
import jsonschema
from jsonschema import Draft202012Validator
from langdetect import detect, LangDetectException
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"normalizer","message":%(message)s}',
    datefmt='%Y-%m-%dT%H:%M:%SZ'
)
logger = logging.getLogger(__name__)

# Configuration from environment
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'redpanda:9092')
KAFKA_TOPIC_RAW = os.getenv('KAFKA_TOPIC_RAW', 'raw.events.v1')
KAFKA_TOPIC_NORMALIZED = os.getenv('KAFKA_TOPIC_NORMALIZED', 'events.normalized.v1')
KAFKA_TOPIC_DLQ = os.getenv('KAFKA_TOPIC_DLQ', 'events.normalized.dlq.v1')
KAFKA_CONSUMER_GROUP = os.getenv('KAFKA_CONSUMER_GROUP', 'normalizer-v1')
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'http://minio:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin123')
HEALTH_PORT = int(os.getenv('HEALTH_PORT', '8000'))
DEDUP_DB_PATH = os.getenv('DEDUP_DB_PATH', '/data/dedup.db')
PIPELINE_VERSION = os.getenv('PIPELINE_VERSION', 'normalizer.v1.0')

# Global state
# Note: These globals are safe as consume_loop processes events sequentially
# and health_server only reads them
shutdown_event = Event()
is_healthy = False
stats = {
    'processed': 0,
    'dedup_hits': 0,
    'dlq_count': 0,
    'errors': 0
}
last_success_timestamp = time.time()  # Initialize to current time to avoid large initial value

# Prometheus metrics
metrics_raw_events_consumed = Counter('normalizer_raw_events_consumed_total', 'Total raw events consumed from Kafka')
metrics_normalized_events_published = Counter('normalizer_normalized_events_published_total', 'Total normalized events published')
metrics_events_failed = Counter('normalizer_events_failed_total', 'Total events that failed processing', ['stage'])
metrics_dlq_published = Counter('normalizer_dlq_published_total', 'Total events sent to DLQ')
metrics_dedup_hits = Counter('normalizer_dedup_hits_total', 'Total duplicate events detected')
metrics_processing_duration = Histogram('normalizer_processing_duration_seconds', 'Duration of event processing end-to-end')
metrics_minio_get_duration = Histogram('normalizer_minio_get_duration_seconds', 'Duration of MinIO get operations')
metrics_kafka_produce_duration = Histogram('normalizer_kafka_produce_duration_seconds', 'Duration of Kafka produce operations')
metrics_last_success = Gauge('normalizer_last_success_timestamp', 'Timestamp of last successful event processing')


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
                    'service': 'normalizer',
                    'stats': stats
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


def init_dedup_db(db_path: str):
    """Initialize SQLite database for deduplication."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dedup_keys (
            dedup_key TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            processed_at TEXT NOT NULL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_processed_at ON dedup_keys(processed_at)')
    conn.commit()
    conn.close()
    logger.info(json.dumps({'message': 'Dedup database initialized', 'path': db_path}))


def is_duplicate(db_path: str, dedup_key: str) -> bool:
    """Check if dedup_key already exists."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM dedup_keys WHERE dedup_key = ?', (dedup_key,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def store_dedup_key(db_path: str, dedup_key: str, event_id: str):
    """Store dedup_key in database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    processed_at = datetime.now(timezone.utc).isoformat()
    try:
        cursor.execute(
            'INSERT INTO dedup_keys (dedup_key, event_id, processed_at) VALUES (?, ?, ?)',
            (dedup_key, event_id, processed_at)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # Already exists (race condition)
        pass
    finally:
        conn.close()


def create_s3_client():
    """Create MinIO S3 client."""
    return boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY
    )


def download_from_minio(s3_client, s3_uri: str) -> Optional[dict]:
    """Download and parse JSON content from MinIO."""
    try:
        start_time = time.time()
        # Parse S3 URI: s3://bucket/key
        parts = s3_uri.replace('s3://', '').split('/', 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid S3 URI format: {s3_uri}")
        
        bucket, key = parts
        
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8')
        metrics_minio_get_duration.observe(time.time() - start_time)
        
        logger.debug(json.dumps({
            'message': 'Downloaded from MinIO',
            'uri': s3_uri,
            'size': len(content)
        }))
        
        return json.loads(content)
        
    except ClientError as e:
        metrics_events_failed.labels(stage='download').inc()
        logger.error(json.dumps({
            'message': 'Failed to download from MinIO',
            'uri': s3_uri,
            'error': str(e)
        }))
        return None
    except json.JSONDecodeError as e:
        metrics_events_failed.labels(stage='parse').inc()
        logger.error(json.dumps({
            'message': 'Invalid JSON in raw content',
            'uri': s3_uri,
            'error': str(e)
        }))
        return None
    except Exception as e:
        metrics_events_failed.labels(stage='download').inc()
        logger.error(json.dumps({
            'message': 'Unexpected error downloading from MinIO',
            'uri': s3_uri,
            'error': str(e)
        }))
        return None


def detect_language(text: str) -> str:
    """Detect language of text."""
    try:
        lang = detect(text)
        return lang
    except LangDetectException:
        return 'unknown'
    except Exception:
        return 'unknown'


def extract_symbols(text: str) -> list:
    """Extract potential ticker symbols from text."""
    # Simple regex to find uppercase sequences that look like ticker symbols
    # This is a basic implementation and can be improved
    pattern = r'\b[A-Z]{2,5}\b'
    matches = re.findall(pattern, text)
    
    # Filter out common words that aren't likely tickers
    common_words = {'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'DAY', 'GET', 'HAS', 'HIM', 'HIS', 'HOW', 'ITS', 'MAY', 'NEW', 'NOW', 'OLD', 'SEE', 'TWO', 'WHO', 'BOY', 'DID', 'ITS', 'LET', 'PUT', 'SAY', 'SHE', 'TOO', 'USE'}
    
    symbols = [s for s in matches if s not in common_words]
    
    # Remove duplicates while preserving order
    seen = set()
    unique_symbols = []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            unique_symbols.append(s)
    
    return unique_symbols[:10]  # Limit to 10 candidates


def normalize_text(raw_content: dict) -> str:
    """Normalize text from raw content."""
    parts = []
    
    if raw_content.get('title'):
        parts.append(raw_content['title'])
    
    if raw_content.get('summary'):
        parts.append(raw_content['summary'])
    
    # Join and clean
    text = ' '.join(parts)
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def calculate_source_score(raw_content: dict, source_type: str, source_name: str) -> float:
    """Calculate source quality score."""
    # Simple scoring logic (can be improved)
    score = 0.5  # Base score
    
    # Adjust based on source type
    if source_type == 'rss':
        score += 0.1
    
    # Adjust based on content quality
    if raw_content.get('title') and len(raw_content['title']) > 10:
        score += 0.1
    
    if raw_content.get('summary') and len(raw_content['summary']) > 50:
        score += 0.1
    
    if raw_content.get('author'):
        score += 0.05
    
    if raw_content.get('published'):
        score += 0.05
    
    # Clamp to [0, 1]
    return min(1.0, max(0.0, score))


def send_to_dlq(
    producer: KafkaProducer,
    raw_event: dict,
    error_type: str,
    error_message: str,
    failed_stage: str
):
    """Send failed event to Dead Letter Queue."""
    try:
        dlq_event = {
            'event_id': raw_event.get('event_id', 'unknown'),
            'correlation_id': raw_event.get('correlation_id', 'unknown'),
            'error_type': error_type,
            'error_message': error_message,
            'failed_stage': failed_stage,
            'failed_at_utc': datetime.now(timezone.utc).isoformat(),
            'original_event': raw_event
        }
        
        producer.send(KAFKA_TOPIC_DLQ, value=dlq_event)
        metrics_dlq_published.inc()
        
        logger.warning(json.dumps({
            'message': 'Sent to DLQ',
            'event_id': raw_event.get('event_id'),
            'error_type': error_type,
            'topic': KAFKA_TOPIC_DLQ
        }))
        
        stats['dlq_count'] += 1
        
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Failed to send to DLQ',
            'error': str(e)
        }))


def process_raw_event(
    raw_event: dict,
    s3_client,
    producer: KafkaProducer,
    raw_schema: dict,
    normalized_schema: dict,
    db_path: str
) -> bool:
    """Process a single raw event."""
    global last_success_timestamp
    event_id = raw_event.get('event_id', 'unknown')
    start_time = time.time()
    
    try:
        metrics_raw_events_consumed.inc()
        
        # Validate raw event schema
        if not validate_event(raw_event, raw_schema):
            metrics_events_failed.labels(stage='schema').inc()
            send_to_dlq(producer, raw_event, 'schema_validation_error', 'Invalid raw event schema', 'validation')
            return False
        
        # Download raw content from MinIO
        raw_uri = raw_event.get('raw_uri')
        if not raw_uri:
            metrics_events_failed.labels(stage='download').inc()
            send_to_dlq(producer, raw_event, 'missing_field', 'Missing raw_uri field', 'download')
            return False
        
        raw_content = download_from_minio(s3_client, raw_uri)
        if raw_content is None:
            send_to_dlq(producer, raw_event, 'download_error', 'Failed to download raw content', 'download')
            return False
        
        # Normalize text
        normalized_text = normalize_text(raw_content)
        if not normalized_text:
            metrics_events_failed.labels(stage='normalize').inc()
            send_to_dlq(producer, raw_event, 'normalization_error', 'Empty normalized text', 'normalization')
            return False
        
        # Extract canonical URL
        canonical_url = raw_content.get('url') or None
        
        # Calculate dedup_key
        dedup_components = f"{normalized_text}|{canonical_url}|{raw_event.get('source_name', '')}"
        dedup_key = calculate_hash(dedup_components)
        
        # Check for duplicates
        if is_duplicate(db_path, dedup_key):
            logger.info(json.dumps({
                'message': 'Duplicate event detected',
                'event_id': event_id,
                'dedup_key': dedup_key
            }))
            stats['dedup_hits'] += 1
            metrics_dedup_hits.inc()
            metrics_processing_duration.observe(time.time() - start_time)
            return True  # Not an error, just a duplicate
        
        # Detect language
        lang = detect_language(normalized_text)
        
        # Calculate source score
        source_score = calculate_source_score(
            raw_content,
            raw_event.get('source_type', ''),
            raw_event.get('source_name', '')
        )
        
        # Extract symbols
        symbols_candidates = extract_symbols(normalized_text)
        
        # Build quality flags
        quality_flags = []
        if symbols_candidates:
            quality_flags.append('has_symbols')
        if source_score >= 0.7:
            quality_flags.append('high_confidence')
        if lang != 'unknown':
            quality_flags.append('language_detected')
        
        # Create normalized event
        normalized_event = {
            'schema_version': 'normalized_event.v1',
            'event_id': event_id,
            'normalized_at_utc': datetime.now(timezone.utc).isoformat(),
            'normalized_text': normalized_text,
            'lang': lang if lang != 'unknown' else 'en',  # Default to 'en' if unknown
            'canonical_url': canonical_url,
            'dedup_key': dedup_key,
            'source_score': source_score,
            'symbols_candidates': symbols_candidates,
            'metadata': {
                'source_type': raw_event.get('source_type'),
                'source_name': raw_event.get('source_name'),
                'raw_event_id': event_id,
                'correlation_id': raw_event.get('correlation_id'),
                'captured_at': raw_event.get('captured_at_utc'),
                'event_time': raw_event.get('event_time_utc')
            },
            'pipeline_version': PIPELINE_VERSION,
            'quality_flags': quality_flags
        }
        
        # Validate normalized event
        if not validate_event(normalized_event, normalized_schema):
            metrics_events_failed.labels(stage='schema').inc()
            send_to_dlq(producer, raw_event, 'schema_validation_error', 'Invalid normalized event schema', 'validation')
            return False
        
        # Publish to Kafka
        produce_start = time.time()
        future = producer.send(KAFKA_TOPIC_NORMALIZED, value=normalized_event)
        future.get(timeout=10)
        metrics_kafka_produce_duration.observe(time.time() - produce_start)
        metrics_normalized_events_published.inc()
        
        # Store dedup key
        store_dedup_key(db_path, dedup_key, event_id)
        
        logger.info(json.dumps({
            'message': 'Published normalized event',
            'event_id': event_id,
            'dedup_key': dedup_key,
            'lang': lang,
            'symbols_count': len(symbols_candidates),
            'topic': KAFKA_TOPIC_NORMALIZED
        }))
        
        stats['processed'] += 1
        last_success_timestamp = time.time()
        metrics_last_success.set(last_success_timestamp)
        metrics_processing_duration.observe(time.time() - start_time)
        return True
        
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Failed to process event',
            'event_id': event_id,
            'error': str(e)
        }))
        stats['errors'] += 1
        metrics_events_failed.labels(stage='processing').inc()
        metrics_processing_duration.observe(time.time() - start_time)
        send_to_dlq(producer, raw_event, 'processing_error', str(e), 'processing')
        return False


def consume_loop():
    """Main consumer loop."""
    global is_healthy
    
    logger.info(json.dumps({
        'message': 'Starting normalizer',
        'consumer_group': KAFKA_CONSUMER_GROUP,
        'input_topic': KAFKA_TOPIC_RAW,
        'output_topic': KAFKA_TOPIC_NORMALIZED,
        'dlq_topic': KAFKA_TOPIC_DLQ
    }))
    
    # Initialize dedup database
    init_dedup_db(DEDUP_DB_PATH)
    
    # Load schemas
    raw_schema = load_schema('/app/schemas/raw_event.v1.json')
    normalized_schema = load_schema('/app/schemas/normalized_event.v1.json')
    
    # Create S3 client
    s3_client = create_s3_client()
    
    # Create Kafka consumer and producer
    consumer = KafkaConsumer(
        KAFKA_TOPIC_RAW,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(','),
        group_id=KAFKA_CONSUMER_GROUP,
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest',
        enable_auto_commit=False,
        max_poll_records=10
    )
    
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(','),
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        acks='all',
        retries=3
    )
    
    is_healthy = True
    
    try:
        logger.info(json.dumps({'message': 'Consumer loop started'}))
        
        while not shutdown_event.is_set():
            # Poll for messages
            records = consumer.poll(timeout_ms=1000)
            
            if not records:
                continue
            
            for topic_partition, messages in records.items():
                for message in messages:
                    if shutdown_event.is_set():
                        break
                    
                    raw_event = message.value
                    
                    process_raw_event(
                        raw_event,
                        s3_client,
                        producer,
                        raw_schema,
                        normalized_schema,
                        DEDUP_DB_PATH
                    )
            
            # Commit offsets after processing batch
            consumer.commit()
            
    except KeyboardInterrupt:
        logger.info(json.dumps({'message': 'Received interrupt signal'}))
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Consumer loop error',
            'error': str(e)
        }))
        is_healthy = False
        raise
    finally:
        consumer.close()
        producer.close()
        logger.info(json.dumps({'message': 'Normalizer stopped', 'stats': stats}))


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
    
    # Run consumer loop
    try:
        consume_loop()
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Fatal error',
            'error': str(e)
        }))
        sys.exit(1)


if __name__ == '__main__':
    main()
