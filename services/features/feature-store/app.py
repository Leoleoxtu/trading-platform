#!/usr/bin/env python3
"""
Feature Store Service v1

Computes and stores versioned feature vectors combining:
- Market features (OHLCV-based: returns, volatility, volume)
- NLP/Event features (sentiment, event counts from enriched events)

Architecture: Batch/Periodic compute (Approach 1)
- Reads latest OHLCV candles from TimescaleDB
- Consumes enriched events from Kafka (maintains local cache)
- Computes features on a schedule
- Upserts to feature_vectors table with idempotency

Observability: Prometheus metrics + health endpoint
"""

import os
import sys
import json
import logging
import hashlib
import signal
import time
import uuid
from datetime import datetime, timezone, timedelta
from threading import Thread, Event, Lock
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict, deque
from dataclasses import dataclass, asdict

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from psycopg2 import sql
import numpy as np
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"feature-store","message":%(message)s}',
    datefmt='%Y-%m-%dT%H:%M:%SZ'
)
logger = logging.getLogger(__name__)

# Configuration from environment
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'timescaledb')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'market')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'market')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'market_secret_change_me')

KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'redpanda:9092')
ENRICHED_TOPIC = os.getenv('ENRICHED_TOPIC', 'events.enriched.v1')

FEATURE_TICKERS = os.getenv('FEATURE_TICKERS', 'AAPL,MSFT,TSLA')
FEATURE_TIMEFRAMES = os.getenv('FEATURE_TIMEFRAMES', '1m,1d')
FEATURE_SET_VERSION = os.getenv('FEATURE_SET_VERSION', 'fs_v1')
FEATURE_REFRESH_SECONDS = int(os.getenv('FEATURE_REFRESH_SECONDS', '60'))
FEATURE_LOOKBACK_PERIODS = int(os.getenv('FEATURE_LOOKBACK_PERIODS', '200'))
FEATURE_EVENT_WINDOW_MINUTES = int(os.getenv('FEATURE_EVENT_WINDOW_MINUTES', '60'))
PIPELINE_VERSION = os.getenv('PIPELINE_VERSION', 'feature-store.v1.0')
HEALTH_PORT = int(os.getenv('HEALTH_PORT', '8000'))

# Parse configuration
TICKERS_LIST = [t.strip() for t in FEATURE_TICKERS.split(',') if t.strip()]
TIMEFRAMES_LIST = [tf.strip() for tf in FEATURE_TIMEFRAMES.split(',') if tf.strip()]

# Global state
shutdown_event = Event()
is_healthy = False
last_success_timestamp = time.time()
compute_active = False

# Event cache for NLP features (thread-safe)
event_cache_lock = Lock()
event_cache: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))  # ticker -> events
cache_max_age_seconds = FEATURE_EVENT_WINDOW_MINUTES * 60 * 2  # Keep 2x window

# Prometheus metrics
# Counters
metrics_compute_runs = Counter('feature_store_compute_runs_total', 'Total feature computation runs')
metrics_vectors_upserted = Counter('feature_store_feature_vectors_upserted_total', 'Total feature vectors upserted')
metrics_compute_failed = Counter('feature_store_compute_failed_total', 'Total failed computations', ['reason'])
metrics_quality_flags = Counter('feature_store_quality_flag_total', 'Quality flags raised', ['flag'])

# Histograms
metrics_compute_duration = Histogram('feature_store_compute_duration_seconds', 'Feature computation duration')
metrics_db_upsert_duration = Histogram('feature_store_db_upsert_duration_seconds', 'DB upsert duration')

# Gauges
metrics_last_success = Gauge('feature_store_last_success_timestamp', 'Timestamp of last successful compute')
metrics_last_feature_ts = Gauge('feature_store_last_feature_ts_timestamp', 'Timestamp of last feature computed', ['timeframe'])
metrics_cached_events = Gauge('feature_store_cached_events', 'Number of events in cache')


@dataclass
class FeatureVector:
    """Feature vector data structure"""
    feature_id: str
    instrument_id: str
    timeframe: str
    ts_utc: datetime
    feature_set_version: str
    features: Dict[str, float]
    quality_flags: List[str]
    computed_at_utc: datetime
    pipeline_version: str
    source_refs: Optional[Dict[str, Any]] = None


def get_db_connection():
    """Get PostgreSQL connection."""
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )


def compute_market_features(candles: List[Dict], quality_flags: List[str]) -> Dict[str, float]:
    """
    Compute market-based features from OHLCV candles.
    
    Features:
    - ret_1: Simple return over 1 period
    - ret_5: Simple return over 5 periods
    - vol_20: Rolling volatility (std of returns over 20 periods)
    
    Args:
        candles: List of OHLCV candle dicts (oldest first)
        quality_flags: List to append quality flags to
    
    Returns:
        Dict of feature name -> value
    """
    features = {}
    
    if len(candles) < 2:
        quality_flags.append('INSUFFICIENT_OHLCV')
        return features
    
    # Extract close prices
    closes = np.array([float(c['close']) for c in candles])
    
    # ret_1: Simple return over 1 period
    if len(closes) >= 2:
        features['ret_1'] = float((closes[-1] / closes[-2]) - 1.0)
    
    # ret_5: Simple return over 5 periods
    if len(closes) >= 6:
        features['ret_5'] = float((closes[-1] / closes[-6]) - 1.0)
    elif len(closes) >= 2:
        quality_flags.append('INSUFFICIENT_OHLCV')
    
    # vol_20: Rolling volatility (std of 1-period returns over 20 periods)
    if len(closes) >= 21:
        returns = np.diff(closes) / closes[:-1]
        features['vol_20'] = float(np.std(returns[-20:]))
    elif len(closes) >= 2:
        quality_flags.append('INSUFFICIENT_OHLCV')
    
    return features


def compute_event_features(events: List[Dict], window_start: datetime, window_end: datetime, quality_flags: List[str]) -> Dict[str, float]:
    """
    Compute event/NLP-based features from enriched events.
    
    Features:
    - event_count_1h: Number of events in window
    - sentiment_mean_1h: Mean sentiment score
    - sentiment_conf_mean_1h: Mean sentiment confidence
    - sentiment_weighted_1h: Confidence-weighted mean sentiment
    - sentiment_std_1h: Standard deviation of sentiment scores
    
    Args:
        events: List of enriched event dicts
        window_start: Start of aggregation window
        window_end: End of aggregation window
        quality_flags: List to append quality flags to
    
    Returns:
        Dict of feature name -> value
    """
    features = {}
    
    if not events:
        quality_flags.append('NO_EVENTS')
        features['event_count_1h'] = 0.0
        return features
    
    features['event_count_1h'] = float(len(events))
    
    # Extract sentiment data
    sentiments = []
    confidences = []
    for event in events:
        if 'sentiment' in event and event['sentiment']:
            sent = event['sentiment']
            sentiments.append(float(sent.get('score', 0.0)))
            confidences.append(float(sent.get('confidence', 0.0)))
    
    if not sentiments:
        quality_flags.append('NO_EVENTS')
        return features
    
    sentiments = np.array(sentiments)
    confidences = np.array(confidences)
    
    # Mean sentiment
    features['sentiment_mean_1h'] = float(np.mean(sentiments))
    
    # Mean confidence
    features['sentiment_conf_mean_1h'] = float(np.mean(confidences))
    
    # Confidence-weighted sentiment
    if np.sum(confidences) > 0:
        features['sentiment_weighted_1h'] = float(np.sum(sentiments * confidences) / np.sum(confidences))
    else:
        features['sentiment_weighted_1h'] = features['sentiment_mean_1h']
        quality_flags.append('LOW_SENTIMENT_CONFIDENCE')
    
    # Standard deviation
    if len(sentiments) > 1:
        features['sentiment_std_1h'] = float(np.std(sentiments))
    
    # Flag if confidence is low on average
    if np.mean(confidences) < 0.5:
        quality_flags.append('LOW_SENTIMENT_CONFIDENCE')
    
    return features


def fetch_ohlcv_candles(conn, instrument_id: str, timeframe: str, limit: int) -> List[Dict]:
    """Fetch recent OHLCV candles from database."""
    query = """
        SELECT instrument_id, timeframe, ts, open, high, low, close, volume
        FROM ohlcv
        WHERE instrument_id = %s AND timeframe = %s
        ORDER BY ts DESC
        LIMIT %s
    """
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (instrument_id, timeframe, limit))
        candles = cur.fetchall()
    
    # Return oldest first for sequential computation
    return list(reversed(candles))


def get_events_for_window(instrument_id: str, window_start: datetime, window_end: datetime) -> List[Dict]:
    """Get enriched events for instrument within time window from cache."""
    with event_cache_lock:
        if instrument_id not in event_cache:
            return []
        
        # Filter events in window
        events_in_window = []
        for event in event_cache[instrument_id]:
            event_time = event.get('enriched_at_utc')
            if not event_time:
                continue
            
            # Parse if string
            if isinstance(event_time, str):
                event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
            
            if window_start <= event_time <= window_end:
                events_in_window.append(event)
        
        return events_in_window


def compute_feature_vector(instrument_id: str, timeframe: str) -> Optional[FeatureVector]:
    """
    Compute a feature vector for a given instrument and timeframe.
    
    Returns None if computation fails.
    """
    quality_flags = []
    
    try:
        # Connect to database
        conn = get_db_connection()
        
        # Fetch OHLCV candles
        candles = fetch_ohlcv_candles(conn, instrument_id, timeframe, FEATURE_LOOKBACK_PERIODS)
        conn.close()
        
        if not candles:
            quality_flags.append('MISSING_OHLCV')
            logger.warning(json.dumps({
                'event': 'no_ohlcv_data',
                'instrument_id': instrument_id,
                'timeframe': timeframe
            }))
            return None
        
        # Get timestamp of most recent candle
        latest_candle_ts = candles[-1]['ts']
        if isinstance(latest_candle_ts, str):
            latest_candle_ts = datetime.fromisoformat(latest_candle_ts.replace('Z', '+00:00'))
        
        # Compute market features
        market_features = compute_market_features(candles, quality_flags)
        
        # Define event window (ending at candle timestamp)
        window_end = latest_candle_ts
        window_start = window_end - timedelta(minutes=FEATURE_EVENT_WINDOW_MINUTES)
        
        # Get events from cache
        events = get_events_for_window(instrument_id, window_start, window_end)
        
        # Compute event features
        event_features = compute_event_features(events, window_start, window_end, quality_flags)
        
        # Combine all features
        all_features = {**market_features, **event_features}
        
        # Create feature vector
        vector = FeatureVector(
            feature_id=str(uuid.uuid4()),
            instrument_id=instrument_id,
            timeframe=timeframe,
            ts_utc=latest_candle_ts,
            feature_set_version=FEATURE_SET_VERSION,
            features=all_features,
            quality_flags=quality_flags,
            computed_at_utc=datetime.now(timezone.utc),
            pipeline_version=PIPELINE_VERSION,
            source_refs={
                'ohlcv_count': len(candles),
                'event_count': len(events),
                'event_window_start': window_start.isoformat(),
                'event_window_end': window_end.isoformat()
            }
        )
        
        return vector
        
    except Exception as e:
        logger.error(json.dumps({
            'event': 'compute_failed',
            'instrument_id': instrument_id,
            'timeframe': timeframe,
            'error': str(e)
        }))
        metrics_compute_failed.labels(reason='compute').inc()
        return None


def upsert_feature_vectors(vectors: List[FeatureVector]) -> int:
    """
    Upsert feature vectors to database.
    
    Returns number of vectors upserted.
    """
    if not vectors:
        return 0
    
    start_time = time.time()
    
    try:
        conn = get_db_connection()
        
        # Prepare data for bulk upsert
        values = []
        for v in vectors:
            values.append((
                v.instrument_id,
                v.timeframe,
                v.ts_utc,
                v.feature_set_version,
                json.dumps(v.features),
                v.quality_flags,
                v.computed_at_utc,
                v.pipeline_version,
                v.source_refs.get('event_window_start') if v.source_refs else None,
                v.source_refs.get('event_window_end') if v.source_refs else None,
                v.source_refs.get('event_count') if v.source_refs else None,
                v.source_refs.get('ohlcv_count') if v.source_refs else None
            ))
        
        # Upsert query with conflict resolution
        query = """
            INSERT INTO feature_vectors 
            (instrument_id, timeframe, ts, feature_set_version, features, 
             quality_flags, computed_at, pipeline_version,
             sentiment_window_start, sentiment_window_end, event_count, ohlcv_count)
            VALUES %s
            ON CONFLICT (instrument_id, timeframe, ts, feature_set_version)
            DO UPDATE SET
                features = EXCLUDED.features,
                quality_flags = EXCLUDED.quality_flags,
                computed_at = EXCLUDED.computed_at,
                pipeline_version = EXCLUDED.pipeline_version,
                sentiment_window_start = EXCLUDED.sentiment_window_start,
                sentiment_window_end = EXCLUDED.sentiment_window_end,
                event_count = EXCLUDED.event_count,
                ohlcv_count = EXCLUDED.ohlcv_count
        """
        
        with conn.cursor() as cur:
            execute_values(cur, query, values)
            conn.commit()
        
        conn.close()
        
        duration = time.time() - start_time
        metrics_db_upsert_duration.observe(duration)
        
        return len(vectors)
        
    except Exception as e:
        logger.error(json.dumps({
            'event': 'upsert_failed',
            'error': str(e),
            'vector_count': len(vectors)
        }))
        metrics_compute_failed.labels(reason='db').inc()
        return 0


def compute_cycle():
    """Run one computation cycle for all instruments and timeframes."""
    global last_success_timestamp, compute_active
    
    start_time = time.time()
    compute_active = True
    
    try:
        metrics_compute_runs.inc()
        
        vectors = []
        
        # Compute features for each instrument/timeframe combination
        for instrument_id in TICKERS_LIST:
            for timeframe in TIMEFRAMES_LIST:
                vector = compute_feature_vector(instrument_id, timeframe)
                if vector:
                    vectors.append(vector)
                    
                    # Update quality flag metrics
                    for flag in vector.quality_flags:
                        metrics_quality_flags.labels(flag=flag).inc()
                    
                    # Update last feature timestamp gauge
                    metrics_last_feature_ts.labels(timeframe=timeframe).set(vector.ts_utc.timestamp())
        
        # Upsert all vectors
        if vectors:
            upserted = upsert_feature_vectors(vectors)
            metrics_vectors_upserted.inc(upserted)
            
            logger.info(json.dumps({
                'event': 'compute_cycle_complete',
                'vectors_computed': len(vectors),
                'vectors_upserted': upserted,
                'duration_seconds': time.time() - start_time
            }))
        
        # Update success metrics
        last_success_timestamp = time.time()
        metrics_last_success.set(last_success_timestamp)
        
        duration = time.time() - start_time
        metrics_compute_duration.observe(duration)
        
    except Exception as e:
        logger.error(json.dumps({
            'event': 'compute_cycle_failed',
            'error': str(e)
        }))
        metrics_compute_failed.labels(reason='compute').inc()
    
    finally:
        compute_active = False


def compute_loop():
    """Main compute loop - runs on schedule."""
    global is_healthy
    
    logger.info(json.dumps({
        'event': 'compute_loop_started',
        'tickers': TICKERS_LIST,
        'timeframes': TIMEFRAMES_LIST,
        'refresh_seconds': FEATURE_REFRESH_SECONDS
    }))
    
    is_healthy = True
    
    while not shutdown_event.is_set():
        try:
            compute_cycle()
        except Exception as e:
            logger.error(json.dumps({
                'event': 'compute_loop_error',
                'error': str(e)
            }))
        
        # Wait for next cycle
        shutdown_event.wait(FEATURE_REFRESH_SECONDS)
    
    is_healthy = False
    logger.info(json.dumps({'event': 'compute_loop_stopped'}))


def event_consumer_loop():
    """Kafka consumer loop - maintains cache of enriched events."""
    logger.info(json.dumps({
        'event': 'event_consumer_started',
        'topic': ENRICHED_TOPIC,
        'bootstrap_servers': KAFKA_BOOTSTRAP_SERVERS
    }))
    
    try:
        consumer = KafkaConsumer(
            ENRICHED_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id='feature-store-v1',
            auto_offset_reset='latest',  # Only consume new events
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            session_timeout_ms=30000,
            max_poll_interval_ms=300000
        )
        
        while not shutdown_event.is_set():
            msg_batch = consumer.poll(timeout_ms=1000)
            
            if not msg_batch:
                continue
            
            for topic_partition, messages in msg_batch.items():
                for message in messages:
                    try:
                        event = message.value
                        
                        # Extract tickers from event
                        tickers = event.get('tickers', [])
                        
                        # Add event to cache for each ticker
                        with event_cache_lock:
                            for ticker_obj in tickers:
                                ticker = ticker_obj.get('symbol')
                                if ticker and ticker in TICKERS_LIST:
                                    event_cache[ticker].append(event)
                            
                            # Update cached events metric
                            total_cached = sum(len(q) for q in event_cache.values())
                            metrics_cached_events.set(total_cached)
                    
                    except Exception as e:
                        logger.error(json.dumps({
                            'event': 'event_processing_failed',
                            'error': str(e)
                        }))
        
        consumer.close()
        
    except Exception as e:
        logger.error(json.dumps({
            'event': 'event_consumer_failed',
            'error': str(e)
        }))
        metrics_compute_failed.labels(reason='kafka').inc()
    
    logger.info(json.dumps({'event': 'event_consumer_stopped'}))


def cache_cleanup_loop():
    """Periodic cleanup of old events from cache."""
    while not shutdown_event.is_set():
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=cache_max_age_seconds)
            
            with event_cache_lock:
                for ticker in list(event_cache.keys()):
                    # Filter out old events
                    cache = event_cache[ticker]
                    filtered = deque(maxlen=1000)
                    
                    for event in cache:
                        event_time = event.get('enriched_at_utc')
                        if isinstance(event_time, str):
                            event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
                        
                        if event_time and event_time >= cutoff_time:
                            filtered.append(event)
                    
                    if filtered:
                        event_cache[ticker] = filtered
                    else:
                        del event_cache[ticker]
                
                # Update metric
                total_cached = sum(len(q) for q in event_cache.values())
                metrics_cached_events.set(total_cached)
        
        except Exception as e:
            logger.error(json.dumps({
                'event': 'cache_cleanup_failed',
                'error': str(e)
            }))
        
        # Cleanup every 5 minutes
        shutdown_event.wait(300)


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for health checks and metrics."""
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def do_GET(self):
        if self.path == '/health':
            status = {
                'status': 'healthy' if is_healthy else 'starting',
                'compute_active': compute_active,
                'last_success_age_seconds': time.time() - last_success_timestamp,
                'cached_events': sum(len(q) for q in event_cache.values()),
                'feature_set_version': FEATURE_SET_VERSION,
                'pipeline_version': PIPELINE_VERSION
            }
            
            self.send_response(200 if is_healthy else 503)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(status, indent=2).encode())
        
        elif self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(generate_latest())
        
        else:
            self.send_response(404)
            self.end_headers()


def run_health_server():
    """Run health check HTTP server."""
    server = HTTPServer(('0.0.0.0', HEALTH_PORT), HealthHandler)
    logger.info(json.dumps({
        'event': 'health_server_started',
        'port': HEALTH_PORT
    }))
    
    while not shutdown_event.is_set():
        server.handle_request()
    
    logger.info(json.dumps({'event': 'health_server_stopped'}))


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(json.dumps({
        'event': 'shutdown_signal_received',
        'signal': signum
    }))
    shutdown_event.set()


def main():
    """Main entry point."""
    logger.info(json.dumps({
        'event': 'feature_store_starting',
        'config': {
            'tickers': TICKERS_LIST,
            'timeframes': TIMEFRAMES_LIST,
            'feature_set_version': FEATURE_SET_VERSION,
            'refresh_seconds': FEATURE_REFRESH_SECONDS,
            'lookback_periods': FEATURE_LOOKBACK_PERIODS,
            'event_window_minutes': FEATURE_EVENT_WINDOW_MINUTES,
            'pipeline_version': PIPELINE_VERSION
        }
    }))
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start background threads
    threads = [
        Thread(target=compute_loop, daemon=True, name='compute-loop'),
        Thread(target=event_consumer_loop, daemon=True, name='event-consumer'),
        Thread(target=cache_cleanup_loop, daemon=True, name='cache-cleanup'),
        Thread(target=run_health_server, daemon=True, name='health-server')
    ]
    
    for thread in threads:
        thread.start()
    
    # Wait for shutdown
    shutdown_event.wait()
    
    # Wait for threads to finish
    logger.info(json.dumps({'event': 'waiting_for_threads'}))
    for thread in threads:
        thread.join(timeout=10)
    
    logger.info(json.dumps({'event': 'feature_store_stopped'}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
