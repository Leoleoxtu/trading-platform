#!/usr/bin/env python3
"""
NLP Enrichment Service

Consumes normalized events from Kafka, applies NLP enrichment (entities, tickers,
sentiment, categorization), validates output schema, and publishes enriched events.
Includes MinIO audit trail, DLQ error handling, and comprehensive observability.
"""

import os
import sys
import json
import logging
import hashlib
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread, Event
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Dict, List, Tuple
import re

import boto3
from botocore.exceptions import ClientError
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
import jsonschema
from jsonschema import Draft202012Validator
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"nlp-enricher","message":%(message)s}',
    datefmt='%Y-%m-%dT%H:%M:%SZ'
)
logger = logging.getLogger(__name__)

# Configuration from environment
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'redpanda:29092')
KAFKA_TOPIC_NORMALIZED = os.getenv('KAFKA_TOPIC_NORMALIZED', 'events.normalized.v1')
KAFKA_TOPIC_ENRICHED = os.getenv('KAFKA_TOPIC_ENRICHED', 'events.enriched.v1')
KAFKA_TOPIC_DLQ = os.getenv('KAFKA_TOPIC_DLQ', 'events.enriched.dlq.v1')
KAFKA_CONSUMER_GROUP = os.getenv('KAFKA_CONSUMER_GROUP', 'nlp-enricher-v1')
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'http://minio:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin123')
MINIO_BUCKET_ARTIFACTS = os.getenv('MINIO_BUCKET_ARTIFACTS', 'pipeline-artifacts')
WRITE_ENRICHED_TO_MINIO = os.getenv('WRITE_ENRICHED_TO_MINIO', 'true').lower() == 'true'
ENABLE_EMBEDDINGS = os.getenv('ENABLE_EMBEDDINGS', 'false').lower() == 'true'
TICKER_WHITELIST = os.getenv('TICKER_WHITELIST', 
    'AAPL,MSFT,GOOGL,GOOG,AMZN,TSLA,META,NVDA,BRK.A,BRK.B,JPM,JNJ,V,PG,UNH,'
    'BTC,ETH,BNB,XRP,ADA,DOGE,SOL,DOT,MATIC'
)
PIPELINE_VERSION = os.getenv('PIPELINE_VERSION', 'nlp-enricher.v1.0')
HEALTH_PORT = int(os.getenv('HEALTH_PORT', '8000'))
USE_SPACY = os.getenv('USE_SPACY', 'false').lower() == 'true'

# Parse ticker whitelist
TICKER_WHITELIST_SET = set(ticker.strip() for ticker in TICKER_WHITELIST.split(',') if ticker.strip())

# Global state
shutdown_event = Event()
is_healthy = False
stats = {
    'consumed': 0,
    'enriched': 0,
    'failed': 0,
    'dlq_count': 0
}
last_success_timestamp = time.time()
sentiment_sum = 0.0
sentiment_count = 0

# Prometheus metrics
metrics_consumed = Counter('nlp_enricher_events_consumed_total', 'Total events consumed')
metrics_enriched = Counter('nlp_enricher_events_enriched_total', 'Total events enriched successfully')
metrics_failed = Counter('nlp_enricher_events_failed_total', 'Total events failed', ['stage'])
metrics_dlq = Counter('nlp_enricher_dlq_published_total', 'Total events sent to DLQ')
metrics_low_confidence = Counter('nlp_enricher_low_confidence_total', 'Low confidence detections', ['kind'])
metrics_category = Counter('nlp_enricher_category_total', 'Events by category', ['category'])
metrics_processing_duration = Histogram('nlp_enricher_processing_duration_seconds', 'End-to-end processing time')
metrics_sentiment_duration = Histogram('nlp_enricher_sentiment_duration_seconds', 'Sentiment analysis time')
metrics_entities_duration = Histogram('nlp_enricher_entities_duration_seconds', 'Entity extraction time')
metrics_embedding_duration = Histogram('nlp_enricher_embedding_duration_seconds', 'Embedding generation time')
metrics_last_success = Gauge('nlp_enricher_last_success_timestamp', 'Timestamp of last success')
metrics_sentiment_mean = Gauge('nlp_enricher_sentiment_mean', 'Moving average of sentiment scores')

# Load schemas
def load_schema(schema_path: str) -> dict:
    """Load JSON schema from file."""
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(json.dumps({'error': 'Failed to load schema', 'path': schema_path, 'details': str(e)}))
        raise

# Load schemas at startup
NORMALIZED_SCHEMA = load_schema('/app/schemas/normalized_event.v1.json')
ENRICHED_SCHEMA = load_schema('/app/schemas/enriched_event.v1.json')

# Initialize validators at module level for better performance
normalized_validator = Draft202012Validator(NORMALIZED_SCHEMA)
enriched_validator = Draft202012Validator(ENRICHED_SCHEMA)

# Initialize sentiment analyzer
sentiment_analyzer = SentimentIntensityAnalyzer()

# Compile regex patterns at module level for better performance
CAPITALIZED_PATTERN = re.compile(r'(?<=[.!?]\s)([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)|(?<=\s)([A-Z][A-Z]+(?:\s[A-Z]+)*)')

# Initialize spaCy if enabled
spacy_nlp = None
if USE_SPACY:
    try:
        import spacy
        spacy_nlp = spacy.load("en_core_web_sm")
        logger.info(json.dumps({'message': 'spaCy model loaded successfully'}))
    except Exception as e:
        logger.warning(json.dumps({'warning': 'Failed to load spaCy model, using fallback', 'error': str(e)}))
        USE_SPACY = False


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for health checks and metrics."""
    
    def do_GET(self):
        if self.path == '/health':
            if is_healthy:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {
                    'status': 'healthy',
                    'service': 'nlp-enricher',
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
        # Suppress default HTTP logging
        pass


def start_health_server():
    """Start HTTP server for health checks and metrics."""
    server = HTTPServer(('0.0.0.0', HEALTH_PORT), HealthHandler)
    logger.info(json.dumps({'message': f'Health server listening on port {HEALTH_PORT}'}))
    while not shutdown_event.is_set():
        server.handle_request()


def extract_entities_spacy(text: str) -> List[Dict]:
    """Extract entities using spaCy."""
    entities = []
    try:
        doc = spacy_nlp(text)
        for ent in doc.ents:
            entity_type = ent.label_
            # Map spaCy labels to our schema
            if entity_type in ('ORG', 'PERSON', 'GPE', 'PRODUCT', 'EVENT'):
                mapped_type = entity_type
                if entity_type == 'GPE':
                    mapped_type = 'COUNTRY'
                
                entities.append({
                    'type': mapped_type,
                    'text': ent.text,
                    'confidence': 0.85  # spaCy doesn't provide confidence, use fixed value
                })
    except Exception as e:
        logger.warning(json.dumps({'warning': 'spaCy entity extraction failed', 'error': str(e)}))
    
    return entities


def extract_entities_heuristic(text: str) -> List[Dict]:
    """Extract entities using simple heuristics."""
    entities = []
    
    # Use pre-compiled regex pattern for performance
    matches = CAPITALIZED_PATTERN.finditer(text)
    
    for match in matches:
        text_match = match.group()
        if len(text_match) > 2:  # Skip single letters
            # Simple heuristic: if all caps, likely ORG, otherwise could be PERSON
            entity_type = 'ORG' if text_match.isupper() else 'OTHER'
            entities.append({
                'type': entity_type,
                'text': text_match,
                'confidence': 0.5  # Lower confidence for heuristic
            })
    
    # Deduplicate
    seen = set()
    unique_entities = []
    for entity in entities:
        key = (entity['type'], entity['text'])
        if key not in seen:
            seen.add(key)
            unique_entities.append(entity)
    
    return unique_entities[:20]  # Limit to top 20


def extract_entities(text: str) -> List[Dict]:
    """Extract named entities from text."""
    if USE_SPACY and spacy_nlp:
        return extract_entities_spacy(text)
    else:
        return extract_entities_heuristic(text)


def resolve_tickers(symbols_candidates: List[str]) -> List[Dict]:
    """Resolve and validate ticker symbols."""
    tickers = []
    
    for symbol in symbols_candidates:
        if not symbol:
            continue
        
        # Check against whitelist
        if symbol in TICKER_WHITELIST_SET:
            tickers.append({
                'symbol': symbol,
                'confidence': 0.9,
                'method': 'validated'
            })
        else:
            # Not in whitelist, but was extracted by normalizer
            # Include with lower confidence
            tickers.append({
                'symbol': symbol,
                'confidence': 0.5,
                'method': 'regex'
            })
    
    # Deduplicate
    seen = set()
    unique_tickers = []
    for ticker in tickers:
        if ticker['symbol'] not in seen:
            seen.add(ticker['symbol'])
            unique_tickers.append(ticker)
    
    return unique_tickers


def analyze_sentiment(text: str) -> Dict:
    """Analyze sentiment of text."""
    try:
        scores = sentiment_analyzer.polarity_scores(text)
        # VADER compound score is already in [-1, 1] range
        compound = scores['compound']
        
        # Calculate confidence based on how far from neutral
        confidence = abs(compound)
        
        return {
            'score': round(compound, 3),
            'confidence': round(confidence, 3),
            'model': 'vader'
        }
    except Exception as e:
        logger.warning(json.dumps({'warning': 'Sentiment analysis failed', 'error': str(e)}))
        return {
            'score': 0.0,
            'confidence': 0.0,
            'model': 'none'
        }


def categorize_event(text: str, source_type: str) -> str:
    """Categorize event based on keywords."""
    text_lower = text.lower()
    
    # Define keyword patterns for each category
    patterns = {
        'earnings': ['earnings', 'revenue', 'profit', 'quarterly results', 'eps', 'guidance'],
        'regulation': ['sec', 'regulatory', 'compliance', 'lawsuit', 'investigation', 'fine', 'settlement'],
        'security': ['hack', 'breach', 'vulnerability', 'exploit', 'cyber', 'ransomware'],
        'macro': ['fed', 'federal reserve', 'interest rate', 'inflation', 'gdp', 'employment', 'treasury'],
        'product': ['launch', 'release', 'product', 'feature', 'update', 'version'],
        'crypto': ['bitcoin', 'ethereum', 'blockchain', 'crypto', 'defi', 'nft'],
        'company': ['merger', 'acquisition', 'ceo', 'executive', 'layoff', 'hiring'],
    }
    
    # Check for pattern matches
    for category, keywords in patterns.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category
    
    # Default based on source type
    if source_type == 'market':
        return 'market'
    
    return 'other'


def validate_schema(data: dict, schema: dict, schema_name: str) -> Tuple[bool, Optional[str]]:
    """Validate data against JSON schema using cached validator."""
    try:
        # Use cached validators for better performance
        if schema_name == 'normalized_event.v1':
            validator = normalized_validator
        elif schema_name == 'enriched_event.v1':
            validator = enriched_validator
        else:
            # Fallback for unknown schemas
            validator = Draft202012Validator(schema)
        
        validator.validate(data)
        return True, None
    except jsonschema.ValidationError as e:
        error_path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "root"
        error_msg = f"Schema validation failed at {error_path}: {e.message}"
        return False, error_msg
    except Exception as e:
        return False, f"Validation error: {str(e)}"


def write_to_minio(s3_client, bucket: str, key: str, data: dict) -> bool:
    """Write JSON data to MinIO."""
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(data, indent=2).encode('utf-8'),
            ContentType='application/json'
        )
        return True
    except ClientError as e:
        logger.error(json.dumps({'error': 'MinIO write failed', 'key': key, 'details': str(e)}))
        return False


def publish_to_dlq(producer, event_id: str, correlation_id: Optional[str], 
                   error_type: str, error_message: str, failed_stage: str,
                   original_payload: dict):
    """Publish failed event to DLQ."""
    dlq_message = {
        'event_id': event_id,
        'correlation_id': correlation_id,
        'failed_at_utc': datetime.now(timezone.utc).isoformat(),
        'error_type': error_type,
        'error_message': error_message,
        'failed_stage': failed_stage,
        'original_payload': original_payload
    }
    
    try:
        producer.send(
            KAFKA_TOPIC_DLQ,
            value=dlq_message,
            key=event_id.encode('utf-8') if event_id else None
        )
        producer.flush()
        metrics_dlq.inc()
        stats['dlq_count'] += 1
        logger.warning(json.dumps({
            'event': 'dlq_publish',
            'event_id': event_id,
            'error_type': error_type,
            'stage': failed_stage
        }))
    except Exception as e:
        logger.error(json.dumps({
            'error': 'Failed to publish to DLQ',
            'event_id': event_id,
            'details': str(e)
        }))


def enrich_event(normalized_event: dict, producer, s3_client) -> bool:
    """Process and enrich a single normalized event."""
    global sentiment_sum, sentiment_count
    
    start_time = time.time()
    event_id = normalized_event.get('event_id', 'unknown')
    
    try:
        # Extract fields from normalized event
        normalized_text = normalized_event.get('normalized_text', '')
        lang = normalized_event.get('lang', 'en')
        metadata = normalized_event.get('metadata', {})
        source_type = metadata.get('source_type', 'unknown')
        source_name = metadata.get('source_name', 'unknown')
        correlation_id = metadata.get('correlation_id')
        symbols_candidates = normalized_event.get('symbols_candidates', [])
        canonical_url = normalized_event.get('canonical_url')
        
        # Extract event_time from metadata or use None
        event_time_utc = metadata.get('published_at')
        
        # Create hash of normalized text
        normalized_text_hash = hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()
        
        # Initialize quality flags
        quality_flags = []
        
        # Check text length
        if len(normalized_text) < 20:
            quality_flags.append('LOW_TEXT')
        
        # Extract entities
        entities_start = time.time()
        entities = extract_entities(normalized_text)
        metrics_entities_duration.observe(time.time() - entities_start)
        
        if not entities or all(e['confidence'] < 0.7 for e in entities):
            quality_flags.append('ENTITIES_UNCERTAIN')
            metrics_low_confidence.labels(kind='entities').inc()
        
        # Resolve tickers
        tickers = resolve_tickers(symbols_candidates)
        
        if tickers and all(t['confidence'] < 0.7 for t in tickers):
            quality_flags.append('TICKERS_UNCERTAIN')
            metrics_low_confidence.labels(kind='tickers').inc()
        
        # Analyze sentiment
        sentiment_start = time.time()
        sentiment = analyze_sentiment(normalized_text)
        metrics_sentiment_duration.observe(time.time() - sentiment_start)
        
        if abs(sentiment['score']) < 0.1:
            quality_flags.append('SENTIMENT_NEUTRAL')
        elif sentiment['confidence'] < 0.5:
            metrics_low_confidence.labels(kind='sentiment').inc()
        
        # Update sentiment mean for drift detection
        sentiment_sum += sentiment['score']
        sentiment_count += 1
        if sentiment_count > 0:
            metrics_sentiment_mean.set(sentiment_sum / sentiment_count)
        
        # Categorize event
        event_category = categorize_event(normalized_text, source_type)
        metrics_category.labels(category=event_category).inc()
        
        # Handle embeddings (optional)
        embedding = None
        if ENABLE_EMBEDDINGS:
            # Placeholder for embeddings - implement if needed
            embedding_start = time.time()
            # embedding = generate_embedding(normalized_text)
            metrics_embedding_duration.observe(time.time() - embedding_start)
        
        # Construct enriched event
        enriched_event = {
            'schema_version': 'enriched_event.v1',
            'event_id': event_id,
            'enriched_at_utc': datetime.now(timezone.utc).isoformat(),
            'pipeline_version': PIPELINE_VERSION,
            'source_type': source_type,
            'source_name': source_name,
            'event_time_utc': event_time_utc,
            'canonical_url': canonical_url,
            'lang': lang,
            'normalized_text_hash': normalized_text_hash,
            'entities': entities,
            'tickers': tickers,
            'sentiment': sentiment,
            'event_category': event_category,
            'embedding': embedding,
            'quality_flags': quality_flags
        }
        
        # Validate enriched event against schema
        is_valid, error_msg = validate_schema(enriched_event, ENRICHED_SCHEMA, 'enriched_event.v1')
        if not is_valid:
            metrics_failed.labels(stage='schema_validation').inc()
            publish_to_dlq(
                producer, event_id, correlation_id,
                'SCHEMA_INVALID', error_msg, 'schema',
                normalized_event
            )
            return False
        
        # Write to MinIO if enabled
        if WRITE_ENRICHED_TO_MINIO:
            # Create date-partitioned path
            date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            minio_key = f"enriched/source={source_type}/dt={date_str}/{event_id}.json"
            
            if not write_to_minio(s3_client, MINIO_BUCKET_ARTIFACTS, minio_key, enriched_event):
                logger.warning(json.dumps({
                    'warning': 'MinIO write failed',
                    'event_id': event_id,
                    'key': minio_key
                }))
                # Don't fail the entire event if MinIO write fails
        
        # Publish to Kafka
        producer.send(
            KAFKA_TOPIC_ENRICHED,
            value=enriched_event,
            key=event_id.encode('utf-8')
        )
        producer.flush()
        
        # Update metrics and stats
        metrics_enriched.inc()
        stats['enriched'] += 1
        metrics_processing_duration.observe(time.time() - start_time)
        
        global last_success_timestamp
        last_success_timestamp = time.time()
        metrics_last_success.set(last_success_timestamp)
        
        logger.info(json.dumps({
            'event': 'enriched',
            'event_id': event_id,
            'category': event_category,
            'sentiment': sentiment['score'],
            'entities_count': len(entities),
            'tickers_count': len(tickers),
            'duration_ms': round((time.time() - start_time) * 1000, 2)
        }))
        
        return True
        
    except Exception as e:
        metrics_failed.labels(stage='processing').inc()
        stats['failed'] += 1
        logger.error(json.dumps({
            'error': 'Enrichment failed',
            'event_id': event_id,
            'details': str(e)
        }))
        
        publish_to_dlq(
            producer, event_id, 
            normalized_event.get('metadata', {}).get('correlation_id'),
            'PROCESSING_FAILED', str(e), 'processing',
            normalized_event
        )
        return False


def consume_loop():
    """Main consumer loop."""
    global is_healthy
    
    logger.info(json.dumps({'message': 'Starting NLP enricher service'}))
    
    # Initialize Kafka consumer
    consumer = KafkaConsumer(
        KAFKA_TOPIC_NORMALIZED,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_CONSUMER_GROUP,
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        key_deserializer=lambda m: m.decode('utf-8') if m else None
    )
    
    # Initialize Kafka producer
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        compression_type='snappy'
    )
    
    # Initialize MinIO client
    s3_client = boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY
    )
    
    is_healthy = True
    logger.info(json.dumps({'message': 'Consumer loop started', 'topic': KAFKA_TOPIC_NORMALIZED}))
    
    try:
        for message in consumer:
            if shutdown_event.is_set():
                break
            
            metrics_consumed.inc()
            stats['consumed'] += 1
            
            normalized_event = message.value
            event_id = normalized_event.get('event_id', 'unknown')
            
            # Validate input schema
            is_valid, error_msg = validate_schema(
                normalized_event, 
                NORMALIZED_SCHEMA,
                'normalized_event.v1'
            )
            
            if not is_valid:
                logger.warning(json.dumps({
                    'warning': 'Invalid input schema',
                    'event_id': event_id,
                    'error': error_msg
                }))
                metrics_failed.labels(stage='input_schema').inc()
                publish_to_dlq(
                    producer, event_id,
                    normalized_event.get('metadata', {}).get('correlation_id'),
                    'SCHEMA_INVALID', error_msg, 'schema',
                    normalized_event
                )
                continue
            
            # Enrich the event
            enrich_event(normalized_event, producer, s3_client)
    
    except Exception as e:
        logger.error(json.dumps({'error': 'Consumer loop failed', 'details': str(e)}))
        is_healthy = False
    finally:
        consumer.close()
        producer.close()
        logger.info(json.dumps({'message': 'Consumer loop stopped'}))


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(json.dumps({'message': 'Shutdown signal received'}))
    shutdown_event.set()


def main():
    """Main entry point."""
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start health server in background
    health_thread = Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Run consumer loop in main thread
    try:
        consume_loop()
    except Exception as e:
        logger.error(json.dumps({'error': 'Fatal error', 'details': str(e)}))
        sys.exit(1)
    
    logger.info(json.dumps({'message': 'Service shutdown complete'}))


if __name__ == '__main__':
    main()
