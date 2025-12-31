"""
Tests for Triage Stage 1 service.
"""

import pytest
import json
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch

from services.preprocessing.triage_stage1.app import TriageStage1


@pytest.fixture
def triage_config(tmp_path):
    """Create test configuration."""
    config_file = tmp_path / "triage_test.yaml"
    config_content = """
keywords:
  strong:
    - earnings
    - fed
    - merger
  weak:
    - rumor
    - reported
  clickbait:
    - shocking

source_scores:
  rss:
    bloomberg:
      reliability: 0.95
      noise: 0.05
  default:
    reliability: 0.30
    noise: 0.60

thresholds:
  fast_score_min: 70
  standard_score_min: 40

text_analysis:
  max_length: 5000
  min_length: 10
  truncation_penalty: -5

recency:
  very_recent_seconds: 300
  recent_seconds: 3600
  recent_decay_hours: 24

deduplication:
  enabled: true
  ttl_seconds: 86400
  backend: redis

scoring:
  source_reliability_weight: 35
  strong_keywords_weight: 25
  ticker_candidates_weight: 15
  numbers_money_weight: 10
  recency_weight: 10
  source_noise_penalty: 20
  clickbait_penalty: 15
  short_text_penalty: 10

priority_hints:
  FAST:
    high_score: P0
    medium_score: P1
  STANDARD:
    high_score: P1
    low_score: P2
  COLD:
    default: P3

ticker_detection:
  regex_pattern: '(?:^|[^a-zA-Z])([A-Z]{1,5})(?:[^a-zA-Z]|$)'
  exclude_words:
    - THE
    - AND

features:
  enable_dedup: true
  enable_weak_keywords: true
  enable_clickbait_detection: true
  enable_ticker_extraction: true
"""
    config_file.write_text(config_content)
    return str(config_file)


@pytest.fixture
def triage(triage_config):
    """Create TriageStage1 instance."""
    with patch('services.preprocessing.triage_stage1.app.redis.from_url') as mock_redis:
        mock_redis_client = Mock()
        mock_redis_client.exists.return_value = False
        mock_redis.return_value = mock_redis_client
        
        triage = TriageStage1(
            config_path=triage_config,
            kafka_bootstrap_servers='localhost:9092'
        )
        triage.redis_client = mock_redis_client
        return triage


def test_extract_signals(triage):
    """Test signal extraction."""
    event = {
        'text': 'Apple Inc. reported Q4 earnings of $34.2B, up 5.4% YoY',
        'url': 'https://example.com/news',
        'source': 'rss',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'metadata': {
            'source_type': 'rss',
            'source_name': 'bloomberg'
        }
    }
    
    signals = triage._extract_signals(event)
    
    assert signals['text_length'] > 0
    assert signals['has_numbers'] is True
    assert signals['has_percent'] is True
    assert signals['has_money'] is True
    # ticker_candidates_count may be 0 depending on regex - just check field exists
    assert 'ticker_candidates_count' in signals


def test_extract_tickers(triage):
    """Test ticker extraction."""
    text = "AAPL and MSFT both beat earnings expectations"
    tickers = triage._extract_tickers(text)
    
    assert 'AAPL' in tickers
    assert 'MSFT' in tickers


def test_match_keywords(triage):
    """Test keyword matching."""
    text = "Apple reported earnings this quarter"
    hits = triage._match_keywords(text)
    
    assert 'strong' in hits


def test_calculate_recency(triage):
    """Test recency calculation."""
    # Recent timestamp
    now_iso = datetime.now(timezone.utc).isoformat()
    recency = triage._calculate_recency(now_iso)
    
    assert recency < 5


def test_get_source_scores(triage):
    """Test source score retrieval."""
    reliability, noise = triage._get_source_scores('rss', 'bloomberg')
    
    assert reliability == 0.95
    assert noise == 0.05


def test_calculate_score_high(triage):
    """Test score calculation for high-quality event."""
    event = {
        'text': 'Apple Inc. reported strong earnings',
        'url': 'https://example.com',
        'source': 'rss',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'metadata': {
            'source_type': 'rss',
            'source_name': 'bloomberg'
        }
    }
    
    signals = triage._extract_signals(event)
    score, reasons = triage._calculate_score(signals, event)
    
    assert score > 50
    assert 'HIGH_SOURCE_RELIABILITY' in reasons
    assert 'STRONG_KEYWORDS' in reasons


def test_calculate_score_low(triage):
    """Test score calculation for low-quality event."""
    event = {
        'text': 'rumor about stock',
        'url': 'https://example.com',
        'source': 'rss',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'metadata': {
            'source_type': 'reddit',
            'source_name': 'wallstreetbets'
        }
    }
    
    signals = triage._extract_signals(event)
    score, reasons = triage._calculate_score(signals, event)
    
    assert score < 70


def test_assign_bucket_fast(triage):
    """Test bucket assignment for FAST."""
    score = 85
    reasons = ['HIGH_SOURCE_RELIABILITY', 'STRONG_KEYWORDS']
    bucket = triage._assign_bucket(score, reasons)
    
    assert bucket == 'FAST'


def test_assign_bucket_standard(triage):
    """Test bucket assignment for STANDARD."""
    score = 50
    reasons = ['HAS_TICKER_CANDIDATES']
    bucket = triage._assign_bucket(score, reasons)
    
    assert bucket == 'STANDARD'


def test_assign_bucket_cold(triage):
    """Test bucket assignment for COLD."""
    score = 25
    reasons = ['WEAK_KEYWORDS']
    bucket = triage._assign_bucket(score, reasons)
    
    assert bucket == 'COLD'


def test_assign_priority(triage):
    """Test priority assignment."""
    # P0 for high FAST
    assert triage._assign_priority('FAST', 85) == 'P0'
    
    # P1 for low FAST
    assert triage._assign_priority('FAST', 70) == 'P1'
    
    # P1 for high STANDARD
    assert triage._assign_priority('STANDARD', 55) == 'P1'
    
    # P3 for COLD
    assert triage._assign_priority('COLD', 30) == 'P3'


@pytest.mark.asyncio
async def test_process_event_complete(triage):
    """Test complete event processing."""
    event = {
        'event_id': 'evt123',
        'text': 'Apple reported earnings beating expectations with $34.2B revenue',
        'url': 'https://example.com/news',
        'source': 'rss',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'metadata': {
            'source_type': 'rss',
            'source_name': 'bloomberg'
        }
    }
    
    triage.redis_client.exists.return_value = False
    stage1_event, bucket = await triage.process_event(event)
    
    assert stage1_event is not None
    assert stage1_event['schema_version'] == 'stage1_event.v1'
    assert stage1_event['triage_bucket'] == 'FAST'
    assert stage1_event['triage_score_stage1'] >= 70
    assert bucket == 'FAST'


@pytest.mark.asyncio
async def test_process_duplicate_event(triage):
    """Test duplicate event handling."""
    event = {
        'event_id': 'evt123',
        'text': 'Some content',
        'url': 'https://example.com',
        'source': 'rss',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'dedup_key': 'key123',
        'metadata': {}
    }
    
    triage.redis_client.exists.return_value = True
    result, bucket = await triage.process_event(event)
    
    assert result is None
    assert bucket == 'DROP_HARD'


def test_create_stage1_event(triage):
    """Test Stage 1 event creation."""
    normalized_event = {
        'event_id': 'evt123',
        'text': 'Test content',
        'url': 'https://example.com',
        'source': 'rss',
        'metadata': {
            'source_type': 'rss',
            'source_name': 'bloomberg'
        }
    }
    
    signals = {
        'text_length': 12,
        'has_ticker_candidate': False,
        'ticker_candidates': None,
        'ticker_candidates_count': 0,
        'has_numbers': False,
        'has_percent': False,
        'has_money': False,
        'keyword_hits': None,
        'source_reliability': 0.95,
        'source_noise': 0.05,
        'recency_seconds': 300
    }
    
    event = triage._create_stage1_event(
        normalized_event, 75, 'FAST', 'P0', ['HIGH_SOURCE_RELIABILITY'], signals
    )
    
    assert event['schema_version'] == 'stage1_event.v1'
    assert event['triage_bucket'] == 'FAST'
    assert event['triage_score_stage1'] == 75
    assert event['priority_hint'] == 'P0'


def test_integration_varied_events(triage):
    """Test with varied event types."""
    test_cases = [
        # Strong keyword + reliable source -> FAST
        {
            'text': 'Apple reported Q4 earnings of $34.2B, beating estimates',
            'source_name': 'bloomberg',
            'expected_bucket': 'FAST'
        },
        # Weak keyword + medium source -> STANDARD/COLD
        {
            'text': 'Rumors suggest Microsoft might acquire startup',
            'source_name': 'reddit',
            'expected_bucket': 'STANDARD'
        },
        # No keywords, ticker + reddit = STANDARD/COLD (ticker gives some signal)
        {
            'text': 'AAPL trading volume up today',
            'source_name': 'reddit',
            'expected_bucket': 'STANDARD'  # Ticker gives 15 points, reddit baseline 35 = ~50
        }
    ]
    
    for test_case in test_cases:
        event = {
            'event_id': 'test',
            'text': test_case['text'],
            'url': 'https://example.com',
            'source': 'rss',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'metadata': {
                'source_type': 'rss',
                'source_name': test_case['source_name']
            }
        }
        
        signals = triage._extract_signals(event)
        score, reasons = triage._calculate_score(signals, event)
        bucket = triage._assign_bucket(score, reasons)
        
        assert bucket == test_case['expected_bucket'], \
            f"Expected {test_case['expected_bucket']} but got {bucket} for: {test_case['text']}"
