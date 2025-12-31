"""
Integration test for Triage Stage 1 - End-to-End
Tests that normalized events are correctly triaged and routed to stage1 topics
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from loguru import logger

# Configuration
KAFKA_BOOTSTRAP_SERVERS = ["localhost:9092"]
NORMALIZED_TOPIC = "events.normalized.v1"
STAGE1_FAST_TOPIC = "events.stage1.fast.v1"
STAGE1_STANDARD_TOPIC = "events.stage1.standard.v1"
STAGE1_COLD_TOPIC = "events.stage1.cold.v1"
STAGE1_DROPPED_TOPIC = "events.stage1.dropped.v1"

TIMEOUT_SECONDS = 30


def create_normalized_event(
    text: str,
    source: str = "rss",
    source_name: str = "bloomberg",
    url: str = "https://example.com",
    timestamp: datetime = None,
) -> Dict:
    """Create a normalized event for testing"""
    if timestamp is None:
        timestamp = datetime.utcnow()

    return {
        "schema_version": "normalized_event.v1",
        "event_id": str(uuid.uuid4()),
        "normalized_at_utc": datetime.utcnow().isoformat() + "Z",
        "pipeline_version": "1.0.0",
        "source_type": source,
        "source_name": source_name,
        "text": text,
        "canonical_url": url,
        "lang": "en",
        "event_time_utc": timestamp.isoformat() + "Z",
        "quality_flags": [],
        "original_source": {
            "id": str(uuid.uuid4()),
            "timestamp": timestamp.isoformat() + "Z",
            "url": url,
            "title": text[:100],
        },
    }


async def send_event(producer: AIOKafkaProducer, event: Dict) -> str:
    """Send event to normalized topic and return event_id"""
    event_id = event["event_id"]
    await producer.send_and_wait(
        NORMALIZED_TOPIC,
        json.dumps(event).encode(),
        key=event_id.encode(),
    )
    logger.info(f"Sent event {event_id}")
    return event_id


async def consume_stage1_events(
    timeout_seconds: int = TIMEOUT_SECONDS,
) -> Dict[str, List[Dict]]:
    """Consume events from all stage1 topics"""
    events_by_bucket = {
        "FAST": [],
        "STANDARD": [],
        "COLD": [],
        "DROP_HARD": [],
    }

    # Create consumers for each topic
    consumers = {}
    topics = {
        "FAST": STAGE1_FAST_TOPIC,
        "STANDARD": STAGE1_STANDARD_TOPIC,
        "COLD": STAGE1_COLD_TOPIC,
        "DROP_HARD": STAGE1_DROPPED_TOPIC,
    }

    for bucket, topic in topics.items():
        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id=f"test-triage-stage1-e2e-{uuid.uuid4()}",
            auto_offset_reset="latest",
            value_deserializer=lambda m: json.loads(m.decode()),
            session_timeout_ms=10000,
        )
        await consumer.start()
        consumers[bucket] = consumer

    try:
        # Collect messages with timeout
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout_seconds:
            for bucket, consumer in consumers.items():
                try:
                    # Non-blocking consumption
                    message = await asyncio.wait_for(
                        consumer.__anext__(),
                        timeout=0.5,
                    )
                    events_by_bucket[bucket].append(message.value)
                    logger.info(f"Received event in {bucket} bucket")
                except asyncio.TimeoutError:
                    pass
                except StopAsyncIteration:
                    pass
    finally:
        # Cleanup
        for consumer in consumers.values():
            await consumer.stop()

    return events_by_bucket


async def test_strong_keyword_reliable_source_goes_fast():
    """
    Test Case 1: Strong keyword + Bloomberg source → FAST bucket
    Event: "Apple reported Q4 earnings exceeding estimates by 15%"
    Expected: score >= 70, bucket=FAST, P0 priority
    """
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    await producer.start()

    try:
        event = create_normalized_event(
            text="Apple reported Q4 earnings exceeding estimates by 15%. Revenue up $34.2B.",
            source="rss",
            source_name="bloomberg",
        )
        event_id = await send_event(producer, event)
        await asyncio.sleep(2)  # Wait for processing

        events = await consume_stage1_events(timeout_seconds=5)

        # Should be in FAST bucket
        assert len(events["FAST"]) > 0, "No events in FAST bucket"
        fast_event = next(e for e in events["FAST"] if e["event_id"] == event_id)

        assert fast_event["triage_bucket"] == "FAST"
        assert fast_event["triage_score_stage1"] >= 70
        assert fast_event["priority_hint"] == "P0"
        assert "STRONG_KEYWORDS" in fast_event["triage_reasons"]
        assert "HAS_TICKER_CANDIDATES" in fast_event["triage_reasons"]
        logger.info(f"✓ Test 1 passed: FAST bucket with score {fast_event['triage_score_stage1']}")

    finally:
        await producer.stop()


async def test_strong_keyword_reddit_source_goes_standard():
    """
    Test Case 2: Strong keyword + Reddit source → STANDARD bucket
    Event: "MSFT merger acquisition rumors"
    Expected: score 40-70, bucket=STANDARD, P1-P2 priority
    """
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    await producer.start()

    try:
        event = create_normalized_event(
            text="Microsoft merger with AI startup rumored by sources. Could be $50 billion deal.",
            source="reddit",
            source_name="stocks",
        )
        event_id = await send_event(producer, event)
        await asyncio.sleep(2)

        events = await consume_stage1_events(timeout_seconds=5)

        # Should be in STANDARD bucket
        assert len(events["STANDARD"]) > 0, "No events in STANDARD bucket"
        std_event = next((e for e in events["STANDARD"] if e["event_id"] == event_id), None)

        if std_event:
            assert std_event["triage_bucket"] == "STANDARD"
            assert 40 <= std_event["triage_score_stage1"] < 70
            assert std_event["priority_hint"] in ["P1", "P2"]
            logger.info(f"✓ Test 2 passed: STANDARD bucket with score {std_event['triage_score_stage1']}")

    finally:
        await producer.stop()


async def test_weak_keyword_with_ticker_goes_standard():
    """
    Test Case 3: Weak keyword + ticker → STANDARD bucket
    Event: "Tesla reported might have new battery technology"
    Expected: score 40-70, bucket=STANDARD
    """
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    await producer.start()

    try:
        event = create_normalized_event(
            text="Tesla might be developing new battery technology. TSLA stock could benefit.",
            source="rss",
            source_name="seeking_alpha",
        )
        event_id = await send_event(producer, event)
        await asyncio.sleep(2)

        events = await consume_stage1_events(timeout_seconds=5)

        # Should be in STANDARD bucket
        assert len(events["STANDARD"]) > 0, "No events in STANDARD bucket"
        std_event = next((e for e in events["STANDARD"] if e["event_id"] == event_id), None)

        if std_event:
            assert std_event["triage_bucket"] == "STANDARD"
            assert 40 <= std_event["triage_score_stage1"] < 70
            logger.info(f"✓ Test 3 passed: STANDARD bucket with score {std_event['triage_score_stage1']}")

    finally:
        await producer.stop()


async def test_ticker_only_no_keywords_goes_cold():
    """
    Test Case 4: Only ticker mentioned, no strong keywords → COLD bucket
    Event: "AAPL trading at all-time highs today"
    Expected: score < 40, bucket=COLD, P3 priority
    """
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    await producer.start()

    try:
        event = create_normalized_event(
            text="AAPL is trading at all-time highs today in the market.",
            source="rss",
            source_name="marketwatch",
        )
        event_id = await send_event(producer, event)
        await asyncio.sleep(2)

        events = await consume_stage1_events(timeout_seconds=5)

        # Should be in COLD bucket
        assert len(events["COLD"]) > 0, "No events in COLD bucket"
        cold_event = next((e for e in events["COLD"] if e["event_id"] == event_id), None)

        if cold_event:
            assert cold_event["triage_bucket"] == "COLD"
            assert cold_event["triage_score_stage1"] < 40
            assert cold_event["priority_hint"] == "P3"
            logger.info(f"✓ Test 4 passed: COLD bucket with score {cold_event['triage_score_stage1']}")

    finally:
        await producer.stop()


async def test_no_signals_goes_cold():
    """
    Test Case 5: Generic text, no signals → COLD bucket
    Event: "The stock market was busy today"
    Expected: score < 40, bucket=COLD
    """
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    await producer.start()

    try:
        event = create_normalized_event(
            text="The stock market was busy today with lots of trading activity.",
            source="reddit",
            source_name="stocks",
        )
        event_id = await send_event(producer, event)
        await asyncio.sleep(2)

        events = await consume_stage1_events(timeout_seconds=5)

        # Should be in COLD bucket
        assert len(events["COLD"]) > 0, "No events in COLD bucket"
        cold_event = next((e for e in events["COLD"] if e["event_id"] == event_id), None)

        if cold_event:
            assert cold_event["triage_bucket"] == "COLD"
            assert cold_event["triage_score_stage1"] < 40
            logger.info(f"✓ Test 5 passed: COLD bucket with score {cold_event['triage_score_stage1']}")

    finally:
        await producer.stop()


async def test_clickbait_suspicious_low_score():
    """
    Test Case 6: Clickbait signals → Lower score, potentially DROP_HARD
    Event: "Shocking revelation you won't believe about tech CEO"
    Expected: penalty applied, score low or DROP_HARD
    """
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    await producer.start()

    try:
        event = create_normalized_event(
            text="Shocking revelation you won't believe about Apple CEO. Exclusive insider story revealed!",
            source="reddit",
            source_name="wallstreetbets",
        )
        event_id = await send_event(producer, event)
        await asyncio.sleep(2)

        events = await consume_stage1_events(timeout_seconds=5)

        # Could be COLD or DROP_HARD
        found = False
        for bucket in ["COLD", "DROP_HARD"]:
            matching = [e for e in events[bucket] if e["event_id"] == event_id]
            if matching:
                event_result = matching[0]
                assert "CLICKBAIT_SUSPECT" in event_result["triage_reasons"]
                logger.info(f"✓ Test 6 passed: Clickbait event in {bucket} with score {event_result['triage_score_stage1']}")
                found = True
                break

        assert found, "Clickbait event not found in COLD or DROP_HARD"

    finally:
        await producer.stop()


async def test_very_short_text_penalty():
    """
    Test Case 7: Very short text → Penalty applied
    Event: "AAPL up"
    Expected: short text penalty, low score
    """
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    await producer.start()

    try:
        event = create_normalized_event(
            text="AAPL up",
            source="rss",
            source_name="default",
        )
        event_id = await send_event(producer, event)
        await asyncio.sleep(2)

        events = await consume_stage1_events(timeout_seconds=5)

        # Should be in COLD or DROP_HARD
        found = False
        for bucket in ["COLD", "DROP_HARD"]:
            matching = [e for e in events[bucket] if e["event_id"] == event_id]
            if matching:
                event_result = matching[0]
                logger.info(f"✓ Test 7 passed: Short text event in {bucket} with score {event_result['triage_score_stage1']}")
                found = True
                break

        assert found, "Short text event not found in COLD or DROP_HARD"

    finally:
        await producer.stop()


async def test_very_recent_event_bonus():
    """
    Test Case 8: Very recent event → Recency bonus
    Event: Published < 1 minute ago with strong keywords
    Expected: Recency bonus applied, higher score
    """
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    await producer.start()

    try:
        recent_time = datetime.utcnow() - timedelta(seconds=30)
        event = create_normalized_event(
            text="Apple announced earnings results today",
            source="rss",
            source_name="bloomberg",
            timestamp=recent_time,
        )
        event_id = await send_event(producer, event)
        await asyncio.sleep(2)

        events = await consume_stage1_events(timeout_seconds=5)

        # Should include VERY_RECENT in reasons
        found = False
        for bucket in ["FAST", "STANDARD"]:
            matching = [e for e in events[bucket] if e["event_id"] == event_id]
            if matching:
                event_result = matching[0]
                assert "VERY_RECENT" in event_result["triage_reasons"]
                logger.info(f"✓ Test 8 passed: Recent event in {bucket} with recency bonus")
                found = True
                break

        assert found, "Recent event not found in FAST or STANDARD"

    finally:
        await producer.stop()


async def main():
    """Run all integration tests"""
    logger.info("Starting Triage Stage 1 E2E Integration Tests...")

    tests = [
        ("Test 1: Strong keyword + reliable source → FAST", test_strong_keyword_reliable_source_goes_fast),
        ("Test 2: Strong keyword + Reddit → STANDARD", test_strong_keyword_reddit_source_goes_standard),
        ("Test 3: Weak keyword + ticker → STANDARD", test_weak_keyword_with_ticker_goes_standard),
        ("Test 4: Ticker only → COLD", test_ticker_only_no_keywords_goes_cold),
        ("Test 5: No signals → COLD", test_no_signals_goes_cold),
        ("Test 6: Clickbait suspicious → COLD/DROP_HARD", test_clickbait_suspicious_low_score),
        ("Test 7: Very short text → Low score", test_very_short_text_penalty),
        ("Test 8: Very recent event → Recency bonus", test_very_recent_event_bonus),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            logger.info(f"\n▶ Running: {test_name}")
            await test_func()
            passed += 1
        except Exception as e:
            logger.error(f"✗ Test failed: {test_name}")
            logger.error(f"  Error: {e}")
            failed += 1

    logger.info(f"\n{'='*60}")
    logger.info(f"Integration Test Results: {passed} passed, {failed} failed")
    logger.info(f"{'='*60}")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
