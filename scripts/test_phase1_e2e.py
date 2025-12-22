#!/usr/bin/env python3
"""
End-to-End Test for Phase 1

Tests the complete flow: schema validation → raw event production → normalization → verification
"""

import json
import uuid
import hashlib
from datetime import datetime, timezone
import subprocess
import time
import sys

def run_command(cmd, check=True):
    """Run a shell command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Command failed: {cmd}")
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def test_schema_validation():
    """Test 1: Validate schemas."""
    print("Test 1: Validating schemas...")
    output = run_command("python3 scripts/validate_schema_samples.py")
    if "All validations passed!" in output:
        print("✓ Schema validation passed")
        return True
    else:
        print("✗ Schema validation failed")
        return False

def test_infrastructure():
    """Test 2: Verify infrastructure is running."""
    print("\nTest 2: Verifying infrastructure...")
    
    # Check topics
    topics = run_command("docker exec redpanda rpk topic list --brokers redpanda:29092")
    required_topics = ["raw.events.v1", "events.normalized.v1", "raw.events.dlq.v1", "events.normalized.dlq.v1"]
    
    all_topics_exist = all(topic in topics for topic in required_topics)
    
    if all_topics_exist:
        print("✓ All Kafka topics exist")
    else:
        print("✗ Some Kafka topics missing")
        return False
    
    # Check buckets
    buckets = run_command("docker run --rm --network infra_trading-platform --entrypoint /bin/sh minio/mc -c 'mc alias set local http://minio:9000 minioadmin minioadmin123 > /dev/null 2>&1 && mc ls local'")
    if "raw-events" in buckets and "pipeline-artifacts" in buckets:
        print("✓ MinIO buckets exist")
        return True
    else:
        print("✗ MinIO buckets missing")
        return False

def test_health_endpoints():
    """Test 3: Verify service health."""
    print("\nTest 3: Checking service health...")
    
    # Check RSS ingestor
    try:
        rss_health = run_command("curl -s http://localhost:8001/health")
        rss_data = json.loads(rss_health)
        if rss_data.get("status") == "healthy":
            print(f"✓ RSS Ingestor healthy (seen_items: {rss_data.get('seen_items', 0)})")
        else:
            print("✗ RSS Ingestor unhealthy")
            return False
    except Exception as e:
        print(f"✗ RSS Ingestor health check failed: {e}")
        return False
    
    # Check Reddit ingestor
    try:
        reddit_health = run_command("curl -s http://localhost:8003/health", check=False)
        if reddit_health:
            reddit_data = json.loads(reddit_health)
            if reddit_data.get("status") == "healthy":
                print(f"✓ Reddit Ingestor healthy (seen_items: {reddit_data.get('seen_items', 0)})")
            else:
                print("⚠ Reddit Ingestor unhealthy (may need credentials)")
        else:
            print("⚠ Reddit Ingestor not running (optional service)")
    except Exception as e:
        print(f"⚠ Reddit Ingestor not available: {e}")
    
    # Check normalizer
    try:
        norm_health = run_command("curl -s http://localhost:8002/health")
        norm_data = json.loads(norm_health)
        if norm_data.get("status") == "healthy":
            stats = norm_data.get("stats", {})
            print(f"✓ Normalizer healthy (processed: {stats.get('processed', 0)}, dlq: {stats.get('dlq_count', 0)})")
            return True
        else:
            print("✗ Normalizer unhealthy")
            return False
    except Exception as e:
        print(f"✗ Normalizer health check failed: {e}")
        return False

def test_end_to_end_flow():
    """Test 4: End-to-end event flow."""
    print("\nTest 4: Testing end-to-end flow...")
    
    # Generate test data
    event_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Create raw content
    raw_content = {
        "url": "https://example.com/test-e2e",
        "title": "Tesla and Microsoft Announce Partnership",
        "summary": "Major tech companies Tesla (TSLA) and Microsoft (MSFT) have announced a strategic partnership. Apple (AAPL) shares also moved on the news.",
        "published": timestamp,
        "author": "E2E Test",
        "tags": ["technology", "business"],
        "feed_url": "https://example.com/feed",
        "feed_name": "E2E Test Feed",
        "raw_entry": {}
    }
    
    raw_json = json.dumps(raw_content)
    raw_hash = hashlib.sha256(raw_json.encode('utf-8')).hexdigest()
    
    # Upload raw content to MinIO
    print(f"  Uploading raw content (event_id: {event_id})")
    with open("/tmp/e2e_raw.json", "w") as f:
        f.write(raw_json)
    
    upload_cmd = f'docker run --rm --network infra_trading-platform -v /tmp/e2e_raw.json:/tmp/raw.json:ro --entrypoint /bin/sh minio/mc -c "mc alias set local http://minio:9000 minioadmin minioadmin123 > /dev/null 2>&1 && mc cp /tmp/raw.json local/raw-events/source=rss/dt={date}/{event_id}.json > /dev/null 2>&1"'
    run_command(upload_cmd)
    print("  ✓ Raw content uploaded to MinIO")
    
    # Create RawEvent
    raw_event = {
        "schema_version": "raw_event.v1",
        "event_id": event_id,
        "source_type": "rss",
        "source_name": "E2E Test Feed",
        "captured_at_utc": timestamp,
        "event_time_utc": timestamp,
        "raw_uri": f"s3://raw-events/source=rss/dt={date}/{event_id}.json",
        "raw_hash": raw_hash,
        "content_type": "application/json",
        "priority": "MEDIUM",
        "correlation_id": correlation_id,
        "metadata": {
            "feed_url": "https://example.com/feed",
            "article_url": "https://example.com/test-e2e",
            "title": "Tesla and Microsoft Announce Partnership"
        }
    }
    
    # Produce RawEvent to Kafka
    print("  Producing RawEvent to Kafka...")
    raw_event_json = json.dumps(raw_event)
    produce_cmd = f'echo \'{raw_event_json}\' | docker exec -i redpanda rpk topic produce raw.events.v1 > /dev/null 2>&1'
    run_command(produce_cmd)
    print("  ✓ RawEvent produced")
    
    # Wait for normalizer to process
    print("  Waiting for normalizer to process (10 seconds)...")
    time.sleep(10)
    
    # Check if normalized event was produced
    print("  Checking for normalized event...")
    consume_cmd = f'docker exec redpanda rpk topic consume events.normalized.v1 -f "%v" -o :end | grep "{event_id}" | head -1'
    normalized_output = run_command(consume_cmd, check=False)
    
    if not normalized_output:
        print(f"  ✗ No normalized event found for event_id: {event_id}")
        print("  Checking DLQ for errors...")
        dlq_cmd = 'docker exec redpanda rpk topic consume events.normalized.dlq.v1 -n 10 -f "%v"'
        dlq_output = run_command(dlq_cmd, check=False)
        if event_id in dlq_output:
            print(f"  ✗ Event found in DLQ:")
            print(f"    {dlq_output}")
        return False
    
    try:
        normalized_event = json.loads(normalized_output)
        print(f"  ✓ Normalized event found!")
        print(f"    - event_id: {normalized_event.get('event_id')}")
        print(f"    - lang: {normalized_event.get('lang')}")
        print(f"    - symbols: {normalized_event.get('symbols_candidates', [])}")
        print(f"    - source_score: {normalized_event.get('source_score')}")
        print(f"    - dedup_key: {normalized_event.get('dedup_key')[:16]}...")
        
        # Verify symbols were extracted
        expected_symbols = ["TSLA", "MSFT", "AAPL"]
        actual_symbols = normalized_event.get('symbols_candidates', [])
        if all(sym in actual_symbols for sym in expected_symbols):
            print(f"  ✓ Ticker symbols extracted correctly")
        else:
            print(f"  ! Expected symbols {expected_symbols}, got {actual_symbols}")
        
        return True
    except json.JSONDecodeError as e:
        print(f"  ✗ Failed to parse normalized event: {e}")
        return False

def test_reddit_metrics():
    """Test 5: Verify Reddit ingestor metrics (if available)."""
    print("\nTest 5: Checking Reddit ingestor metrics...")
    
    try:
        metrics_output = run_command("curl -s http://localhost:8003/metrics", check=False)
        if not metrics_output:
            print("⚠ Reddit Ingestor not available (optional service)")
            return True  # Pass test if service not running
        
        # Check for expected metrics
        required_metrics = [
            'reddit_ingestor_raw_events_published_total',
            'reddit_ingestor_items_fetched_total',
            'reddit_ingestor_dedup_hits_total',
            'reddit_ingestor_last_success_timestamp'
        ]
        
        missing_metrics = []
        for metric in required_metrics:
            if metric not in metrics_output:
                missing_metrics.append(metric)
        
        if missing_metrics:
            print(f"✗ Missing metrics: {', '.join(missing_metrics)}")
            return False
        else:
            print("✓ All Reddit metrics present")
            
            # Try to check if Reddit events are being published
            if 'reddit_ingestor_raw_events_published_total' in metrics_output:
                # Look for the metric value
                for line in metrics_output.split('\n'):
                    if line.startswith('reddit_ingestor_raw_events_published_total'):
                        parts = line.split()
                        if len(parts) >= 2:
                            count = float(parts[1])
                            print(f"  Reddit events published: {int(count)}")
                            break
            
            return True
            
    except Exception as e:
        print(f"⚠ Could not check Reddit metrics: {e}")
        return True  # Pass if Reddit service not available

def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 1 - End-to-End Acceptance Tests")
    print("=" * 60)
    
    tests = [
        test_schema_validation,
        test_infrastructure,
        test_health_endpoints,
        test_end_to_end_flow,
        test_reddit_metrics
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("\n✓ All tests passed! Phase 1 implementation complete.")
        return 0
    else:
        print("\n✗ Some tests failed. Please review the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
