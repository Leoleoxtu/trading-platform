#!/usr/bin/env python3
"""
Market Ingestor Smoke Test

Tests the market ingestor service for basic functionality:
- TimescaleDB connectivity
- Market data ingestion
- Metrics exposure
- Health endpoint
"""

import json
import sys
import subprocess
import time
import psycopg2
from datetime import datetime


def run_command(cmd, check=True):
    """Run a shell command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Command failed: {cmd}")
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()


def test_timescaledb_accessible():
    """Test 1: Verify TimescaleDB is accessible."""
    print("Test 1: Verifying TimescaleDB accessibility...")
    
    try:
        # Try to connect to TimescaleDB
        conn = psycopg2.connect(
            host='localhost',
            port=5432,
            dbname='market',
            user='market',
            password='market_secret_change_me',
            connect_timeout=10
        )
        
        with conn.cursor() as cur:
            # Check if timescale extension is loaded
            cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';")
            result = cur.fetchone()
            
            if result:
                print(f"  ✓ TimescaleDB extension loaded (version: {result[1]})")
            else:
                print("  ✗ TimescaleDB extension not found")
                conn.close()
                return False
            
            # Check if ohlcv table exists
            cur.execute("""
                SELECT tablename FROM pg_tables 
                WHERE schemaname = 'public' AND tablename = 'ohlcv';
            """)
            result = cur.fetchone()
            
            if result:
                print(f"  ✓ OHLCV table exists")
            else:
                print("  ✗ OHLCV table not found")
                conn.close()
                return False
            
            # Check if it's a hypertable
            cur.execute("""
                SELECT hypertable_name FROM timescaledb_information.hypertables 
                WHERE hypertable_name = 'ohlcv';
            """)
            result = cur.fetchone()
            
            if result:
                print(f"  ✓ OHLCV is a hypertable")
            else:
                print("  ⚠ OHLCV is not a hypertable")
        
        conn.close()
        print("✓ TimescaleDB is accessible and configured\n")
        return True
        
    except Exception as e:
        print(f"✗ Failed to connect to TimescaleDB: {e}\n")
        return False


def test_market_ingestor_health():
    """Test 2: Verify market ingestor health endpoint."""
    print("Test 2: Checking market ingestor health...")
    
    try:
        health_output = run_command("curl -s http://localhost:8004/health")
        health_data = json.loads(health_output)
        
        if health_data.get('status') == 'healthy':
            print(f"  ✓ Market ingestor is healthy")
            print(f"    Tickers: {', '.join(health_data.get('tickers', []))}")
            print(f"    Timeframes: {', '.join(health_data.get('timeframes', []))}")
            print(f"    Adjusted: {health_data.get('adjusted')}")
            
            recent = health_data.get('recent_data', {})
            if recent:
                print(f"    Recent tickers updated: {recent.get('tickers_updated', 0)}")
                print(f"    Recent timeframes updated: {recent.get('timeframes_updated', 0)}")
                if recent.get('latest_candle'):
                    print(f"    Latest candle: {recent.get('latest_candle')}")
            
            print("✓ Market ingestor health check passed\n")
            return True
        else:
            print(f"  ✗ Market ingestor is unhealthy: {health_data}")
            print("✗ Market ingestor health check failed\n")
            return False
            
    except Exception as e:
        print(f"✗ Failed to check market ingestor health: {e}\n")
        return False


def test_metrics_exposed():
    """Test 3: Verify Prometheus metrics are exposed."""
    print("Test 3: Checking Prometheus metrics...")
    
    try:
        metrics_output = run_command("curl -s http://localhost:8004/metrics")
        
        required_metrics = [
            'market_ingestor_candles_upserted_total',
            'market_ingestor_fetch_failed_total',
            'market_ingestor_missing_candles_detected_total',
            'market_ingestor_fetch_duration_seconds',
            'market_ingestor_db_upsert_duration_seconds',
            'market_ingestor_last_success_timestamp',
            'market_ingestor_last_candle_timestamp'
        ]
        
        missing_metrics = []
        for metric in required_metrics:
            if metric not in metrics_output:
                missing_metrics.append(metric)
        
        if missing_metrics:
            print(f"  ✗ Missing metrics: {', '.join(missing_metrics)}")
            print("✗ Metrics check failed\n")
            return False
        else:
            print(f"  ✓ All required metrics present ({len(required_metrics)} metrics)")
            
            # Try to extract some metric values
            for line in metrics_output.split('\n'):
                if line.startswith('market_ingestor_candles_upserted_total'):
                    print(f"    {line}")
                    break
            
            for line in metrics_output.split('\n'):
                if line.startswith('market_ingestor_last_success_timestamp') and not line.startswith('#'):
                    parts = line.split()
                    if len(parts) >= 2:
                        timestamp = float(parts[1])
                        dt = datetime.fromtimestamp(timestamp)
                        print(f"    Last success: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                    break
            
            print("✓ Metrics exposure check passed\n")
            return True
            
    except Exception as e:
        print(f"✗ Failed to check metrics: {e}\n")
        return False


def test_ohlcv_data_present():
    """Test 4: Verify OHLCV data is being ingested."""
    print("Test 4: Checking for OHLCV data in database...")
    
    try:
        conn = psycopg2.connect(
            host='localhost',
            port=5432,
            dbname='market',
            user='market',
            password='market_secret_change_me',
            connect_timeout=10
        )
        
        with conn.cursor() as cur:
            # Check total rows
            cur.execute("SELECT COUNT(*) FROM ohlcv;")
            total_rows = cur.fetchone()[0]
            
            if total_rows == 0:
                print("  ⚠ No OHLCV data found yet (service may still be fetching)")
                print("  Waiting for data ingestion with retries (up to 2 minutes)...")
                
                # Retry up to 4 times with 30-second intervals
                for attempt in range(4):
                    time.sleep(30)
                    cur.execute("SELECT COUNT(*) FROM ohlcv;")
                    total_rows = cur.fetchone()[0]
                    
                    if total_rows > 0:
                        print(f"  ✓ Data found after {(attempt + 1) * 30} seconds")
                        break
                    else:
                        print(f"  ⚠ No data yet (attempt {attempt + 1}/4)")
                
                if total_rows == 0:
                    print("  ✗ Still no data after waiting 2 minutes")
                    print("  Note: This may be normal if Yahoo Finance is not accessible")
                    conn.close()
                    return False
            
            print(f"  ✓ Total candles in database: {total_rows}")
            
            # Check distinct tickers
            cur.execute("SELECT DISTINCT instrument_id FROM ohlcv ORDER BY instrument_id;")
            tickers = [row[0] for row in cur.fetchall()]
            print(f"  ✓ Tickers present: {', '.join(tickers)}")
            
            # Check distinct timeframes
            cur.execute("SELECT DISTINCT timeframe FROM ohlcv ORDER BY timeframe;")
            timeframes = [row[0] for row in cur.fetchall()]
            print(f"  ✓ Timeframes present: {', '.join(timeframes)}")
            
            # Check latest candle per timeframe
            cur.execute("""
                SELECT timeframe, MAX(ts) as latest_ts, COUNT(*) as count
                FROM ohlcv
                GROUP BY timeframe
                ORDER BY timeframe;
            """)
            
            print(f"  ✓ Latest candles by timeframe:")
            for row in cur.fetchall():
                timeframe, latest_ts, count = row
                print(f"    {timeframe}: {latest_ts.strftime('%Y-%m-%d %H:%M:%S %Z')} ({count} candles)")
            
            # Sample a few candles
            cur.execute("""
                SELECT instrument_id, timeframe, ts, open, high, low, close, volume
                FROM ohlcv
                ORDER BY ingested_at DESC
                LIMIT 3;
            """)
            
            print(f"  ✓ Sample recent candles:")
            for row in cur.fetchall():
                ticker, tf, ts, o, h, l, c, v = row
                print(f"    {ticker} {tf} @ {ts.strftime('%Y-%m-%d %H:%M')}: O={o:.2f} H={h:.2f} L={l:.2f} C={c:.2f} V={v:.0f}")
        
        conn.close()
        print("✓ OHLCV data ingestion verified\n")
        return True
        
    except Exception as e:
        print(f"✗ Failed to check OHLCV data: {e}\n")
        return False


def test_data_quality():
    """Test 5: Basic data quality checks."""
    print("Test 5: Running data quality checks...")
    
    try:
        conn = psycopg2.connect(
            host='localhost',
            port=5432,
            dbname='market',
            user='market',
            password='market_secret_change_me',
            connect_timeout=10
        )
        
        with conn.cursor() as cur:
            # Check for NULL values in critical columns
            cur.execute("""
                SELECT COUNT(*) FROM ohlcv 
                WHERE open IS NULL OR high IS NULL OR low IS NULL 
                   OR close IS NULL OR volume IS NULL OR ts IS NULL;
            """)
            null_count = cur.fetchone()[0]
            
            if null_count > 0:
                print(f"  ✗ Found {null_count} rows with NULL values in critical columns")
                conn.close()
                return False
            else:
                print(f"  ✓ No NULL values in critical columns")
            
            # Check for invalid OHLC relationships (high >= low, etc.)
            cur.execute("""
                SELECT COUNT(*) FROM ohlcv 
                WHERE high < low OR high < open OR high < close 
                   OR low > open OR low > close;
            """)
            invalid_count = cur.fetchone()[0]
            
            if invalid_count > 0:
                print(f"  ⚠ Found {invalid_count} rows with invalid OHLC relationships")
            else:
                print(f"  ✓ All OHLC relationships are valid")
            
            # Check for duplicate candles (should be prevented by unique constraint)
            cur.execute("""
                SELECT instrument_id, timeframe, ts, COUNT(*) as dup_count
                FROM ohlcv
                GROUP BY instrument_id, timeframe, ts
                HAVING COUNT(*) > 1;
            """)
            duplicates = cur.fetchall()
            
            if duplicates:
                print(f"  ✗ Found {len(duplicates)} duplicate candles")
                for dup in duplicates[:3]:
                    print(f"    {dup[0]} {dup[1]} @ {dup[2]}: {dup[3]} duplicates")
                conn.close()
                return False
            else:
                print(f"  ✓ No duplicate candles found")
            
            # Check timestamp timezone (should all be UTC)
            cur.execute("""
                SELECT ts FROM ohlcv 
                WHERE EXTRACT(TIMEZONE FROM ts) != 0
                LIMIT 1;
            """)
            non_utc = cur.fetchone()
            
            if non_utc:
                print(f"  ⚠ Found non-UTC timestamps")
            else:
                print(f"  ✓ All timestamps are in UTC")
        
        conn.close()
        print("✓ Data quality checks passed\n")
        return True
        
    except Exception as e:
        print(f"✗ Failed data quality checks: {e}\n")
        return False


def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("Market Ingestor - Smoke Tests")
    print("=" * 60)
    print()
    
    tests = [
        test_timescaledb_accessible,
        test_market_ingestor_health,
        test_metrics_exposed,
        test_ohlcv_data_present,
        test_data_quality
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test failed with exception: {e}\n")
            results.append(False)
    
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("\n✓ All smoke tests passed! Market ingestor is working correctly.")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
