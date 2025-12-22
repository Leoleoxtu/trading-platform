#!/usr/bin/env python3
"""
End-to-End Test for NLP Enrichment Service

Tests the complete enrichment flow:
1. Schema validation
2. Service health check
3. Produce normalized event
4. Consume enriched event
5. Validate enriched event schema
6. Check MinIO audit trail
7. Verify Prometheus metrics
"""

import json
import uuid
import hashlib
import time
import sys
import subprocess
from datetime import datetime, timezone
from typing import Optional


def run_command(cmd: str, check: bool = True) -> str:
    """Run a shell command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"❌ Command failed: {cmd}")
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()


def test_schema_validation():
    """Test 1: Validate enriched event schema."""
    print("\n📋 Test 1: Validating enriched event schema...")
    output = run_command("python3 scripts/validate_schema_samples.py")
    if "All validations passed!" in output and "enriched_event_valid.json is valid" in output:
        print("✅ Enriched event schema validation passed")
        return True
    else:
        print("❌ Enriched event schema validation failed")
        print(output)
        return False


def test_service_health():
    """Test 2: Check NLP enricher health endpoint."""
    print("\n🏥 Test 2: Checking NLP enricher health...")
    try:
        health_output = run_command("curl -s http://localhost:8005/health", check=False)
        if not health_output:
            print("❌ NLP enricher not responding")
            return False
        
        health_data = json.loads(health_output)
        if health_data.get("status") == "healthy":
            stats = health_data.get("stats", {})
            print(f"✅ NLP enricher healthy")
            print(f"   Stats: consumed={stats.get('consumed', 0)}, "
                  f"enriched={stats.get('enriched', 0)}, "
                  f"failed={stats.get('failed', 0)}, "
                  f"dlq={stats.get('dlq_count', 0)}")
            return True
        else:
            print(f"❌ NLP enricher unhealthy: {health_data}")
            return False
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False


def test_metrics_exposure():
    """Test 3: Verify Prometheus metrics are exposed."""
    print("\n📊 Test 3: Checking Prometheus metrics...")
    try:
        metrics_output = run_command("curl -s http://localhost:8005/metrics", check=False)
        
        required_metrics = [
            'nlp_enricher_events_consumed_total',
            'nlp_enricher_events_enriched_total',
            'nlp_enricher_events_failed_total',
            'nlp_enricher_dlq_published_total',
            'nlp_enricher_processing_duration_seconds',
            'nlp_enricher_sentiment_mean',
        ]
        
        all_present = True
        for metric in required_metrics:
            if metric in metrics_output:
                print(f"   ✅ {metric}")
            else:
                print(f"   ❌ {metric} missing")
                all_present = False
        
        if all_present:
            print("✅ All required metrics exposed")
            return True
        else:
            print("❌ Some metrics missing")
            return False
    except Exception as e:
        print(f"❌ Metrics check failed: {e}")
        return False


def test_kafka_topics():
    """Test 4: Verify enrichment Kafka topics exist."""
    print("\n📬 Test 4: Checking Kafka topics...")
    topics = run_command("docker exec redpanda rpk topic list --brokers redpanda:29092")
    
    required_topics = ["events.enriched.v1", "events.enriched.dlq.v1"]
    all_exist = True
    
    for topic in required_topics:
        if topic in topics:
            print(f"   ✅ {topic}")
        else:
            print(f"   ❌ {topic} missing")
            all_exist = False
    
    if all_exist:
        print("✅ All enrichment topics exist")
        return True
    else:
        print("❌ Some topics missing")
        return False


def create_test_normalized_event() -> dict:
    """Create a test normalized event."""
    event_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    
    normalized_text = "Apple Inc. announced record earnings today. The tech giant's stock AAPL surged on the news. CEO Tim Cook praised the strong iPhone sales."
    dedup_key = hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()
    
    event = {
        "schema_version": "normalized_event.v1",
        "event_id": event_id,
        "normalized_at_utc": datetime.now(timezone.utc).isoformat(),
        "normalized_text": normalized_text,
        "lang": "en",
        "canonical_url": "https://test.example.com/article-123",
        "dedup_key": dedup_key,
        "source_score": 0.85,
        "symbols_candidates": ["AAPL"],
        "metadata": {
            "source_type": "rss",
            "source_name": "Test Feed",
            "raw_event_id": event_id,
            "correlation_id": correlation_id,
            "published_at": "2024-01-15T10:00:00Z"
        },
        "pipeline_version": "normalizer.v1.0.test",
        "quality_flags": ["test_event"]
    }
    
    return event


def test_end_to_end_enrichment():
    """Test 5: End-to-end enrichment flow."""
    print("\n🔄 Test 5: Testing end-to-end enrichment...")
    
    # Create test event
    test_event = create_test_normalized_event()
    event_id = test_event["event_id"]
    print(f"   Created test event: {event_id}")
    
    # Save to temp file
    temp_file = f"/tmp/test_normalized_{event_id}.json"
    with open(temp_file, 'w') as f:
        json.dump(test_event, f)
    
    # Produce to Kafka
    print("   Publishing to events.normalized.v1...")
    produce_cmd = f"docker exec -i redpanda rpk topic produce events.normalized.v1 --brokers redpanda:29092 < {temp_file}"
    run_command(produce_cmd, check=True)
    
    # Wait for processing
    print("   Waiting for enrichment (10 seconds)...")
    time.sleep(10)
    
    # Try to consume enriched event
    print("   Consuming from events.enriched.v1...")
    consume_cmd = f"docker exec redpanda rpk topic consume events.enriched.v1 --brokers redpanda:29092 -n 100 --format '%v'"
    enriched_output = run_command(consume_cmd, check=False)
    
    # Look for our event_id in the output
    if event_id in enriched_output:
        print(f"✅ Found enriched event with ID {event_id}")
        
        # Parse the enriched event
        lines = enriched_output.strip().split('\n')
        for line in lines:
            try:
                event = json.loads(line)
                if event.get('event_id') == event_id:
                    print("\n   📄 Enriched event details:")
                    print(f"      Schema: {event.get('schema_version')}")
                    print(f"      Entities: {len(event.get('entities', []))} found")
                    print(f"      Tickers: {[t['symbol'] for t in event.get('tickers', [])]}")
                    print(f"      Sentiment: {event.get('sentiment', {}).get('score')} ({event.get('sentiment', {}).get('model')})")
                    print(f"      Category: {event.get('event_category')}")
                    print(f"      Quality flags: {event.get('quality_flags', [])}")
                    
                    # Validate schema
                    if event.get('schema_version') == 'enriched_event.v1':
                        print("      ✅ Schema version correct")
                    else:
                        print(f"      ❌ Wrong schema version: {event.get('schema_version')}")
                        return False
                    
                    # Check required fields
                    required_fields = ['event_id', 'enriched_at_utc', 'pipeline_version', 
                                     'source_type', 'entities', 'tickers', 'sentiment', 'event_category']
                    all_present = all(field in event for field in required_fields)
                    
                    if all_present:
                        print("      ✅ All required fields present")
                        return True
                    else:
                        missing = [f for f in required_fields if f not in event]
                        print(f"      ❌ Missing fields: {missing}")
                        return False
                        
            except json.JSONDecodeError:
                continue
        
        print(f"❌ Could not parse enriched event for ID {event_id}")
        return False
    else:
        print(f"❌ Enriched event not found for ID {event_id}")
        print(f"   Output length: {len(enriched_output)} chars")
        if len(enriched_output) > 0:
            print(f"   Sample output: {enriched_output[:200]}")
        return False


def test_minio_audit():
    """Test 6: Check MinIO audit trail (optional)."""
    print("\n💾 Test 6: Checking MinIO audit trail...")
    try:
        # List recent enriched artifacts
        list_cmd = """docker run --rm --network infra_trading-platform --entrypoint /bin/sh minio/mc -c '
mc alias set local http://minio:9000 minioadmin minioadmin123 > /dev/null 2>&1
mc ls --recursive local/pipeline-artifacts/enriched/ | tail -5
'"""
        output = run_command(list_cmd, check=False)
        
        if output and len(output) > 0:
            print("✅ MinIO audit trail contains enriched events:")
            print(output)
            return True
        else:
            print("⚠️  MinIO audit trail empty or not accessible")
            print("   (This is OK if WRITE_ENRICHED_TO_MINIO=false)")
            return True  # Don't fail on this
    except Exception as e:
        print(f"⚠️  MinIO check failed: {e}")
        print("   (This is OK if MinIO is not running)")
        return True  # Don't fail on this


def main():
    """Main test runner."""
    print("="*70)
    print("🧪 NLP Enrichment Service - End-to-End Tests")
    print("="*70)
    
    tests = [
        ("Schema Validation", test_schema_validation),
        ("Service Health", test_service_health),
        ("Metrics Exposure", test_metrics_exposure),
        ("Kafka Topics", test_kafka_topics),
        ("End-to-End Enrichment", test_end_to_end_enrichment),
        ("MinIO Audit Trail", test_minio_audit),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*70)
    print("📊 Test Summary")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:10} {test_name}")
    
    print("="*70)
    print(f"Result: {passed}/{total} tests passed")
    print("="*70)
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
