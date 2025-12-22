#!/usr/bin/env python3
"""
Feature Store Smoke Test

Tests the feature store service by:
1. Verifying TimescaleDB is accessible
2. Checking OHLCV data exists
3. Simulating enriched events via Kafka
4. Waiting for feature computation
5. Verifying feature vectors in database
"""

import os
import sys
import json
import time
import uuid
from datetime import datetime, timezone, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor
from kafka import KafkaProducer
from kafka.errors import KafkaError
import requests

# Configuration
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'market')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'market')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'market_secret_change_me')

KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
ENRICHED_TOPIC = 'events.enriched.v1'

FEATURE_STORE_URL = os.getenv('FEATURE_STORE_URL', 'http://localhost:8006')
FEATURE_SET_VERSION = os.getenv('FEATURE_SET_VERSION', 'fs_v1')

TEST_TICKER = 'AAPL'
TEST_TIMEFRAME = '1d'


def get_db_connection():
    """Get PostgreSQL connection."""
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )


def test_db_connection():
    """Test 1: Verify TimescaleDB is accessible."""
    print("Test 1: Verifying TimescaleDB connection...")
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            print(f"  ✓ Connected to: {version}")
        conn.close()
        return True
    except Exception as e:
        print(f"  ✗ Failed to connect: {e}")
        return False


def test_ohlcv_data():
    """Test 2: Check OHLCV data exists for test ticker."""
    print(f"\nTest 2: Checking OHLCV data for {TEST_TICKER}/{TEST_TIMEFRAME}...")
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT COUNT(*) as count FROM ohlcv WHERE instrument_id = %s AND timeframe = %s",
                (TEST_TICKER, TEST_TIMEFRAME)
            )
            result = cur.fetchone()
            count = result['count']
            
            if count > 0:
                print(f"  ✓ Found {count} OHLCV candles")
                
                # Get latest candle
                cur.execute(
                    "SELECT ts, close FROM ohlcv WHERE instrument_id = %s AND timeframe = %s ORDER BY ts DESC LIMIT 1",
                    (TEST_TICKER, TEST_TIMEFRAME)
                )
                latest = cur.fetchone()
                print(f"  ✓ Latest candle: {latest['ts']}, close={latest['close']}")
                conn.close()
                return True
            else:
                print(f"  ✗ No OHLCV data found")
                conn.close()
                return False
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def test_feature_vectors_table():
    """Test 2.5: Verify feature_vectors table exists."""
    print("\nTest 2.5: Checking feature_vectors table...")
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'feature_vectors'
            """)
            result = cur.fetchone()
            
            if result:
                print("  ✓ feature_vectors table exists")
                
                # Check structure
                cur.execute("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'feature_vectors'
                    ORDER BY ordinal_position
                """)
                columns = cur.fetchall()
                print(f"  ✓ Table has {len(columns)} columns")
                conn.close()
                return True
            else:
                print("  ✗ feature_vectors table not found")
                conn.close()
                return False
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def simulate_enriched_events():
    """Test 3: Publish test enriched events to Kafka."""
    print(f"\nTest 3: Publishing test enriched events for {TEST_TICKER}...")
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        now = datetime.now(timezone.utc)
        events_published = 0
        
        # Create 3 test events
        for i in range(3):
            event = {
                "schema_version": "enriched_event.v1",
                "event_id": str(uuid.uuid4()),
                "enriched_at_utc": (now - timedelta(minutes=30-i*10)).isoformat(),
                "pipeline_version": "test-smoke",
                "source_type": "test",
                "source_name": "smoke-test",
                "lang": "en",
                "normalized_text_hash": "a" * 64,
                "entities": [],
                "tickers": [
                    {
                        "symbol": TEST_TICKER,
                        "confidence": 0.95,
                        "method": "validated"
                    }
                ],
                "sentiment": {
                    "score": 0.2 + (i * 0.1),
                    "confidence": 0.85 + (i * 0.05),
                    "model": "test"
                },
                "event_category": "market",
                "quality_flags": []
            }
            
            future = producer.send(ENRICHED_TOPIC, value=event)
            future.get(timeout=10)
            events_published += 1
        
        producer.flush()
        producer.close()
        
        print(f"  ✓ Published {events_published} test events")
        return True
        
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def test_health_endpoint():
    """Test 4: Check feature store health endpoint."""
    print(f"\nTest 4: Checking feature store health endpoint...")
    try:
        response = requests.get(f"{FEATURE_STORE_URL}/health", timeout=5)
        
        if response.status_code == 200:
            health = response.json()
            print(f"  ✓ Health check passed")
            print(f"    Status: {health.get('status')}")
            print(f"    Cached events: {health.get('cached_events')}")
            print(f"    Feature set version: {health.get('feature_set_version')}")
            return True
        else:
            print(f"  ✗ Health check failed: status {response.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def wait_for_computation(max_wait_seconds=120):
    """Test 5: Wait for feature computation to complete."""
    print(f"\nTest 5: Waiting for feature computation (max {max_wait_seconds}s)...")
    
    start_time = time.time()
    
    while time.time() - start_time < max_wait_seconds:
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT COUNT(*) as count 
                    FROM feature_vectors 
                    WHERE instrument_id = %s 
                    AND timeframe = %s 
                    AND feature_set_version = %s
                    AND computed_at > NOW() - INTERVAL '5 minutes'
                """, (TEST_TICKER, TEST_TIMEFRAME, FEATURE_SET_VERSION))
                
                result = cur.fetchone()
                count = result['count']
                
                if count > 0:
                    print(f"  ✓ Found {count} recent feature vector(s)")
                    conn.close()
                    return True
            
            conn.close()
            
        except Exception as e:
            print(f"  ! Error checking: {e}")
        
        time.sleep(5)
        print(f"  ... waiting ({int(time.time() - start_time)}s elapsed)")
    
    print(f"  ✗ Timeout: no features computed in {max_wait_seconds}s")
    return False


def verify_feature_content():
    """Test 6: Verify feature vector content."""
    print(f"\nTest 6: Verifying feature vector content...")
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    instrument_id,
                    timeframe,
                    ts,
                    feature_set_version,
                    features,
                    quality_flags,
                    event_count,
                    computed_at
                FROM feature_vectors
                WHERE instrument_id = %s 
                AND timeframe = %s 
                AND feature_set_version = %s
                ORDER BY ts DESC
                LIMIT 1
            """, (TEST_TICKER, TEST_TIMEFRAME, FEATURE_SET_VERSION))
            
            vector = cur.fetchone()
            
            if not vector:
                print("  ✗ No feature vector found")
                conn.close()
                return False
            
            print(f"  ✓ Feature vector found:")
            print(f"    Timestamp: {vector['ts']}")
            print(f"    Computed at: {vector['computed_at']}")
            print(f"    Event count: {vector['event_count']}")
            print(f"    Quality flags: {vector['quality_flags']}")
            
            features = vector['features']
            print(f"    Features ({len(features)} total):")
            
            # Check required features
            required_features = ['ret_1', 'sentiment_mean_1h']
            missing = []
            
            for feat in required_features:
                if feat in features:
                    print(f"      ✓ {feat}: {features[feat]}")
                else:
                    missing.append(feat)
                    print(f"      ✗ {feat}: MISSING")
            
            # Show other features
            for feat, value in features.items():
                if feat not in required_features:
                    print(f"      • {feat}: {value}")
            
            conn.close()
            
            if missing:
                print(f"  ✗ Missing required features: {missing}")
                return False
            else:
                print("  ✓ All required features present")
                return True
                
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("Feature Store Smoke Test")
    print("=" * 60)
    
    tests = [
        ("DB Connection", test_db_connection),
        ("OHLCV Data", test_ohlcv_data),
        ("Feature Vectors Table", test_feature_vectors_table),
        ("Simulate Events", simulate_enriched_events),
        ("Health Endpoint", test_health_endpoint),
        ("Wait for Computation", lambda: wait_for_computation(120)),
        ("Verify Features", verify_feature_content)
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\nTest '{name}' raised exception: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
    
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    
    print(f"\n{passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
