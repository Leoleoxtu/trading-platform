"""
Market Data Collector - Collects OHLCV data from financial markets.

Fetches 1-minute bars from yfinance (delayed) with optional Polygon.io (real-time).
Stores data directly in TimescaleDB for efficient time-series queries.
"""

import asyncio
import os
from datetime import datetime, timezone, time, timedelta
from typing import List, Dict, Optional
from pathlib import Path
import yaml

import yfinance as yf
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from loguru import logger
from prometheus_client import Counter, Histogram, Gauge

from .base import Collector


# Prometheus metrics
MARKET_BARS_FETCHED = Counter(
    'market_collector_bars_fetched_total',
    'Total market bars fetched',
    ['ticker', 'source']
)
MARKET_BARS_STORED = Counter(
    'market_collector_bars_stored_total',
    'Total market bars stored in database',
    ['ticker']
)
MARKET_FETCH_DURATION = Histogram(
    'market_collector_fetch_duration_seconds',
    'Time to fetch market data',
    ['ticker']
)
MARKET_FETCH_ERRORS = Counter(
    'market_collector_fetch_errors_total',
    'Total market data fetch errors',
    ['ticker', 'error_type']
)
MARKET_ACTIVE_TICKERS = Gauge(
    'market_collector_active_tickers',
    'Number of active tickers being monitored'
)


class MarketCollector(Collector):
    """
    Collector for market OHLCV data.
    
    Features:
    - Fetches 1-minute bars from yfinance (delayed ~15min)
    - Optional Polygon.io integration for real-time data
    - Configurable watchlist from YAML
    - Direct TimescaleDB storage
    - Market hours awareness (9:30-16:00 ET)
    - Prometheus metrics
    """
    
    def __init__(
        self,
        config_path: str = "config/market_watchlist.yaml",
        database_url: Optional[str] = None,
        polygon_api_key: Optional[str] = None,
        interval: str = "1m"
    ):
        """
        Initialize Market Data Collector.
        
        Args:
            config_path: Path to watchlist configuration file
            database_url: PostgreSQL connection string
            polygon_api_key: Polygon.io API key (optional)
            interval: Data interval (1m, 5m, 15m, etc.)
        """
        self.config_path = Path(config_path)
        self.database_url = database_url or os.getenv(
            'DATABASE_URL',
            'postgresql://trader:password@localhost:5432/trading'
        )
        self.polygon_api_key = polygon_api_key or os.getenv('POLYGON_API_KEY')
        self.interval = interval
        
        # Load configuration
        self.config = self._load_config()
        self.tickers = self._load_tickers()
        
        # Running state
        self._running = False
        
        logger.info(
            f"Market Collector initialized with {len(self.tickers)} tickers, "
            f"interval={self.interval}"
        )
        MARKET_ACTIVE_TICKERS.set(len(self.tickers))
    
    def _load_config(self) -> Dict:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded market config from {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {
                'collection': {'interval_seconds': 60, 'market_hours_only': True},
                'tickers': []
            }
    
    def _load_tickers(self) -> List[Dict]:
        """Extract tickers from configuration."""
        return self.config.get('tickers', [])
    
    def _is_market_hours(self) -> bool:
        """Check if current time is within market hours (ET)."""
        if not self.config.get('collection', {}).get('market_hours_only', True):
            return True
        
        now_utc = datetime.now(timezone.utc)
        # Convert to ET (UTC-5 or UTC-4 depending on DST)
        # Simplified: assume UTC-5 for now
        now_et = now_utc - timedelta(hours=5)
        current_time = now_et.time()
        
        market_open = time(9, 30)  # 9:30 AM ET
        market_close = time(16, 0)  # 4:00 PM ET
        
        # Check if weekday
        if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        
        return market_open <= current_time <= market_close
    
    async def collect(self) -> List[Dict]:
        """
        Collect market data for all tickers in watchlist.
        
        Returns:
            List of OHLCV data dictionaries
        """
        all_bars = []
        
        # Check market hours
        if not self._is_market_hours():
            logger.info("Outside market hours, skipping collection")
            return all_bars
        
        for ticker_config in self.tickers:
            symbol = ticker_config['symbol']
            
            try:
                with MARKET_FETCH_DURATION.labels(ticker=symbol).time():
                    # Fetch data using yfinance
                    bars = await self._fetch_yfinance(symbol)
                    
                    if bars:
                        all_bars.extend(bars)
                        MARKET_BARS_FETCHED.labels(
                            ticker=symbol,
                            source='yfinance'
                        ).inc(len(bars))
                        logger.debug(f"{symbol}: fetched {len(bars)} bars")
                    
            except Exception as e:
                logger.error(f"Error fetching {symbol}: {e}")
                MARKET_FETCH_ERRORS.labels(
                    ticker=symbol,
                    error_type=type(e).__name__
                ).inc()
                continue
        
        logger.info(f"Collected {len(all_bars)} total bars from {len(self.tickers)} tickers")
        return all_bars
    
    async def _fetch_yfinance(self, symbol: str) -> List[Dict]:
        """
        Fetch data from yfinance.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            List of OHLCV dictionaries
        """
        try:
            # Fetch last 1 day of 1-minute data
            ticker = yf.Ticker(symbol)
            df = await asyncio.to_thread(
                ticker.history,
                period='1d',
                interval=self.interval
            )
            
            if df.empty:
                return []
            
            # Convert to list of dicts
            bars = []
            for timestamp, row in df.iterrows():
                bar = {
                    'ticker': symbol,
                    'timestamp': timestamp.to_pydatetime().replace(tzinfo=timezone.utc),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': int(row['Volume'])
                }
                bars.append(bar)
            
            return bars
            
        except Exception as e:
            logger.error(f"yfinance fetch failed for {symbol}: {e}")
            return []
    
    async def _fetch_polygon(self, symbol: str) -> List[Dict]:
        """
        Fetch real-time data from Polygon.io (optional).
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            List of OHLCV dictionaries
        """
        if not self.polygon_api_key:
            return []
        
        # TODO: Implement Polygon.io integration
        # Requires polygon-api-client library
        logger.warning("Polygon.io integration not yet implemented")
        return []
    
    async def store_to_database(self, bars: List[Dict]) -> bool:
        """
        Store OHLCV data directly in TimescaleDB.
        
        Args:
            bars: List of OHLCV dictionaries
            
        Returns:
            True if successful, False otherwise
        """
        if not bars:
            return True
        
        try:
            # Connect to database
            conn = await asyncio.to_thread(
                psycopg2.connect,
                self.database_url
            )
            
            try:
                cursor = conn.cursor()
                
                # Prepare data for insertion
                values = [
                    (
                        bar['timestamp'],
                        bar['ticker'],
                        bar['open'],
                        bar['high'],
                        bar['low'],
                        bar['close'],
                        bar['volume']
                    )
                    for bar in bars
                ]
                
                # Insert with ON CONFLICT to handle duplicates
                insert_query = """
                    INSERT INTO ohlcv (time, ticker, open, high, low, close, volume)
                    VALUES %s
                    ON CONFLICT (time, ticker) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume
                """
                
                execute_values(cursor, insert_query, values)
                conn.commit()
                
                # Update metrics
                for bar in bars:
                    MARKET_BARS_STORED.labels(ticker=bar['ticker']).inc()
                
                logger.info(f"Stored {len(bars)} bars to TimescaleDB")
                return True
                
            finally:
                cursor.close()
                conn.close()
                
        except Exception as e:
            logger.error(f"Failed to store to database: {e}")
            return False
    
    async def publish_to_kafka(self, events) -> bool:
        """
        Market data goes directly to TimescaleDB, not Kafka.
        Implementing for Collector interface compatibility.
        """
        logger.warning("Market data is stored in TimescaleDB, not published to Kafka")
        return True
    
    async def archive_to_minio(self, events) -> bool:
        """
        Market data goes directly to TimescaleDB, not MinIO.
        Implementing for Collector interface compatibility.
        """
        logger.warning("Market data is stored in TimescaleDB, not archived to MinIO")
        return True
    
    async def run_once(self) -> Dict:
        """
        Run one complete collection cycle.
        
        Returns:
            Statistics dictionary with results
        """
        self.start()
        
        try:
            # Collect market data
            bars = await self.collect()
            
            # Store to database
            db_success = await self.store_to_database(bars)
            
            stats = {
                'collected': len(bars),
                'stored': len(bars) if db_success else 0,
                'errors': [] if db_success else ['Database storage failed']
            }
            
            return stats
            
        finally:
            self.stop()
    
    def start(self):
        """Mark collector as running."""
        self._running = True
        logger.info("Market Collector started")
    
    def stop(self):
        """Mark collector as stopped."""
        self._running = False
        logger.info("Market Collector stopped")
    
    def is_running(self) -> bool:
        """Check if collector is running."""
        return self._running
    
    async def run_scheduled(self, interval_seconds: int = 60):
        """
        Run collector on a schedule.
        
        Args:
            interval_seconds: Seconds between collections
        """
        logger.info(f"Starting scheduled collection every {interval_seconds}s")
        self.start()
        
        try:
            while self._running:
                # Check if market hours
                if self._is_market_hours():
                    stats = await self.run_once()
                    logger.info(f"Collection cycle complete: {stats}")
                else:
                    logger.debug("Outside market hours, sleeping")
                
                # Wait for next interval
                await asyncio.sleep(interval_seconds)
                
        except Exception as e:
            logger.error(f"Scheduled collection error: {e}")
        finally:
            self.stop()
