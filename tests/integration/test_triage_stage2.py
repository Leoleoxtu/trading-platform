#!/usr/bin/env python3
"""
Integration tests for Triage Stage 2 (NLP)
Tests entity extraction, sentiment analysis, scoring, and priority assignment
"""

import json
import time
import asyncio
from datetime import datetime, timezone
from kafka import KafkaProducer, KafkaConsumer

# Test events with various characteristics
TEST_EVENTS = [
    # Event 1: French high-impact earnings event
    {
        "schema_version": "stage1_event.v1",
        "event_id": "test-s2-001",
        "event_time_utc": datetime.now(timezone.utc).isoformat(),
        "source_type": "rss",
        "source_name": "les_echos",
        "canonical_url": "https://example.com/apple-q4-earnings",
        "lang": "fr",
        "normalized_text": "Apple annonce des résultats Q4 record avec un chiffre d'affaires de $89.5 milliards, "
                          "en hausse de 12.5%. Le PDG Tim Cook a déclaré être très satisfait. "
                          "Les ventes d'iPhone ont augmenté de 15% alors que la marge bénéficiaire atteint 42%.",
        "normalized_text_hash": "abc123",
        "dedup_key": "test-s2-001-dedup",
        "triage_score_stage1": 75.0,
        "triage_bucket": "fast",
        "symbols_candidates": ["AAPL"]
    },
    
    # Event 2: English ticker mention with positive sentiment
    {
        "schema_version": "stage1_event.v1",
        "event_id": "test-s2-002",
        "event_time_utc": datetime.now(timezone.utc).isoformat(),
        "source_type": "rss",
        "source_name": "bloomberg",
        "canonical_url": "https://example.com/nvidia-ai-leadership",
        "lang": "en",
        "normalized_text": "NVDA continues to dominate the AI chip market with strong demand from cloud providers. "
                          "Jensen Huang announced a new product line targeting enterprise customers. "
                          "Stock surged 8% on the news as analysts raised price targets.",
        "normalized_text_hash": "def456",
        "dedup_key": "test-s2-002-dedup",
        "triage_score_stage1": 82.0,
        "triage_bucket": "fast",
        "symbols_candidates": ["NVDA"]
    },
    
    # Event 3: Low entity event (expect NER_EMPTY flag)
    {
        "schema_version": "stage1_event.v1",
        "event_id": "test-s2-003",
        "event_time_utc": datetime.now(timezone.utc).isoformat(),
        "source_type": "reddit",
        "source_name": "wallstreetbets",
        "canonical_url": "https://reddit.com/r/wallstreetbets/comments/123",
        "lang": "en",
        "normalized_text": "The market is looking good today. I think we might see some gains.",
        "normalized_text_hash": "ghi789",
        "dedup_key": "test-s2-003-dedup",
        "triage_score_stage1": 35.0,
        "triage_bucket": "standard",
        "symbols_candidates": []
    },
    
    # Event 4: High-impact regulatory event (P0 expected)
    {
        "schema_version": "stage1_event.v1",
        "event_id": "test-s2-004",
        "event_time_utc": datetime.now(timezone.utc).isoformat(),
        "source_type": "rss",
        "source_name": "wsj",
        "canonical_url": "https://example.com/sec-investigation",
        "lang": "en",
        "normalized_text": "SEC launches investigation into Tesla over Elon Musk's tweet regarding potential merger. "
                          "The probe involves possible securities fraud and market manipulation. "
                          "Legal experts expect penalties exceeding $50 million if violations are confirmed. "
                          "TSLA shares plunged 10% in after-hours trading.",
        "normalized_text_hash": "jkl012",
        "dedup_key": "test-s2-004-dedup",
        "triage_score_stage1": 88.0,
        "triage_bucket": "fast",
        "symbols_candidates": ["TSLA"]
    },
    
    # Event 5: Low-quality reddit event (P3 expected)
    {
        "schema_version": "stage1_event.v1",
        "event_id": "test-s2-005",
        "event_time_utc": datetime.now(timezone.utc).isoformat(),
        "source_type": "reddit",
        "source_name": "pennystocks",
        "canonical_url": "https://reddit.com/r/pennystocks/comments/456",
        "lang": "en",
        "normalized_text": "This random stock might go up soon. Just a feeling. To the moon! 🚀🚀🚀",
        "normalized_text_hash": "mno345",
        "dedup_key": "test-s2-005-dedup",
        "triage_score_stage1": 25.0,
        "triage_bucket": "standard",
        "symbols_candidates": []
    }
]


def publish_test_events(bootstrap_servers='localhost:9092', topic='events.stage1.fast.v1'):
    """Publish test events to Kafka"""
    producer = KafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        compression_type='snappy'
    )
    
    print(f"Publishing {len(TEST_EVENTS)} test events to {topic}...")
    
    for event in TEST_EVENTS:
        try:
            # Publish to appropriate topic based on bucket
            target_topic = f"events.stage1.{event['triage_bucket']}.v1"
            future = producer.send(target_topic, value=event)
            result = future.get(timeout=10)
            print(f"✅ Published event {event['event_id']} to {target_topic} "
                  f"(partition {result.partition}, offset {result.offset})")
        except Exception as e:
            print(f"❌ Failed to publish event {event['event_id']}: {e}")
    
    producer.flush()
    producer.close()
    print("\nAll test events published!")


def consume_and_validate_results(
    bootstrap_servers='localhost:9092',
    topic='events.triaged.v1',
    timeout_seconds=60
):
    """Consume triaged events and validate results"""
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        value_deserializer=lambda v: json.loads(v.decode('utf-8')),
        auto_offset_reset='latest',
        consumer_timeout_ms=timeout_seconds * 1000,
        group_id='test-triage-stage2-validator'
    )
    
    print(f"\nConsuming from {topic} (timeout: {timeout_seconds}s)...")
    results = []
    
    try:
        for message in consumer:
            event = message.value
            event_id = event.get('event_id')
            
            print(f"\n{'='*80}")
            print(f"Event: {event_id}")
            print(f"{'='*80}")
            
            # Validate schema
            assert event.get('schema_version') == 'triaged_event.v1', "Invalid schema version"
            assert event.get('triage_score') is not None, "Missing triage_score"
            assert event.get('priority') in ['P0', 'P1', 'P2', 'P3'], "Invalid priority"
            
            # Display key fields
            print(f"Priority: {event['priority']}")
            print(f"Score: {event['triage_score']}/100")
            print(f"Score Breakdown: {json.dumps(event.get('score_breakdown', {}), indent=2)}")
            print(f"Sentiment: {event.get('sentiment', {}).get('label')} "
                  f"(score={event.get('sentiment', {}).get('score'):.2f}, "
                  f"conf={event.get('sentiment', {}).get('confidence'):.2f})")
            print(f"Entities: {len(event.get('entities', []))} extracted")
            for entity in event.get('entities', [])[:5]:  # Show first 5
                print(f"  - {entity['type']}: {entity['text']} (conf={entity['confidence']:.2f})")
            print(f"Tickers: {', '.join(t['symbol'] for t in event.get('tickers', []))}")
            print(f"Reasons: {', '.join(event.get('triage_reasons', []))}")
            print(f"Market Regime: {event.get('regime', {}).get('market_regime')}")
            print(f"Load Regime: {event.get('regime', {}).get('load_regime')}")
            print(f"Processing Time: {event.get('processing_time_ms')}ms")
            print(f"Quality Flags: {', '.join(event.get('quality_flags', []))}")
            
            # Specific validations per test event
            if event_id == 'test-s2-001':
                # French earnings event - should have high score, entities, P0/P1
                assert event['priority'] in ['P0', 'P1'], f"Expected P0/P1 for earnings event, got {event['priority']}"
                assert len(event.get('entities', [])) > 0, "Expected entities for detailed event"
                assert any('KEYWORD' in r for r in event.get('triage_reasons', [])), "Expected keyword match"
                print("✅ Test 1 passed: French earnings event properly scored")
            
            elif event_id == 'test-s2-002':
                # Nvidia ticker event - should have NVDA ticker, positive sentiment
                assert any(t['symbol'] == 'NVDA' for t in event.get('tickers', [])), "Expected NVDA ticker"
                assert event.get('sentiment', {}).get('score') > 0, "Expected positive sentiment"
                assert event['priority'] in ['P0', 'P1'], "Expected high priority for positive news"
                print("✅ Test 2 passed: Ticker and sentiment validated")
            
            elif event_id == 'test-s2-003':
                # Low entity event - should have NER_EMPTY flag, low score
                assert 'NO_ENTITIES' in event.get('quality_flags', []) or \
                       'NER_EMPTY' in event.get('triage_reasons', []), "Expected NO_ENTITIES flag"
                assert event['triage_score'] < 60, f"Expected low score for vague event, got {event['triage_score']}"
                print("✅ Test 3 passed: Low entity event detected")
            
            elif event_id == 'test-s2-004':
                # High-impact regulatory event - should be P0 with strong keywords
                assert event['priority'] == 'P0', f"Expected P0 for SEC investigation, got {event['priority']}"
                assert any('SEC' in r or 'KEYWORD' in r for r in event.get('triage_reasons', [])), \
                       "Expected SEC/regulatory keyword match"
                assert any(t['symbol'] == 'TSLA' for t in event.get('tickers', [])), "Expected TSLA ticker"
                assert event.get('sentiment', {}).get('score') < 0, "Expected negative sentiment"
                print("✅ Test 4 passed: High-impact regulatory event = P0")
            
            elif event_id == 'test-s2-005':
                # Low-quality reddit - should be P3 with low source quality
                assert event['priority'] == 'P3', f"Expected P3 for low-quality reddit, got {event['priority']}"
                assert 'LOW_SOURCE_QUALITY' in event.get('triage_reasons', []), "Expected low source quality flag"
                print("✅ Test 5 passed: Low-quality reddit = P3")
            
            results.append(event)
            
            # Stop after receiving all test events
            if len(results) >= len(TEST_EVENTS):
                break
    
    except Exception as e:
        print(f"\n❌ Error during validation: {e}")
    finally:
        consumer.close()
    
    print(f"\n{'='*80}")
    print(f"VALIDATION SUMMARY")
    print(f"{'='*80}")
    print(f"Total events processed: {len(results)}/{len(TEST_EVENTS)}")
    
    if len(results) == len(TEST_EVENTS):
        print("✅ All test events successfully processed and validated!")
        return True
    else:
        print(f"⚠️  Only {len(results)} events received (expected {len(TEST_EVENTS)})")
        print("Tip: Ensure triage-stage2 service is running and consuming from stage1 topics")
        return False


def main():
    """Run integration tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Triage Stage 2 Integration Tests')
    parser.add_argument(
        '--bootstrap-servers',
        default='localhost:9092',
        help='Kafka bootstrap servers (default: localhost:9092)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=60,
        help='Consumer timeout in seconds (default: 60)'
    )
    parser.add_argument(
        '--publish-only',
        action='store_true',
        help='Only publish test events without consuming'
    )
    parser.add_argument(
        '--consume-only',
        action='store_true',
        help='Only consume and validate without publishing'
    )
    
    args = parser.parse_args()
    
    if not args.consume_only:
        print("Step 1: Publishing test events...")
        publish_test_events(bootstrap_servers=args.bootstrap_servers)
        
        if not args.publish_only:
            print("\nWaiting 5 seconds for processing...")
            time.sleep(5)
    
    if not args.publish_only:
        print("\nStep 2: Consuming and validating results...")
        success = consume_and_validate_results(
            bootstrap_servers=args.bootstrap_servers,
            timeout_seconds=args.timeout
        )
        
        return 0 if success else 1
    
    return 0


if __name__ == '__main__':
    exit(main())
