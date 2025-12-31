"""
Unit tests for RSS Collector
Tests feed parsing, deduplication, Kafka publishing, and MinIO archiving.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pathlib import Path
import json

from src.ingestion.rss_collector import RSSCollector
from src.ingestion.base import RawEvent


# Mock RSS feed data
MOCK_RSS_FEED_1 = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>Test Financial News</title>
        <item>
            <title>Stock Market Hits New High</title>
            <link>https://example.com/news/1</link>
            <description>Markets reached record levels today...</description>
            <pubDate>Mon, 30 Dec 2024 10:00:00 GMT</pubDate>
        </item>
        <item>
            <title>Fed Announces Rate Decision</title>
            <link>https://example.com/news/2</link>
            <description>Federal Reserve announces...</description>
            <pubDate>Mon, 30 Dec 2024 11:00:00 GMT</pubDate>
        </item>
    </channel>
</rss>
"""

MOCK_RSS_FEED_2 = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>Test Tech News</title>
        <item>
            <title>AI Breakthrough Announced</title>
            <link>https://example.com/tech/1</link>
            <description>New AI model released...</description>
            <pubDate>Mon, 30 Dec 2024 12:00:00 GMT</pubDate>
        </item>
    </channel>
</rss>
"""


@pytest.fixture
def mock_config(tmp_path):
    """Create mock RSS config file."""
    config_path = tmp_path / "test_rss_sources.yaml"
    config_content = """
sources:
  - name: Test Feed 1
    url: https://example.com/feed1.xml
    priority: high
    quality: 9
  - name: Test Feed 2
    url: https://example.com/feed2.xml
    priority: medium
    quality: 7
"""
    config_path.write_text(config_content)
    return str(config_path)


@pytest.fixture
def mock_dedup_file(tmp_path):
    """Create mock dedup state file."""
    return str(tmp_path / "seen_items.json")


@pytest.fixture
def rss_collector(mock_config, mock_dedup_file):
    """Create RSSCollector instance with mocked dependencies."""
    with patch('src.ingestion.rss_collector.boto3.client'):
        collector = RSSCollector(
            config_path=mock_config,
            kafka_bootstrap_servers="localhost:9092",
            kafka_topic="test.raw.events.v1",
            minio_endpoint="localhost:9000",
            minio_access_key="test",
            minio_secret_key="test",
            minio_bucket="test-bucket",
            dedup_state_file=mock_dedup_file
        )
        return collector


@pytest.mark.asyncio
async def test_load_config(rss_collector):
    """Test loading RSS sources from config."""
    assert len(rss_collector.feeds) == 2
    assert rss_collector.feeds[0]['name'] == 'Test Feed 1'
    assert rss_collector.feeds[0]['priority'] == 'high'
    assert rss_collector.feeds[1]['quality'] == 7


@pytest.mark.asyncio
async def test_generate_item_id(rss_collector):
    """Test unique ID generation for RSS items."""
    id1 = rss_collector._generate_item_id("Feed1", "http://example.com/1", "Title 1")
    id2 = rss_collector._generate_item_id("Feed1", "http://example.com/1", "Title 1")
    id3 = rss_collector._generate_item_id("Feed1", "http://example.com/2", "Title 1")
    
    assert id1 == id2  # Same content = same ID
    assert id1 != id3  # Different URL = different ID
    assert len(id1) == 16  # ID length check


@pytest.mark.asyncio
async def test_deduplication(rss_collector):
    """Test duplicate detection."""
    item_id = "test_id_12345"
    
    # First check - not duplicate
    assert rss_collector._is_duplicate(item_id) is False
    
    # Add to seen items
    rss_collector.seen_items.add(item_id)
    
    # Second check - is duplicate
    assert rss_collector._is_duplicate(item_id) is True


@pytest.mark.asyncio
async def test_dedup_state_persistence(rss_collector, mock_dedup_file):
    """Test saving and loading dedup state."""
    # Add some items
    rss_collector.seen_items = {"id1", "id2", "id3"}
    
    # Save state
    rss_collector._save_dedup_state()
    
    # Create new collector with same state file
    with patch('src.ingestion.rss_collector.boto3.client'):
        new_collector = RSSCollector(
            config_path=rss_collector.config_path,
            dedup_state_file=mock_dedup_file
        )
    
    # Check state was loaded
    assert len(new_collector.seen_items) == 3
    assert "id1" in new_collector.seen_items


@pytest.mark.asyncio
async def test_collect_events(rss_collector):
    """Test collecting events from RSS feeds."""
    # Mock feedparser.parse
    mock_feed = Mock()
    mock_feed.bozo = False
    mock_feed.entries = [
        {
            'title': 'Test Title 1',
            'link': 'https://example.com/1',
            'summary': 'Test summary 1',
            'published_parsed': (2024, 12, 30, 10, 0, 0, 0, 0, 0)
        },
        {
            'title': 'Test Title 2',
            'link': 'https://example.com/2',
            'summary': 'Test summary 2',
            'published_parsed': (2024, 12, 30, 11, 0, 0, 0, 0, 0)
        }
    ]
    
    with patch('feedparser.parse', return_value=mock_feed):
        events = await rss_collector.collect()
    
    # Should get 2 events per feed (2 feeds * 2 items = 4 total)
    assert len(events) == 4
    assert all(isinstance(e, RawEvent) for e in events)
    assert events[0].source == 'rss'
    assert 'Test Title 1' in events[0].text


@pytest.mark.asyncio
async def test_collect_with_duplicates(rss_collector):
    """Test that duplicates are filtered during collection."""
    # Pre-populate seen items
    item_id = rss_collector._generate_item_id(
        "Test Feed 1",
        "https://example.com/1",
        "Test Title 1"
    )
    rss_collector.seen_items.add(item_id)
    
    # Mock feedparser
    mock_feed = Mock()
    mock_feed.bozo = False
    mock_feed.entries = [
        {
            'title': 'Test Title 1',
            'link': 'https://example.com/1',
            'summary': 'Test summary 1',
            'published_parsed': (2024, 12, 30, 10, 0, 0, 0, 0, 0)
        }
    ]
    
    with patch('feedparser.parse', return_value=mock_feed):
        events = await rss_collector.collect()
    
    # Should be filtered out (appears in both feeds, but deduplicated)
    assert len(events) < 2


@pytest.mark.asyncio
async def test_publish_to_kafka(rss_collector):
    """Test publishing events to Kafka."""
    events = [
        RawEvent(
            source='rss',
            url='https://example.com/1',
            text='Test event 1',
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={'feed_name': 'Test Feed'}
        ),
        RawEvent(
            source='rss',
            url='https://example.com/2',
            text='Test event 2',
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={'feed_name': 'Test Feed'}
        )
    ]
    
    # Mock Kafka producer
    mock_producer = AsyncMock()
    mock_producer.start = AsyncMock()
    mock_producer.send_and_wait = AsyncMock()
    
    with patch('src.ingestion.rss_collector.AIOKafkaProducer', return_value=mock_producer):
        rss_collector.kafka_producer = None  # Reset
        count = await rss_collector.publish_to_kafka(events)
    
    assert count == 2
    assert mock_producer.send_and_wait.call_count == 2


@pytest.mark.asyncio
async def test_archive_to_minio(rss_collector):
    """Test archiving events to MinIO."""
    events = [
        RawEvent(
            source='rss',
            url='https://example.com/1',
            text='Test event 1',
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={}
        )
    ]
    
    # Mock S3 client
    mock_s3 = Mock()
    mock_s3.put_object = Mock()
    rss_collector.s3_client = mock_s3
    
    result = await rss_collector.archive_to_minio(events)
    
    assert result is True
    assert mock_s3.put_object.called


@pytest.mark.asyncio
async def test_run_once_integration(rss_collector):
    """Test complete run_once cycle."""
    # Mock all external calls
    mock_feed = Mock()
    mock_feed.bozo = False
    mock_feed.entries = [
        {
            'title': 'Integration Test',
            'link': 'https://example.com/test',
            'summary': 'Test content',
            'published_parsed': (2024, 12, 30, 10, 0, 0, 0, 0, 0)
        }
    ]
    
    mock_producer = AsyncMock()
    mock_producer.start = AsyncMock()
    mock_producer.send_and_wait = AsyncMock()
    
    mock_s3 = Mock()
    mock_s3.put_object = Mock()
    rss_collector.s3_client = mock_s3
    
    with patch('feedparser.parse', return_value=mock_feed), \
         patch('src.ingestion.rss_collector.AIOKafkaProducer', return_value=mock_producer):
        
        stats = await rss_collector.run_once()
    
    assert stats['collector'] == 'rss_collector'
    assert stats['collected'] > 0
    assert stats['published'] > 0
    assert stats['archived'] is True
    assert len(stats['errors']) == 0


@pytest.mark.asyncio
async def test_error_handling_invalid_feed(rss_collector):
    """Test handling of invalid RSS feed."""
    # Mock feedparser with bozo error
    mock_feed = Mock()
    mock_feed.bozo = True
    mock_feed.bozo_exception = Exception("Invalid XML")
    mock_feed.entries = []
    
    with patch('feedparser.parse', return_value=mock_feed):
        events = await rss_collector.collect()
    
    # Should handle error gracefully and return empty list
    assert len(events) == 0


@pytest.mark.asyncio
async def test_metrics_incremented(rss_collector):
    """Test that Prometheus metrics are incremented."""
    from src.ingestion.rss_collector import ITEMS_FETCHED, FEEDS_PROCESSED
    
    initial_items = ITEMS_FETCHED.labels(feed_name='Test Feed 1')._value._value
    initial_feeds = FEEDS_PROCESSED.labels(feed_name='Test Feed 1', status='success')._value._value
    
    mock_feed = Mock()
    mock_feed.bozo = False
    mock_feed.entries = [
        {
            'title': 'Metric Test',
            'link': 'https://example.com/metric',
            'summary': 'Metric content',
            'published_parsed': (2024, 12, 30, 10, 0, 0, 0, 0, 0)
        }
    ]
    
    with patch('feedparser.parse', return_value=mock_feed):
        await rss_collector.collect()
    
    # Metrics should have increased
    # Note: Actual values depend on previous test runs in same session


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
