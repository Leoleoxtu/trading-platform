"""
Reddit Collector - Collects posts from financial subreddits.

Monitors wallstreetbets, stocks, and investing subreddits for high-score posts.
Publishes to Kafka and archives to MinIO.
"""

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Optional
from pathlib import Path

import praw
from praw.models import Submission
from aiokafka import AIOKafkaProducer
import boto3
from loguru import logger
from prometheus_client import Counter, Histogram, Gauge

from .base import Collector, RawEvent


# Prometheus metrics
REDDIT_POSTS_FETCHED = Counter(
    'reddit_collector_posts_fetched_total',
    'Total Reddit posts fetched',
    ['subreddit']
)
REDDIT_POSTS_PUBLISHED = Counter(
    'reddit_collector_posts_published_total',
    'Total Reddit posts published to Kafka',
    ['status']
)
REDDIT_FETCH_DURATION = Histogram(
    'reddit_collector_fetch_duration_seconds',
    'Time to fetch Reddit posts',
    ['subreddit']
)
REDDIT_DEDUP_HITS = Counter(
    'reddit_collector_dedup_hits_total',
    'Number of duplicate posts filtered'
)
REDDIT_ACTIVE_SUBREDDITS = Gauge(
    'reddit_collector_active_subreddits',
    'Number of active subreddits being monitored'
)


class RedditCollector(Collector):
    """
    Collector for Reddit posts from financial subreddits.
    
    Features:
    - Monitors multiple subreddits (wallstreetbets, stocks, investing)
    - Filters by minimum score threshold
    - Deduplicates posts using SHA256 hashing
    - Publishes to Kafka topic raw.events.v1
    - Archives to MinIO bucket raw-events/reddit/
    - Exposes Prometheus metrics
    """
    
    def __init__(
        self,
        subreddits: List[str] = None,
        min_score: int = 50,
        kafka_bootstrap_servers: str = "localhost:9092",
        kafka_topic: str = "raw.events.v1",
        minio_endpoint: str = "localhost:9000",
        minio_access_key: str = "minioadmin",
        minio_secret_key: str = "minioadmin",
        minio_bucket: str = "raw-events",
        dedup_state_path: str = "/tmp/reddit_seen_posts.json",
        reddit_client_id: Optional[str] = None,
        reddit_client_secret: Optional[str] = None,
        reddit_user_agent: Optional[str] = None
    ):
        """
        Initialize Reddit collector.
        
        Args:
            subreddits: List of subreddit names to monitor
            min_score: Minimum post score threshold
            kafka_bootstrap_servers: Kafka broker addresses
            kafka_topic: Kafka topic to publish to
            minio_endpoint: MinIO server endpoint
            minio_access_key: MinIO access key
            minio_secret_key: MinIO secret key
            minio_bucket: MinIO bucket name
            dedup_state_path: Path to deduplication state file
            reddit_client_id: Reddit API client ID
            reddit_client_secret: Reddit API client secret
            reddit_user_agent: Reddit API user agent
        """
        self.subreddits = subreddits or ['wallstreetbets', 'stocks', 'investing']
        self.min_score = min_score
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.kafka_topic = kafka_topic
        self.minio_endpoint = minio_endpoint
        self.minio_access_key = minio_access_key
        self.minio_secret_key = minio_secret_key
        self.minio_bucket = minio_bucket
        self.dedup_state_path = Path(dedup_state_path)
        
        # Reddit credentials from env or params
        self.reddit_client_id = reddit_client_id or os.getenv('REDDIT_CLIENT_ID')
        self.reddit_client_secret = reddit_client_secret or os.getenv('REDDIT_CLIENT_SECRET')
        self.reddit_user_agent = reddit_user_agent or os.getenv('REDDIT_USER_AGENT', 'TradingBot/1.0')
        
        # Initialize Reddit client
        if not self.reddit_client_id or not self.reddit_client_secret:
            raise ValueError("Reddit API credentials required. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET")
        
        self.reddit = praw.Reddit(
            client_id=self.reddit_client_id,
            client_secret=self.reddit_client_secret,
            user_agent=self.reddit_user_agent
        )
        
        # Deduplication state
        self.seen_posts: Dict[str, float] = {}
        self._load_dedup_state()
        
        # Running state
        self._running = False
        
        logger.info(
            f"Reddit Collector initialized with {len(self.subreddits)} subreddits, "
            f"min_score={self.min_score}"
        )
        REDDIT_ACTIVE_SUBREDDITS.set(len(self.subreddits))
    
    def _load_dedup_state(self):
        """Load deduplication state from disk."""
        if self.dedup_state_path.exists():
            try:
                with open(self.dedup_state_path, 'r') as f:
                    data = json.load(f)
                    self.seen_posts = data.get('seen_posts', {})
                logger.info(f"Loaded {len(self.seen_posts)} seen posts from state file")
            except Exception as e:
                logger.warning(f"Failed to load dedup state: {e}")
                self.seen_posts = {}
    
    def _save_dedup_state(self):
        """Save deduplication state to disk."""
        try:
            self.dedup_state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.dedup_state_path, 'w') as f:
                json.dump({'seen_posts': self.seen_posts}, f)
        except Exception as e:
            logger.warning(f"Failed to save dedup state: {e}")
    
    def _generate_post_id(self, submission: Submission) -> str:
        """Generate unique ID for a Reddit post."""
        # Use Reddit's internal ID
        return f"reddit_{submission.id}"
    
    def _is_duplicate(self, post_id: str) -> bool:
        """Check if post has been seen before."""
        if post_id in self.seen_posts:
            REDDIT_DEDUP_HITS.inc()
            return True
        return False
    
    def _mark_seen(self, post_id: str):
        """Mark post as seen."""
        self.seen_posts[post_id] = datetime.now(timezone.utc).timestamp()
    
    def _cleanup_old_entries(self, retention_hours: int = 48):
        """Remove old entries from dedup state."""
        cutoff = datetime.now(timezone.utc).timestamp() - (retention_hours * 3600)
        self.seen_posts = {
            k: v for k, v in self.seen_posts.items() 
            if v > cutoff
        }
    
    async def collect(self) -> List[RawEvent]:
        """
        Collect posts from configured subreddits.
        
        Returns:
            List of RawEvent objects
        """
        all_events = []
        
        for subreddit_name in self.subreddits:
            try:
                with REDDIT_FETCH_DURATION.labels(subreddit=subreddit_name).time():
                    # Fetch hot posts from subreddit
                    subreddit = self.reddit.subreddit(subreddit_name)
                    posts = await asyncio.to_thread(
                        lambda: list(subreddit.hot(limit=100))
                    )
                    
                    posts_fetched = 0
                    posts_filtered = 0
                    
                    for submission in posts:
                        # Filter by score threshold
                        if submission.score < self.min_score:
                            continue
                        
                        posts_fetched += 1
                        
                        # Generate post ID
                        post_id = self._generate_post_id(submission)
                        
                        # Skip duplicates
                        if self._is_duplicate(post_id):
                            posts_filtered += 1
                            continue
                        
                        # Mark as seen
                        self._mark_seen(post_id)
                        
                        # Create RawEvent
                        event = RawEvent(
                            source='reddit',
                            url=f"https://reddit.com{submission.permalink}",
                            text=f"{submission.title}\n\n{submission.selftext}",
                            timestamp=datetime.fromtimestamp(
                                submission.created_utc,
                                tz=timezone.utc
                            ).isoformat(),
                            metadata={
                                'subreddit': subreddit_name,
                                'author': str(submission.author),
                                'score': submission.score,
                                'num_comments': submission.num_comments,
                                'upvote_ratio': submission.upvote_ratio,
                                'flair': submission.link_flair_text,
                                'post_id': submission.id,
                                'is_self': submission.is_self,
                                'priority': 'high' if submission.score > 500 else 'medium',
                                'quality': min(10, int(submission.score / 100))
                            }
                        )
                        
                        all_events.append(event)
                    
                    REDDIT_POSTS_FETCHED.labels(subreddit=subreddit_name).inc(posts_fetched)
                    
                    logger.info(
                        f"r/{subreddit_name}: fetched {posts_fetched} posts, "
                        f"filtered {posts_filtered} duplicates, "
                        f"collected {posts_fetched - posts_filtered} new posts"
                    )
                    
            except Exception as e:
                logger.error(f"Error fetching from r/{subreddit_name}: {e}")
                continue
        
        # Cleanup old entries periodically
        self._cleanup_old_entries()
        
        return all_events
    
    async def publish_to_kafka(self, events: List[RawEvent]) -> bool:
        """
        Publish events to Kafka topic.
        
        Args:
            events: List of RawEvent objects
            
        Returns:
            True if successful, False otherwise
        """
        if not events:
            return True
        
        try:
            producer = AIOKafkaProducer(
                bootstrap_servers=self.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            await producer.start()
            
            try:
                for event in events:
                    await producer.send(
                        self.kafka_topic,
                        value=event.to_dict()
                    )
                
                await producer.flush()
                REDDIT_POSTS_PUBLISHED.labels(status='success').inc(len(events))
                logger.info(f"Published {len(events)} Reddit posts to Kafka topic {self.kafka_topic}")
                return True
                
            finally:
                await producer.stop()
                
        except Exception as e:
            logger.error(f"Failed to publish to Kafka: {e}")
            REDDIT_POSTS_PUBLISHED.labels(status='error').inc(len(events))
            return False
    
    async def archive_to_minio(self, events: List[RawEvent]) -> bool:
        """
        Archive events to MinIO in JSONL format.
        
        Args:
            events: List of RawEvent objects
            
        Returns:
            True if successful, False otherwise
        """
        if not events:
            return True
        
        try:
            # Create S3 client
            s3 = boto3.client(
                's3',
                endpoint_url=f'http://{self.minio_endpoint}',
                aws_access_key_id=self.minio_access_key,
                aws_secret_access_key=self.minio_secret_key
            )
            
            # Create JSONL content
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            jsonl_content = '\n'.join(event.to_json() for event in events)
            
            # Upload to MinIO
            object_key = f"reddit/{timestamp}.jsonl"
            s3.put_object(
                Bucket=self.minio_bucket,
                Key=object_key,
                Body=jsonl_content.encode('utf-8')
            )
            
            logger.info(f"Archived {len(events)} Reddit posts to MinIO: {object_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to archive to MinIO: {e}")
            return False
    
    async def run_once(self) -> Dict:
        """
        Run one complete collection cycle.
        
        Returns:
            Statistics dictionary with results
        """
        self.start()
        
        try:
            # Collect events
            events = await self.collect()
            
            # Publish to Kafka
            kafka_success = await self.publish_to_kafka(events)
            
            # Archive to MinIO
            minio_success = await self.archive_to_minio(events)
            
            # Save dedup state
            self._save_dedup_state()
            
            stats = {
                'collected': len(events),
                'published': len(events) if kafka_success else 0,
                'archived': minio_success,
                'errors': []
            }
            
            if not kafka_success:
                stats['errors'].append('Kafka publishing failed')
            if not minio_success:
                stats['errors'].append('MinIO archiving failed')
            
            return stats
            
        finally:
            self.stop()
    
    def start(self):
        """Mark collector as running."""
        self._running = True
        logger.info("Reddit Collector started")
    
    def stop(self):
        """Mark collector as stopped."""
        self._running = False
        logger.info("Reddit Collector stopped")
    
    def is_running(self) -> bool:
        """Check if collector is running."""
        return self._running
