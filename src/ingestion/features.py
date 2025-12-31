"""
Feature Calculator - Calculates technical indicators from OHLCV data.

Computes VWAP, RSI, MACD, Bollinger Bands, and ATR indicators.
Stores calculated features in TimescaleDB for downstream ML/strategy use.
"""

import asyncio
import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
from loguru import logger
from prometheus_client import Counter, Histogram


# Prometheus metrics
FEATURES_CALCULATED = Counter(
    'features_calculator_calculated_total',
    'Total features calculated',
    ['ticker', 'indicator']
)
FEATURES_STORED = Counter(
    'features_calculator_stored_total',
    'Total features stored in database',
    ['ticker']
)
FEATURE_CALC_DURATION = Histogram(
    'features_calculator_duration_seconds',
    'Time to calculate features',
    ['ticker']
)
FEATURE_CALC_ERRORS = Counter(
    'features_calculator_errors_total',
    'Total feature calculation errors',
    ['ticker', 'error_type']
)


class FeatureCalculator:
    """
    Calculator for technical indicators and features.
    
    Features:
    - VWAP (1h, 1d)
    - RSI (14 periods)
    - MACD (12, 26, 9)
    - Bollinger Bands (20, 2)
    - ATR (Average True Range, 14 periods)
    """
    
    def __init__(
        self,
        database_url: Optional[str] = None,
        lookback_days: int = 90
    ):
        """
        Initialize Feature Calculator.
        
        Args:
            database_url: PostgreSQL connection string
            lookback_days: Days of historical data to load for calculations
        """
        self.database_url = database_url or os.getenv(
            'DATABASE_URL',
            'postgresql://trader:password@localhost:5432/trading'
        )
        self.lookback_days = lookback_days
        
        logger.info(f"Feature Calculator initialized with {lookback_days}d lookback")
    
    async def load_ohlcv_data(self, ticker: str, days: int = None) -> pd.DataFrame:
        """
        Load OHLCV data from TimescaleDB.
        
        Args:
            ticker: Stock ticker symbol
            days: Number of days to load (default: self.lookback_days)
            
        Returns:
            DataFrame with OHLCV data
        """
        days = days or self.lookback_days
        
        try:
            conn = await asyncio.to_thread(
                psycopg2.connect,
                self.database_url
            )
            
            try:
                query = """
                    SELECT time, ticker, open, high, low, close, volume
                    FROM ohlcv
                    WHERE ticker = %s
                      AND time >= NOW() - INTERVAL '%s days'
                    ORDER BY time ASC
                """
                
                df = await asyncio.to_thread(
                    pd.read_sql_query,
                    query,
                    conn,
                    params=(ticker, days)
                )
                
                if not df.empty:
                    df['time'] = pd.to_datetime(df['time'])
                    df.set_index('time', inplace=True)
                
                logger.debug(f"Loaded {len(df)} rows for {ticker}")
                return df
                
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Failed to load OHLCV data for {ticker}: {e}")
            return pd.DataFrame()
    
    def calculate_vwap(self, df: pd.DataFrame, period: str = '1h') -> pd.Series:
        """
        Calculate Volume Weighted Average Price.
        
        Args:
            df: DataFrame with OHLCV data
            period: Resampling period ('1h', '1d')
            
        Returns:
            Series with VWAP values
        """
        try:
            # Calculate typical price
            df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
            df['tp_volume'] = df['typical_price'] * df['volume']
            
            # Resample and calculate VWAP
            resampled = df.resample(period).agg({
                'tp_volume': 'sum',
                'volume': 'sum'
            })
            
            vwap = resampled['tp_volume'] / resampled['volume']
            
            # Forward fill to match original index
            vwap = vwap.reindex(df.index, method='ffill')
            
            return vwap
            
        except Exception as e:
            logger.error(f"VWAP calculation error: {e}")
            return pd.Series(index=df.index, dtype=float)
    
    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate Relative Strength Index.
        
        Args:
            df: DataFrame with OHLCV data
            period: RSI period (default: 14)
            
        Returns:
            Series with RSI values
        """
        try:
            close = df['close']
            delta = close.diff()
            
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
            
        except Exception as e:
            logger.error(f"RSI calculation error: {e}")
            return pd.Series(index=df.index, dtype=float)
    
    def calculate_macd(
        self,
        df: pd.DataFrame,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Dict[str, pd.Series]:
        """
        Calculate MACD (Moving Average Convergence Divergence).
        
        Args:
            df: DataFrame with OHLCV data
            fast: Fast EMA period (default: 12)
            slow: Slow EMA period (default: 26)
            signal: Signal line period (default: 9)
            
        Returns:
            Dictionary with 'macd', 'signal', 'histogram' Series
        """
        try:
            close = df['close']
            
            ema_fast = close.ewm(span=fast, adjust=False).mean()
            ema_slow = close.ewm(span=slow, adjust=False).mean()
            
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=signal, adjust=False).mean()
            histogram = macd_line - signal_line
            
            return {
                'macd': macd_line,
                'signal': signal_line,
                'histogram': histogram
            }
            
        except Exception as e:
            logger.error(f"MACD calculation error: {e}")
            return {
                'macd': pd.Series(index=df.index, dtype=float),
                'signal': pd.Series(index=df.index, dtype=float),
                'histogram': pd.Series(index=df.index, dtype=float)
            }
    
    def calculate_bollinger_bands(
        self,
        df: pd.DataFrame,
        period: int = 20,
        std_dev: float = 2.0
    ) -> Dict[str, pd.Series]:
        """
        Calculate Bollinger Bands.
        
        Args:
            df: DataFrame with OHLCV data
            period: Moving average period (default: 20)
            std_dev: Standard deviation multiplier (default: 2.0)
            
        Returns:
            Dictionary with 'upper', 'middle', 'lower' Series
        """
        try:
            close = df['close']
            
            middle = close.rolling(window=period).mean()
            std = close.rolling(window=period).std()
            
            upper = middle + (std * std_dev)
            lower = middle - (std * std_dev)
            
            return {
                'upper': upper,
                'middle': middle,
                'lower': lower
            }
            
        except Exception as e:
            logger.error(f"Bollinger Bands calculation error: {e}")
            return {
                'upper': pd.Series(index=df.index, dtype=float),
                'middle': pd.Series(index=df.index, dtype=float),
                'lower': pd.Series(index=df.index, dtype=float)
            }
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate Average True Range.
        
        Args:
            df: DataFrame with OHLCV data
            period: ATR period (default: 14)
            
        Returns:
            Series with ATR values
        """
        try:
            high = df['high']
            low = df['low']
            close = df['close']
            
            # True Range components
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            
            # True Range
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            # Average True Range
            atr = tr.rolling(window=period).mean()
            
            return atr
            
        except Exception as e:
            logger.error(f"ATR calculation error: {e}")
            return pd.Series(index=df.index, dtype=float)
    
    async def calculate_all_features(self, ticker: str) -> pd.DataFrame:
        """
        Calculate all features for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            DataFrame with all calculated features
        """
        try:
            with FEATURE_CALC_DURATION.labels(ticker=ticker).time():
                # Load OHLCV data
                df = await self.load_ohlcv_data(ticker)
                
                if df.empty:
                    logger.warning(f"No data available for {ticker}")
                    return pd.DataFrame()
                
                # Calculate features
                features_df = pd.DataFrame(index=df.index)
                features_df['ticker'] = ticker
                
                # VWAP
                features_df['vwap_1h'] = self.calculate_vwap(df, '1h')
                features_df['vwap_1d'] = self.calculate_vwap(df, '1d')
                FEATURES_CALCULATED.labels(ticker=ticker, indicator='vwap').inc(2)
                
                # RSI
                features_df['rsi_14'] = self.calculate_rsi(df, 14)
                FEATURES_CALCULATED.labels(ticker=ticker, indicator='rsi').inc()
                
                # MACD
                macd = self.calculate_macd(df)
                features_df['macd'] = macd['macd']
                features_df['macd_signal'] = macd['signal']
                features_df['macd_histogram'] = macd['histogram']
                FEATURES_CALCULATED.labels(ticker=ticker, indicator='macd').inc(3)
                
                # Bollinger Bands
                bb = self.calculate_bollinger_bands(df)
                features_df['bb_upper'] = bb['upper']
                features_df['bb_middle'] = bb['middle']
                features_df['bb_lower'] = bb['lower']
                FEATURES_CALCULATED.labels(ticker=ticker, indicator='bollinger').inc(3)
                
                # ATR
                features_df['atr_14'] = self.calculate_atr(df, 14)
                FEATURES_CALCULATED.labels(ticker=ticker, indicator='atr').inc()
                
                logger.info(f"Calculated {len(features_df.columns)-1} features for {ticker}")
                return features_df
                
        except Exception as e:
            logger.error(f"Feature calculation failed for {ticker}: {e}")
            FEATURE_CALC_ERRORS.labels(
                ticker=ticker,
                error_type=type(e).__name__
            ).inc()
            return pd.DataFrame()
    
    async def store_features(self, features_df: pd.DataFrame) -> bool:
        """
        Store calculated features in TimescaleDB.
        
        Args:
            features_df: DataFrame with calculated features
            
        Returns:
            True if successful, False otherwise
        """
        if features_df.empty:
            return True
        
        try:
            conn = await asyncio.to_thread(
                psycopg2.connect,
                self.database_url
            )
            
            try:
                cursor = conn.cursor()
                
                # Prepare data for insertion
                values = []
                for timestamp, row in features_df.iterrows():
                    values.append((
                        timestamp,
                        row['ticker'],
                        float(row['vwap_1h']) if pd.notna(row['vwap_1h']) else None,
                        float(row['vwap_1d']) if pd.notna(row['vwap_1d']) else None,
                        float(row['rsi_14']) if pd.notna(row['rsi_14']) else None,
                        float(row['macd']) if pd.notna(row['macd']) else None,
                        float(row['macd_signal']) if pd.notna(row['macd_signal']) else None,
                        float(row['macd_histogram']) if pd.notna(row['macd_histogram']) else None,
                        float(row['bb_upper']) if pd.notna(row['bb_upper']) else None,
                        float(row['bb_middle']) if pd.notna(row['bb_middle']) else None,
                        float(row['bb_lower']) if pd.notna(row['bb_lower']) else None,
                        float(row['atr_14']) if pd.notna(row['atr_14']) else None
                    ))
                
                # Insert with ON CONFLICT to handle duplicates
                insert_query = """
                    INSERT INTO features (
                        time, ticker,
                        vwap_1h, vwap_1d,
                        rsi_14,
                        macd, macd_signal, macd_histogram,
                        bb_upper, bb_middle, bb_lower,
                        atr_14
                    )
                    VALUES %s
                    ON CONFLICT (time, ticker) DO UPDATE SET
                        vwap_1h = EXCLUDED.vwap_1h,
                        vwap_1d = EXCLUDED.vwap_1d,
                        rsi_14 = EXCLUDED.rsi_14,
                        macd = EXCLUDED.macd,
                        macd_signal = EXCLUDED.macd_signal,
                        macd_histogram = EXCLUDED.macd_histogram,
                        bb_upper = EXCLUDED.bb_upper,
                        bb_middle = EXCLUDED.bb_middle,
                        bb_lower = EXCLUDED.bb_lower,
                        atr_14 = EXCLUDED.atr_14
                """
                
                execute_values(cursor, insert_query, values)
                conn.commit()
                
                ticker = features_df['ticker'].iloc[0]
                FEATURES_STORED.labels(ticker=ticker).inc(len(values))
                
                logger.info(f"Stored {len(values)} feature rows to TimescaleDB")
                return True
                
            finally:
                cursor.close()
                conn.close()
                
        except Exception as e:
            logger.error(f"Failed to store features: {e}")
            return False
    
    async def calculate_and_store(self, ticker: str) -> Dict:
        """
        Calculate and store features for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Statistics dictionary
        """
        try:
            # Calculate features
            features_df = await self.calculate_all_features(ticker)
            
            if features_df.empty:
                return {
                    'ticker': ticker,
                    'calculated': 0,
                    'stored': 0,
                    'errors': ['No data available']
                }
            
            # Store features
            success = await self.store_features(features_df)
            
            return {
                'ticker': ticker,
                'calculated': len(features_df),
                'stored': len(features_df) if success else 0,
                'errors': [] if success else ['Storage failed']
            }
            
        except Exception as e:
            logger.error(f"Calculate and store failed for {ticker}: {e}")
            return {
                'ticker': ticker,
                'calculated': 0,
                'stored': 0,
                'errors': [str(e)]
            }
    
    async def process_watchlist(self, tickers: List[str]) -> List[Dict]:
        """
        Process features for multiple tickers.
        
        Args:
            tickers: List of ticker symbols
            
        Returns:
            List of statistics dictionaries
        """
        results = []
        
        for ticker in tickers:
            result = await self.calculate_and_store(ticker)
            results.append(result)
        
        return results
