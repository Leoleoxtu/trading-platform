"""
Unit tests for Normalizer.
Tests text cleaning, deduplication, and Kafka processing.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.preprocessing.normalizer import Normalizer


@pytest.fixture
def normalizer():
    """Create normalizer instance with mocked Redis."""
    with patch('src.preprocessing.normalizer.redis.from_url') as mock_redis:
        mock_redis_client = Mock()
        mock_redis_client.exists.return_value = False
        mock_redis_client.setex.return_value = True
        mock_redis.return_value = mock_redis_client
        
        norm = Normalizer(
            kafka_bootstrap_servers='localhost:9092',
            redis_url='redis://localhost:6379'
        )
        return norm


def test_normalizer_init(normalizer):
    """Test normalizer initialization."""
    assert normalizer.input_topic == 'raw.events.v1'
    assert normalizer.output_topic == 'events.normalized.v1'
    assert normalizer.dedup_ttl == 172800
    assert not normalizer.is_running()


def test_strip_html(normalizer):
    """Test HTML stripping."""
    html_text = '<p>This is <b>bold</b> and <a href="link">linked</a> text.</p>'
    clean_text = normalizer._strip_html(html_text)
    
    assert '<' not in clean_text
    assert '>' not in clean_text
    assert 'bold' in clean_text
    assert 'linked' in clean_text


def test_strip_html_with_entities(normalizer):
    """Test HTML entity unescaping."""
    html_text = 'Stock up 5% &amp; volume increased &gt; 1M'
    clean_text = normalizer._strip_html(html_text)
    
    assert '&amp;' not in clean_text
    assert '&' in clean_text
    assert '&gt;' not in clean_text
    assert '>' in clean_text


def test_normalize_unicode(normalizer):
    """Test Unicode normalization."""
    text_with_special = 'Café\u00a0résumé\u200b'  # non-breaking space, zero-width space
    normalized = normalizer._normalize_unicode(text_with_special)
    
    assert '\u200b' not in normalized
    assert 'Café' in normalized


def test_remove_urls(normalizer):
    """Test URL removal."""
    text_with_urls = 'Check this out: https://example.com and www.test.com for more info'
    clean_text = normalizer._remove_urls(text_with_urls)
    
    assert 'https://' not in clean_text
    assert 'www.' not in clean_text
    assert 'Check this out:' in clean_text
    assert 'for more info' in clean_text


def test_normalize_timestamp(normalizer):
    """Test timestamp normalization."""
    # ISO 8601 with timezone
    ts1 = '2024-01-15T10:30:00+00:00'
    normalized1 = normalizer._normalize_timestamp(ts1)
    assert '+00:00' in normalized1 or 'Z' in normalized1
    
    # ISO 8601 with Z
    ts2 = '2024-01-15T10:30:00Z'
    normalized2 = normalizer._normalize_timestamp(ts2)
    assert '+00:00' in normalized2 or 'Z' in normalized2


def test_generate_content_hash(normalizer):
    """Test content hash generation."""
    text = "This is test content"
    hash1 = normalizer._generate_content_hash(text)
    hash2 = normalizer._generate_content_hash(text)
    
    # Same content should produce same hash
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 hex length
    
    # Different content should produce different hash
    hash3 = normalizer._generate_content_hash("Different content")
    assert hash1 != hash3


def test_deduplication(normalizer):
    """Test deduplication logic."""
    content_hash = "abc123def456"
    
    # First check - not duplicate
    assert not normalizer._is_duplicate(content_hash)
    
    # Mock Redis to return exists=True
    normalizer.redis_client.exists.return_value = True
    
    # Second check - is duplicate
    assert normalizer._is_duplicate(content_hash)


def test_normalize_event_complete(normalizer):
    """Test complete event normalization."""
    raw_event = {
        'source': 'rss',
        'url': 'https://example.com/article',
        'text': '<p>Stock <b>AAPL</b> rises 5% on earnings beat. More at https://link.com</p>',
        'timestamp': '2024-01-15T10:30:00Z',
        'metadata': {'priority': 'high'}
    }
    
    normalized = normalizer.normalize_event(raw_event)
    
    assert normalized is not None
    assert normalized['source'] == 'rss'
    assert '<p>' not in normalized['text']
    assert '<b>' not in normalized['text']
    assert 'AAPL' in normalized['text']
    assert 'https://' not in normalized['text']
    assert 'event_id' in normalized
    assert 'content_hash' in normalized
    assert 'processed_at' in normalized


def test_normalize_event_duplicate(normalizer):
    """Test duplicate event filtering."""
    raw_event = {
        'source': 'rss',
        'url': 'https://example.com/article',
        'text': 'Test article content',
        'timestamp': '2024-01-15T10:30:00Z',
        'metadata': {}
    }
    
    # First normalization should succeed
    normalized1 = normalizer.normalize_event(raw_event)
    assert normalized1 is not None
    
    # Mock Redis to indicate duplicate
    normalizer.redis_client.exists.return_value = True
    
    # Second normalization should return None (duplicate)
    normalized2 = normalizer.normalize_event(raw_event)
    assert normalized2 is None


def test_normalize_event_short_text(normalizer):
    """Test filtering of events with short text."""
    raw_event = {
        'source': 'rss',
        'url': 'https://example.com/article',
        'text': '<p>Hi</p>',  # Very short after cleaning
        'timestamp': '2024-01-15T10:30:00Z',
        'metadata': {}
    }
    
    normalized = normalizer.normalize_event(raw_event)
    
    # Should be filtered out due to short length
    assert normalized is None


@pytest.mark.asyncio
async def test_consume_and_normalize_integration(normalizer):
    """Test consume and normalize integration (mocked)."""
    with patch('src.preprocessing.normalizer.AIOKafkaConsumer') as mock_consumer_class, \
         patch('src.preprocessing.normalizer.AIOKafkaProducer') as mock_producer_class:
        
        # Mock consumer
        mock_consumer = AsyncMock()
        mock_message = Mock()
        mock_message.value = {
            'source': 'rss',
            'url': 'https://test.com',
            'text': 'Test article content',
            'timestamp': '2024-01-15T10:30:00Z',
            'metadata': {}
        }
        
        # Make consumer return one message then stop
        async def mock_iter():
            yield mock_message
            normalizer.stop()
        
        mock_consumer.__aiter__.return_value = mock_iter()
        mock_consumer_class.return_value = mock_consumer
        
        # Mock producer
        mock_producer = AsyncMock()
        mock_producer_class.return_value = mock_producer
        
        # Run consume loop
        await normalizer.consume_and_normalize()
        
        # Verify
        mock_consumer.start.assert_called_once()
        mock_producer.start.assert_called_once()
        mock_producer.send.assert_called_once()
        mock_consumer.stop.assert_called_once()
        mock_producer.stop.assert_called_once()


def test_normalize_event_metadata_preservation(normalizer):
    """Test that metadata is preserved during normalization."""
    raw_event = {
        'source': 'reddit',
        'url': 'https://reddit.com/r/test/post',
        'text': 'This is a test post with metadata',
        'timestamp': '2024-01-15T10:30:00Z',
        'metadata': {
            'subreddit': 'test',
            'score': 150,
            'author': 'testuser'
        }
    }
    
    normalized = normalizer.normalize_event(raw_event)
    
    assert normalized is not None
    assert normalized['metadata']['subreddit'] == 'test'
    assert normalized['metadata']['score'] == 150
    assert normalized['metadata']['author'] == 'testuser'


def test_normalize_event_with_complex_html(normalizer):
    """Test normalization with complex HTML structure."""
    raw_event = {
        'source': 'rss',
        'url': 'https://example.com/article',
        'text': '''
            <div class="article">
                <h1>Breaking News</h1>
                <p>Stock market <strong>surges</strong> as Fed announces rate cut.</p>
                <ul>
                    <li>S&P 500 up 2%</li>
                    <li>Nasdaq gains 3%</li>
                </ul>
                <a href="https://link.com">Read more</a>
            </div>
        ''',
        'timestamp': '2024-01-15T10:30:00Z',
        'metadata': {}
    }
    
    normalized = normalizer.normalize_event(raw_event)
    
    assert normalized is not None
    assert '<div' not in normalized['text']
    assert '<h1>' not in normalized['text']
    assert '<strong>' not in normalized['text']
    assert 'Breaking News' in normalized['text']
    assert 'surges' in normalized['text']
    assert 'S&P 500 up 2%' in normalized['text']
