"""
RSS Feed Collector
Collects news from RSS feeds, publishes to Kafka, and archives to MinIO.
"""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Set
from pathlib import Path

import feedparser
import yaml
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
import boto3
from botocore.exceptions import ClientError
from loguru import logger
from prometheus_client import Counter, Histogram, Gauge

from .base import Collector, RawEvent


# Prometheus metrics
FEEDS_PROCESSED = Counter(
    'rss_collector_feeds_processed_total',
    'Total number of RSS feeds processed',
    ['feed_name', 'status']
)

ITEMS_FETCHED = Counter(
    'rss_collector_items_fetched_total',
    'Total number of RSS items fetched',
    ['feed_name']
)

ITEMS_PUBLISHED = Counter(
    'rss_collector_items_published_total',
    'Total number of items published to Kafka',
    ['status']
)

FETCH_DURATION = Histogram(
    'rss_collector_fetch_duration_seconds',
    'Time spent fetching RSS feed',
    ['feed_name']
)

DEDUP_HITS = Counter(
    'rss_collector_dedup_hits_total',
    'Number of duplicate items filtered'
)

ACTIVE_FEEDS = Gauge(
    'rss_collector_active_feeds',
    'Number of active RSS feeds'
)


class RSSCollector(Collector):
    """
    RSS Feed Collector
    
    Fetches news from configured RSS feeds, deduplicates, publishes to Kafka,
    and archives to MinIO.
    """
    
    def __init__(
        self,
        config_path: str = "config/rss_sources.yaml",
        kafka_bootstrap_servers: str = "localhost:9092",
        kafka_topic: str = "raw.events.v1",
        minio_endpoint: str = "localhost:9000",
        minio_access_key: str = "minioadmin",
        minio_secret_key: str = "minioadmin123",
        minio_bucket: str = "raw-events",
        dedup_state_file: str = "/tmp/rss_seen_items.json"
    ):
        """
        Initialize RSS Collector.
        
        Args:
            config_path: Path to RSS sources YAML config
            kafka_bootstrap_servers: Kafka broker addresses
            kafka_topic: Kafka topic for raw events
            minio_endpoint: MinIO endpoint
            minio_access_key: MinIO access key
            minio_secret_key: MinIO secret key
            minio_bucket: MinIO bucket name
            dedup_state_file: Path to deduplication state file
        """
        super().__init__("rss_collector")
        
        self.config_path = config_path
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.kafka_topic = kafka_topic
        self.minio_endpoint = minio_endpoint
        self.minio_access_key = minio_access_key
        self.minio_secret_key = minio_secret_key
        self.minio_bucket = minio_bucket
        self.dedup_state_file = dedup_state_file
        
        # State
        self.feeds: List[Dict] = []
        self.seen_items: Set[str] = set()
        self.kafka_producer: Optional[AIOKafkaProducer] = None
        self.s3_client = None
        
        # Load configuration
        self._load_config()
        self._load_dedup_state()
        self._init_minio()
    
    def _load_config(self):
        """Load RSS sources from YAML config."""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
                self.feeds = config.get('sources', [])
                ACTIVE_FEEDS.set(len(self.feeds))
                logger.info(f"Loaded {len(self.feeds)} RSS feeds from {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load RSS config: {e}")
            self.feeds = []
    
    def _load_dedup_state(self):
        """Load seen items from state file."""
        try:
            state_path = Path(self.dedup_state_file)
            if state_path.exists():
                with open(state_path, 'r') as f:
                    data = json.load(f)
                    self.seen_items = set(data.get('seen_items', []))
                    logger.info(f"Loaded {len(self.seen_items)} seen items from state")
        except Exception as e:
            logger.warning(f"Could not load dedup state: {e}")
            self.seen_items = set()
    
    def _save_dedup_state(self):
        """Save seen items to state file."""
        try:
            state_path = Path(self.dedup_state_file)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Keep only last 10,000 items to prevent unbounded growth
            if len(self.seen_items) > 10000:
                self.seen_items = set(list(self.seen_items)[-10000:])
            
            with open(state_path, 'w') as f:
                json.dump({'seen_items': list(self.seen_items)}, f)
        except Exception as e:
            logger.error(f"Failed to save dedup state: {e}")
    
    def _init_minio(self):
        """Initialize MinIO/S3 client."""
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=f'http://{self.minio_endpoint}',
                aws_access_key_id=self.minio_access_key,
                aws_secret_access_key=self.minio_secret_key
            )
            # Test connection
            self.s3_client.head_bucket(Bucket=self.minio_bucket)
            logger.info(f"Connected to MinIO bucket: {self.minio_bucket}")
        except Exception as e:
            logger.error(f"Failed to initialize MinIO: {e}")
            self.s3_client = None
    
    def _generate_item_id(self, feed_name: str, item_link: str, item_title: str) -> str:
        """Generate unique ID for RSS item."""
        content = f"{feed_name}:{item_link}:{item_title}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _is_duplicate(self, item_id: str) -> bool:
        """Check if item has been seen before."""
        if item_id in self.seen_items:
            DEDUP_HITS.inc()
            return True
        return False
    
    async def collect(self) -> List[RawEvent]:
        """
        Collect raw events from RSS feeds.
        
        Returns:
            List of RawEvent objects
        """
        all_events = []
        
        for feed_config in self.feeds:
            feed_name = feed_config.get('name', 'unknown')
            feed_url = feed_config.get('url')
            priority = feed_config.get('priority', 'medium')
            quality = feed_config.get('quality', 5)
            
            if not feed_url:
                logger.warning(f"Feed {feed_name} has no URL, skipping")
                continue
            
            try:
                # Fetch feed with timing
                with FETCH_DURATION.labels(feed_name=feed_name).time():
                    feed = await asyncio.to_thread(feedparser.parse, feed_url)
                
                if feed.bozo:
                    logger.warning(f"Feed {feed_name} parse error: {feed.bozo_exception}")
                    FEEDS_PROCESSED.labels(feed_name=feed_name, status='error').inc()
                    continue
                
                # Process entries
                feed_events = []
                for entry in feed.entries:
                    item_link = entry.get('link', '')
                    item_title = entry.get('title', '')
                    item_summary = entry.get('summary', entry.get('description', ''))
                    
                    # Generate ID and check for duplicates
                    item_id = self._generate_item_id(feed_name, item_link, item_title)
                    if self._is_duplicate(item_id):
                        continue
                    
                    # Parse timestamp
                    published = entry.get('published_parsed')
                    if published:
                        timestamp = datetime(*published[:6], tzinfo=timezone.utc).isoformat()
                    else:
                        timestamp = datetime.now(timezone.utc).isoformat()
                    
                    # Create RawEvent
                    event = RawEvent(
                        source='rss',
                        url=item_link,
                        text=f"{item_title}\n\n{item_summary}",
                        timestamp=timestamp,
                        metadata={
                            'feed_name': feed_name,
                            'feed_url': feed_url,
                            'priority': priority,
                            'quality': quality,
                            'item_id': item_id,
                            'author': entry.get('author', ''),
                            'tags': [tag.get('term', '') for tag in entry.get('tags', [])]
                        }
                    )
                    
                    feed_events.append(event)
                    self.seen_items.add(item_id)
                
                ITEMS_FETCHED.labels(feed_name=feed_name).inc(len(feed_events))
                FEEDS_PROCESSED.labels(feed_name=feed_name, status='success').inc()
                
                logger.info(f"Feed {feed_name}: fetched {len(feed_events)} new items")
                all_events.extend(feed_events)
                
            except Exception as e:
                logger.error(f"Error processing feed {feed_name}: {e}")
                FEEDS_PROCESSED.labels(feed_name=feed_name, status='error').inc()
        
        # Save dedup state
        self._save_dedup_state()
        
        return all_events
    
    async def publish_to_kafka(self, events: List[RawEvent]) -> int:
        """
        Publish events to Kafka topic.
        
        Args:
            events: List of RawEvent objects
            
        Returns:
            Number of successfully published events
        """
        if not events:
            return 0
        
        try:
            # Initialize producer if needed
            if self.kafka_producer is None:
                self.kafka_producer = AIOKafkaProducer(
                    bootstrap_servers=self.kafka_bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8')
                )
                await self.kafka_producer.start()
                logger.info("Kafka producer started")
            
            published_count = 0
            for event in events:
                try:
                    await self.kafka_producer.send_and_wait(
                        self.kafka_topic,
                        value=event.to_dict()
                    )
                    published_count += 1
                    ITEMS_PUBLISHED.labels(status='success').inc()
                except KafkaError as e:
                    logger.error(f"Failed to publish event to Kafka: {e}")
                    ITEMS_PUBLISHED.labels(status='error').inc()
            
            logger.info(f"Published {published_count}/{len(events)} events to Kafka")
            return published_count
            
        except Exception as e:
            logger.error(f"Kafka publish error: {e}")
            ITEMS_PUBLISHED.labels(status='error').inc(len(events))
            return 0
    
    async def archive_to_minio(self, events: List[RawEvent]) -> bool:
        """
        Archive events to MinIO/S3.
        
        Args:
            events: List of RawEvent objects
            
        Returns:
            True if archiving succeeded
        """
        if not events or not self.s3_client:
            return False
        
        try:
            # Create archive file
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            key = f"rss/{timestamp}.jsonl"
            
            # Create JSONL content
            content = "\n".join([event.to_json() for event in events])
            
            # Upload to MinIO
            await asyncio.to_thread(
                self.s3_client.put_object,
                Bucket=self.minio_bucket,
                Key=key,
                Body=content.encode('utf-8'),
                ContentType='application/x-ndjson'
            )
            
            logger.info(f"Archived {len(events)} events to MinIO: {key}")
            return True
            
        except ClientError as e:
            logger.error(f"MinIO archive error: {e}")
            return False
    
    async def stop(self):
        """Stop the collector gracefully."""
        await super().stop()
        
        # Close Kafka producer
        if self.kafka_producer:
            await self.kafka_producer.stop()
            logger.info("Kafka producer stopped")
