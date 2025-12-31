"""
Unit tests for Reddit Collector.
Tests Reddit post collection, filtering, deduplication, and publishing.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
import json
import tempfile

from src.ingestion.reddit_collector import RedditCollector
from src.ingestion.base import RawEvent


@pytest.fixture
def temp_state_file():
    """Create temporary state file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def mock_reddit_credentials():
    """Mock Reddit API credentials."""
    return {
        'reddit_client_id': 'test_client_id',
        'reddit_client_secret': 'test_client_secret',
        'reddit_user_agent': 'TestBot/1.0'
    }


@pytest.fixture
def mock_submission():
    """Create mock Reddit submission."""
    mock = Mock()
    mock.id = 'abc123'
    mock.title = 'AAPL to the moon! 🚀'
    mock.selftext = 'Technical analysis shows strong bullish signals.'
    mock.permalink = '/r/wallstreetbets/comments/abc123/aapl_moon'
    mock.created_utc = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc).timestamp()
    mock.author = 'DeepValue'
    mock.score = 150
    mock.num_comments = 45
    mock.upvote_ratio = 0.85
    mock.link_flair_text = 'DD'
    mock.is_self = True
    return mock


@pytest.mark.asyncio
async def test_reddit_collector_init(mock_reddit_credentials, temp_state_file):
    """Test RedditCollector initialization."""
    with patch('src.ingestion.reddit_collector.praw.Reddit'):
        collector = RedditCollector(
            dedup_state_path=temp_state_file,
            **mock_reddit_credentials
        )
        
        assert collector.subreddits == ['wallstreetbets', 'stocks', 'investing']
        assert collector.min_score == 50
        assert not collector.is_running()


@pytest.mark.asyncio
async def test_generate_post_id(mock_reddit_credentials, temp_state_file, mock_submission):
    """Test post ID generation."""
    with patch('src.ingestion.reddit_collector.praw.Reddit'):
        collector = RedditCollector(
            dedup_state_path=temp_state_file,
            **mock_reddit_credentials
        )
        
        post_id = collector._generate_post_id(mock_submission)
        assert post_id == 'reddit_abc123'


@pytest.mark.asyncio
async def test_deduplication(mock_reddit_credentials, temp_state_file, mock_submission):
    """Test post deduplication."""
    with patch('src.ingestion.reddit_collector.praw.Reddit'):
        collector = RedditCollector(
            dedup_state_path=temp_state_file,
            **mock_reddit_credentials
        )
        
        post_id = collector._generate_post_id(mock_submission)
        
        # First check - not duplicate
        assert not collector._is_duplicate(post_id)
        
        # Mark as seen
        collector._mark_seen(post_id)
        
        # Second check - is duplicate
        assert collector._is_duplicate(post_id)


@pytest.mark.asyncio
async def test_dedup_state_persistence(mock_reddit_credentials, temp_state_file):
    """Test deduplication state save and load."""
    with patch('src.ingestion.reddit_collector.praw.Reddit'):
        # Create collector and mark posts as seen
        collector1 = RedditCollector(
            dedup_state_path=temp_state_file,
            **mock_reddit_credentials
        )
        collector1._mark_seen('reddit_post1')
        collector1._mark_seen('reddit_post2')
        collector1._save_dedup_state()
        
        # Create new collector and verify state loaded
        collector2 = RedditCollector(
            dedup_state_path=temp_state_file,
            **mock_reddit_credentials
        )
        
        assert 'reddit_post1' in collector2.seen_posts
        assert 'reddit_post2' in collector2.seen_posts


@pytest.mark.asyncio
async def test_collect_posts(mock_reddit_credentials, temp_state_file, mock_submission):
    """Test collecting Reddit posts."""
    with patch('src.ingestion.reddit_collector.praw.Reddit') as mock_reddit_class:
        # Setup mock
        mock_reddit = Mock()
        mock_subreddit = Mock()
        mock_subreddit.hot.return_value = [mock_submission]
        mock_reddit.subreddit.return_value = mock_subreddit
        mock_reddit_class.return_value = mock_reddit
        
        collector = RedditCollector(
            subreddits=['wallstreetbets'],
            min_score=50,
            dedup_state_path=temp_state_file,
            **mock_reddit_credentials
        )
        
        # Collect posts
        events = await collector.collect()
        
        # Verify
        assert len(events) == 1
        assert events[0].source == 'reddit'
        assert events[0].metadata['subreddit'] == 'wallstreetbets'
        assert events[0].metadata['score'] == 150
        assert 'AAPL to the moon!' in events[0].text


@pytest.mark.asyncio
async def test_score_filtering(mock_reddit_credentials, temp_state_file):
    """Test filtering posts by score threshold."""
    with patch('src.ingestion.reddit_collector.praw.Reddit') as mock_reddit_class:
        # Create submissions with different scores
        high_score_post = Mock()
        high_score_post.id = 'high1'
        high_score_post.score = 150
        high_score_post.title = 'High score post'
        high_score_post.selftext = 'Content'
        high_score_post.permalink = '/r/test/high1'
        high_score_post.created_utc = datetime.now(timezone.utc).timestamp()
        high_score_post.author = 'user1'
        high_score_post.num_comments = 10
        high_score_post.upvote_ratio = 0.9
        high_score_post.link_flair_text = None
        high_score_post.is_self = True
        
        low_score_post = Mock()
        low_score_post.id = 'low1'
        low_score_post.score = 25
        low_score_post.title = 'Low score post'
        low_score_post.selftext = 'Content'
        low_score_post.permalink = '/r/test/low1'
        low_score_post.created_utc = datetime.now(timezone.utc).timestamp()
        low_score_post.author = 'user2'
        low_score_post.num_comments = 2
        low_score_post.upvote_ratio = 0.6
        low_score_post.link_flair_text = None
        low_score_post.is_self = True
        
        # Setup mock
        mock_reddit = Mock()
        mock_subreddit = Mock()
        mock_subreddit.hot.return_value = [high_score_post, low_score_post]
        mock_reddit.subreddit.return_value = mock_subreddit
        mock_reddit_class.return_value = mock_reddit
        
        collector = RedditCollector(
            subreddits=['test'],
            min_score=50,
            dedup_state_path=temp_state_file,
            **mock_reddit_credentials
        )
        
        # Collect posts
        events = await collector.collect()
        
        # Only high score post should be collected
        assert len(events) == 1
        assert events[0].metadata['post_id'] == 'high1'


@pytest.mark.asyncio
async def test_publish_to_kafka(mock_reddit_credentials, temp_state_file):
    """Test publishing posts to Kafka."""
    with patch('src.ingestion.reddit_collector.praw.Reddit'), \
         patch('src.ingestion.reddit_collector.AIOKafkaProducer') as mock_producer_class:
        
        # Setup mock producer
        mock_producer = AsyncMock()
        mock_producer_class.return_value = mock_producer
        
        collector = RedditCollector(
            dedup_state_path=temp_state_file,
            **mock_reddit_credentials
        )
        
        # Create test events
        events = [
            RawEvent(
                source='reddit',
                url='https://reddit.com/r/test/1',
                text='Test post',
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={'subreddit': 'test'}
            )
        ]
        
        # Publish
        success = await collector.publish_to_kafka(events)
        
        # Verify
        assert success
        mock_producer.start.assert_called_once()
        mock_producer.send.assert_called_once()
        mock_producer.flush.assert_called_once()
        mock_producer.stop.assert_called_once()


@pytest.mark.asyncio
async def test_archive_to_minio(mock_reddit_credentials, temp_state_file):
    """Test archiving posts to MinIO."""
    with patch('src.ingestion.reddit_collector.praw.Reddit'), \
         patch('src.ingestion.reddit_collector.boto3.client') as mock_s3:
        
        mock_s3_client = Mock()
        mock_s3.return_value = mock_s3_client
        
        collector = RedditCollector(
            dedup_state_path=temp_state_file,
            **mock_reddit_credentials
        )
        
        # Create test events
        events = [
            RawEvent(
                source='reddit',
                url='https://reddit.com/r/test/1',
                text='Test post',
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={'subreddit': 'test'}
            )
        ]
        
        # Archive
        success = await collector.archive_to_minio(events)
        
        # Verify
        assert success
        mock_s3_client.put_object.assert_called_once()
        call_args = mock_s3_client.put_object.call_args
        assert call_args[1]['Bucket'] == 'raw-events'
        assert 'reddit/' in call_args[1]['Key']


@pytest.mark.asyncio
async def test_run_once_integration(mock_reddit_credentials, temp_state_file, mock_submission):
    """Test complete run_once cycle."""
    with patch('src.ingestion.reddit_collector.praw.Reddit') as mock_reddit_class, \
         patch('src.ingestion.reddit_collector.AIOKafkaProducer') as mock_producer_class, \
         patch('src.ingestion.reddit_collector.boto3.client') as mock_s3:
        
        # Setup mocks
        mock_reddit = Mock()
        mock_subreddit = Mock()
        mock_subreddit.hot.return_value = [mock_submission]
        mock_reddit.subreddit.return_value = mock_subreddit
        mock_reddit_class.return_value = mock_reddit
        
        mock_producer = AsyncMock()
        mock_producer_class.return_value = mock_producer
        
        mock_s3_client = Mock()
        mock_s3.return_value = mock_s3_client
        
        collector = RedditCollector(
            subreddits=['wallstreetbets'],
            dedup_state_path=temp_state_file,
            **mock_reddit_credentials
        )
        
        # Run cycle
        stats = await collector.run_once()
        
        # Verify stats
        assert stats['collected'] == 1
        assert stats['published'] == 1
        assert stats['archived'] is True
        assert len(stats['errors']) == 0


@pytest.mark.asyncio
async def test_error_handling_invalid_subreddit(mock_reddit_credentials, temp_state_file):
    """Test error handling for invalid subreddit."""
    with patch('src.ingestion.reddit_collector.praw.Reddit') as mock_reddit_class:
        # Setup mock to raise exception
        mock_reddit = Mock()
        mock_reddit.subreddit.side_effect = Exception("Subreddit not found")
        mock_reddit_class.return_value = mock_reddit
        
        collector = RedditCollector(
            subreddits=['invalid_subreddit_xyz'],
            dedup_state_path=temp_state_file,
            **mock_reddit_credentials
        )
        
        # Should not raise exception, just return empty list
        events = await collector.collect()
        assert events == []
