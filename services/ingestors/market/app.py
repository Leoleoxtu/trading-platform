#!/usr/bin/env python3
"""
Market Data Ingestor Service

Fetches OHLCV market data from yfinance and stores in TimescaleDB.
Provides data quality monitoring and observability metrics.
"""

import os
import sys
import json
import logging
import signal
import time
from datetime import datetime, timezone, timedelta
from threading import Thread, Event
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Optional, Tuple

import yfinance as yf
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from psycopg2 import sql
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"market-ingestor","message":%(message)s}',
    datefmt='%Y-%m-%dT%H:%M:%SZ'
)
logger = logging.getLogger(__name__)

# Configuration from environment
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'timescaledb')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'market')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'market')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'market_secret_change_me')

MARKET_TICKERS = os.getenv('MARKET_TICKERS', 'AAPL,MSFT,TSLA')
MARKET_TIMEFRAMES = os.getenv('MARKET_TIMEFRAMES', '1m,5m,1d')
MARKET_LOOKBACK_DAYS = int(os.getenv('MARKET_LOOKBACK_DAYS', '30'))
MARKET_REFRESH_SECONDS = int(os.getenv('MARKET_REFRESH_SECONDS', '300'))
MARKET_ADJUSTED = os.getenv('MARKET_ADJUSTED', 'true').lower() == 'true'
HEALTH_PORT = int(os.getenv('HEALTH_PORT', '8000'))

# Global state
shutdown_event = Event()
is_healthy = False
last_success_timestamp = time.time()
last_fetch_errors: Dict[str, str] = {}

# Prometheus metrics
# Counters
metrics_candles_upserted = Counter(
    'market_ingestor_candles_upserted_total',
    'Total OHLCV candles upserted to database',
    ['timeframe']
)
metrics_fetch_failed = Counter(
    'market_ingestor_fetch_failed_total',
    'Total failed data fetch attempts',
    ['reason']
)
metrics_missing_candles = Counter(
    'market_ingestor_missing_candles_detected_total',
    'Total missing candles detected',
    ['timeframe']
)

# Histograms
metrics_fetch_duration = Histogram(
    'market_ingestor_fetch_duration_seconds',
    'Duration of market data fetch operations',
    ['timeframe']
)
metrics_db_upsert_duration = Histogram(
    'market_ingestor_db_upsert_duration_seconds',
    'Duration of database upsert operations',
    ['timeframe']
)

# Gauges
metrics_last_success = Gauge(
    'market_ingestor_last_success_timestamp',
    'Timestamp of last successful data fetch'
)
metrics_last_candle_timestamp = Gauge(
    'market_ingestor_last_candle_timestamp',
    'Timestamp of most recent candle fetched',
    ['timeframe']
)


# Timeframe mapping for yfinance
TIMEFRAME_MAP = {
    '1m': '1m',
    '2m': '2m',
    '5m': '5m',
    '15m': '15m',
    '30m': '30m',
    '60m': '60m',
    '1h': '1h',
    '90m': '90m',
    '1d': '1d',
    '5d': '5d',
    '1wk': '1wk',
    '1mo': '1mo',
    '3mo': '3mo'
}

# Period mapping based on timeframe
def get_period_for_timeframe(timeframe: str, lookback_days: int) -> str:
    """Get appropriate period string for yfinance based on timeframe."""
    # For intraday data, yfinance has limitations
    if timeframe in ['1m', '2m', '5m', '15m', '30m', '60m', '1h', '90m']:
        # Intraday data limited to last 60 days for minute intervals
        if lookback_days <= 7:
            return '7d'
        elif lookback_days <= 30:
            return '30d'
        else:
            return '60d'  # Max for minute data
    else:
        # Daily and higher can go back further
        if lookback_days <= 30:
            return '1mo'
        elif lookback_days <= 90:
            return '3mo'
        elif lookback_days <= 180:
            return '6mo'
        elif lookback_days <= 365:
            return '1y'
        else:
            return '2y'


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for health checks and metrics."""
    
    def do_GET(self):
        if self.path == '/health':
            if is_healthy:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                
                # Get recent candle info from DB
                try:
                    conn = get_db_connection()
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT COUNT(DISTINCT instrument_id) as ticker_count,
                                   COUNT(DISTINCT timeframe) as timeframe_count,
                                   MAX(ts) as latest_candle
                            FROM ohlcv
                            WHERE ingested_at > NOW() - INTERVAL '1 hour'
                        """)
                        row = cur.fetchone()
                        ticker_count = row[0] if row else 0
                        timeframe_count = row[1] if row else 0
                        latest_candle = row[2].isoformat() if row and row[2] else None
                    conn.close()
                except Exception as e:
                    logger.error(json.dumps({'message': 'Health check DB query failed', 'error': str(e)}))
                    ticker_count = 0
                    timeframe_count = 0
                    latest_candle = None
                
                response = {
                    'status': 'healthy',
                    'service': 'market-ingestor',
                    'tickers': MARKET_TICKERS.split(','),
                    'timeframes': MARKET_TIMEFRAMES.split(','),
                    'adjusted': MARKET_ADJUSTED,
                    'recent_data': {
                        'tickers_updated': ticker_count,
                        'timeframes_updated': timeframe_count,
                        'latest_candle': latest_candle
                    }
                }
                self.wfile.write(json.dumps(response).encode())
            else:
                self.send_response(503)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {
                    'status': 'unhealthy',
                    'errors': last_fetch_errors
                }
                self.wfile.write(json.dumps(response).encode())
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


def get_db_connection():
    """Create PostgreSQL database connection."""
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        connect_timeout=10
    )


def test_db_connection() -> bool:
    """Test database connectivity."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
        conn.close()
        logger.info(json.dumps({'message': 'Database connection successful'}))
        return True
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Database connection failed',
            'error': str(e)
        }))
        return False


def fetch_ohlcv_data(
    ticker: str,
    timeframe: str,
    period: str,
    adjusted: bool
) -> Optional[List[Tuple]]:
    """
    Fetch OHLCV data from yfinance.
    
    Returns list of tuples: (timestamp, open, high, low, close, volume)
    """
    try:
        start_time = time.time()
        
        # Get yfinance timeframe
        yf_interval = TIMEFRAME_MAP.get(timeframe)
        if not yf_interval:
            logger.error(json.dumps({
                'message': 'Invalid timeframe',
                'timeframe': timeframe
            }))
            metrics_fetch_failed.labels(reason='invalid_timeframe').inc()
            return None
        
        logger.info(json.dumps({
            'message': 'Fetching market data',
            'ticker': ticker,
            'timeframe': timeframe,
            'period': period,
            'adjusted': adjusted
        }))
        
        # Fetch data from yfinance
        stock = yf.Ticker(ticker)
        df = stock.history(
            period=period,
            interval=yf_interval,
            auto_adjust=adjusted,
            actions=False  # Don't include dividends/splits as separate rows
        )
        
        duration = time.time() - start_time
        metrics_fetch_duration.labels(timeframe=timeframe).observe(duration)
        
        if df.empty:
            logger.warning(json.dumps({
                'message': 'No data returned',
                'ticker': ticker,
                'timeframe': timeframe,
                'period': period
            }))
            metrics_fetch_failed.labels(reason='no_data').inc()
            return None
        
        # Convert to list of tuples
        # Ensure timestamps are in UTC
        data = []
        for idx, row in df.iterrows():
            # Convert pandas Timestamp to Python datetime in UTC
            ts = idx.to_pydatetime()
            if ts.tzinfo is None:
                # Naive timestamp - assume UTC
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                # Convert to UTC if timezone-aware
                ts = ts.astimezone(timezone.utc)
            
            # Convert values to float with error handling
            try:
                open_val = float(row['Open']) if not pd.isna(row['Open']) else None
                high_val = float(row['High']) if not pd.isna(row['High']) else None
                low_val = float(row['Low']) if not pd.isna(row['Low']) else None
                close_val = float(row['Close']) if not pd.isna(row['Close']) else None
                volume_val = float(row['Volume']) if not pd.isna(row['Volume']) else None
                
                # Skip rows with missing critical data
                if any(v is None for v in [open_val, high_val, low_val, close_val, volume_val]):
                    logger.warning(json.dumps({
                        'message': 'Skipping row with missing data',
                        'ticker': ticker,
                        'timestamp': ts.isoformat()
                    }))
                    continue
                
                data.append((ts, open_val, high_val, low_val, close_val, volume_val))
            except (ValueError, TypeError) as e:
                logger.warning(json.dumps({
                    'message': 'Failed to convert row to numeric values',
                    'ticker': ticker,
                    'timestamp': ts.isoformat(),
                    'error': str(e)
                }))
                continue
        
        logger.info(json.dumps({
            'message': 'Data fetched successfully',
            'ticker': ticker,
            'timeframe': timeframe,
            'candles': len(data),
            'duration_seconds': round(duration, 2)
        }))
        
        return data
        
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Failed to fetch data',
            'ticker': ticker,
            'timeframe': timeframe,
            'error': str(e)
        }))
        metrics_fetch_failed.labels(reason='api').inc()
        return None


def detect_missing_candles(
    data: List[Tuple],
    timeframe: str
) -> int:
    """
    Detect missing candles in the data series.
    
    Returns count of missing candles.
    """
    if len(data) < 2:
        return 0
    
    # Calculate expected interval based on timeframe
    interval_map = {
        '1m': timedelta(minutes=1),
        '2m': timedelta(minutes=2),
        '5m': timedelta(minutes=5),
        '15m': timedelta(minutes=15),
        '30m': timedelta(minutes=30),
        '60m': timedelta(hours=1),
        '1h': timedelta(hours=1),
        '90m': timedelta(minutes=90),
        '1d': timedelta(days=1),
        '5d': timedelta(days=5),
        '1wk': timedelta(weeks=1),
        '1mo': timedelta(days=30),  # Approximate
        '3mo': timedelta(days=90),  # Approximate
    }
    
    expected_delta = interval_map.get(timeframe)
    if not expected_delta:
        return 0
    
    missing_count = 0
    for i in range(1, len(data)):
        prev_ts = data[i-1][0]
        curr_ts = data[i][0]
        actual_delta = curr_ts - prev_ts
        
        # For minute intervals, account for market hours and weekends
        # For daily intervals, account for weekends and holidays
        # This is a simple check - more sophisticated logic would account for exact market hours
        
        if timeframe in ['1m', '2m', '5m', '15m', '30m', '60m', '1h', '90m']:
            # Allow some tolerance for intraday data (market hours, gaps)
            # Skip large gaps (overnight, weekends)
            if actual_delta > expected_delta * 10:
                continue
            elif actual_delta > expected_delta * 1.5:
                # Estimate missing candles
                estimated_missing = int(actual_delta / expected_delta) - 1
                missing_count += estimated_missing
        else:
            # For daily and higher, simpler logic
            if actual_delta > expected_delta * 1.5:
                estimated_missing = int(actual_delta / expected_delta) - 1
                missing_count += estimated_missing
    
    if missing_count > 0:
        logger.warning(json.dumps({
            'message': 'Missing candles detected',
            'timeframe': timeframe,
            'missing_count': missing_count
        }))
        metrics_missing_candles.labels(timeframe=timeframe).inc(missing_count)
    
    return missing_count


def upsert_ohlcv_data(
    conn,
    ticker: str,
    timeframe: str,
    data: List[Tuple]
) -> int:
    """
    Upsert OHLCV data into TimescaleDB.
    
    Returns number of rows upserted.
    """
    if not data:
        return 0
    
    try:
        start_time = time.time()
        
        # Prepare data for insert
        # Format: (instrument_id, timeframe, ts, open, high, low, close, volume, source, ingested_at)
        now = datetime.now(timezone.utc)
        values = [
            (ticker, timeframe, ts, o, h, l, c, v, 'yfinance', now)
            for ts, o, h, l, c, v in data
        ]
        
        # Use INSERT ... ON CONFLICT to handle duplicates (idempotent)
        query = """
            INSERT INTO ohlcv (instrument_id, timeframe, ts, open, high, low, close, volume, source, ingested_at)
            VALUES %s
            ON CONFLICT (instrument_id, timeframe, ts)
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                source = EXCLUDED.source,
                ingested_at = EXCLUDED.ingested_at
        """
        
        with conn.cursor() as cur:
            execute_values(cur, query, values)
            conn.commit()
        
        duration = time.time() - start_time
        metrics_db_upsert_duration.labels(timeframe=timeframe).observe(duration)
        metrics_candles_upserted.labels(timeframe=timeframe).inc(len(data))
        
        # Update last candle timestamp metric
        latest_ts = max(ts for ts, _, _, _, _, _ in data)
        metrics_last_candle_timestamp.labels(timeframe=timeframe).set(latest_ts.timestamp())
        
        logger.info(json.dumps({
            'message': 'Data upserted successfully',
            'ticker': ticker,
            'timeframe': timeframe,
            'rows': len(data),
            'duration_seconds': round(duration, 3)
        }))
        
        return len(data)
        
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Failed to upsert data',
            'ticker': ticker,
            'timeframe': timeframe,
            'error': str(e)
        }))
        metrics_fetch_failed.labels(reason='db').inc()
        conn.rollback()
        return 0


def refresh_materialized_view(conn):
    """Refresh the materialized view for latest candles."""
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT refresh_ohlcv_latest()')
            conn.commit()
        logger.info(json.dumps({'message': 'Materialized view refreshed'}))
    except Exception as e:
        logger.warning(json.dumps({
            'message': 'Failed to refresh materialized view',
            'error': str(e)
        }))
        conn.rollback()


def process_ticker_timeframe(
    conn,
    ticker: str,
    timeframe: str,
    period: str,
    adjusted: bool
) -> bool:
    """Process a single ticker/timeframe combination."""
    try:
        # Fetch data
        data = fetch_ohlcv_data(ticker, timeframe, period, adjusted)
        if not data:
            return False
        
        # Detect missing candles
        detect_missing_candles(data, timeframe)
        
        # Upsert to database
        upsert_ohlcv_data(conn, ticker, timeframe, data)
        
        return True
        
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Error processing ticker/timeframe',
            'ticker': ticker,
            'timeframe': timeframe,
            'error': str(e)
        }))
        return False


def ingestion_loop():
    """Main ingestion loop."""
    global is_healthy, last_success_timestamp, last_fetch_errors
    
    # Parse configuration
    tickers = [t.strip() for t in MARKET_TICKERS.split(',') if t.strip()]
    timeframes = [tf.strip() for tf in MARKET_TIMEFRAMES.split(',') if tf.strip()]
    
    if not tickers:
        logger.error(json.dumps({'message': 'No tickers configured'}))
        return
    
    if not timeframes:
        logger.error(json.dumps({'message': 'No timeframes configured'}))
        return
    
    logger.info(json.dumps({
        'message': 'Starting market data ingestor',
        'tickers': tickers,
        'timeframes': timeframes,
        'lookback_days': MARKET_LOOKBACK_DAYS,
        'refresh_seconds': MARKET_REFRESH_SECONDS,
        'adjusted': MARKET_ADJUSTED
    }))
    
    # Test database connection
    if not test_db_connection():
        logger.error(json.dumps({'message': 'Cannot connect to database'}))
        return
    
    is_healthy = True
    
    try:
        while not shutdown_event.is_set():
            start_time = time.time()
            last_fetch_errors.clear()
            
            # Get database connection
            try:
                conn = get_db_connection()
            except Exception as e:
                logger.error(json.dumps({
                    'message': 'Failed to connect to database',
                    'error': str(e)
                }))
                last_fetch_errors['database'] = str(e)
                shutdown_event.wait(timeout=60)
                continue
            
            # Process each ticker/timeframe combination
            success_count = 0
            total_count = len(tickers) * len(timeframes)
            
            for ticker in tickers:
                if shutdown_event.is_set():
                    break
                
                for timeframe in timeframes:
                    if shutdown_event.is_set():
                        break
                    
                    # Get appropriate period for this timeframe
                    period = get_period_for_timeframe(timeframe, MARKET_LOOKBACK_DAYS)
                    
                    # Process ticker/timeframe
                    success = process_ticker_timeframe(
                        conn, ticker, timeframe, period, MARKET_ADJUSTED
                    )
                    
                    if success:
                        success_count += 1
                    else:
                        last_fetch_errors[f'{ticker}_{timeframe}'] = 'fetch_failed'
                    
                    # Small delay between requests to avoid rate limiting
                    time.sleep(0.5)
            
            # Refresh materialized view
            refresh_materialized_view(conn)
            
            # Close connection
            conn.close()
            
            # Update metrics
            if success_count > 0:
                last_success_timestamp = time.time()
                metrics_last_success.set(last_success_timestamp)
            
            # Log cycle summary
            elapsed = time.time() - start_time
            sleep_time = max(0, MARKET_REFRESH_SECONDS - elapsed)
            
            logger.info(json.dumps({
                'message': 'Ingestion cycle complete',
                'successful': success_count,
                'total': total_count,
                'elapsed_seconds': round(elapsed, 2),
                'next_refresh_in': round(sleep_time, 2)
            }))
            
            # Wait for next cycle
            shutdown_event.wait(timeout=sleep_time)
            
    except KeyboardInterrupt:
        logger.info(json.dumps({'message': 'Received interrupt signal'}))
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Ingestion loop error',
            'error': str(e)
        }))
        is_healthy = False
        raise
    finally:
        logger.info(json.dumps({'message': 'Market ingestor stopped'}))


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
    
    # Run ingestion loop
    try:
        ingestion_loop()
    except Exception as e:
        logger.error(json.dumps({
            'message': 'Fatal error',
            'error': str(e)
        }))
        sys.exit(1)


if __name__ == '__main__':
    main()
