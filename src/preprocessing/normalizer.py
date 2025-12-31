"""
Normalizer - Cleans and normalizes raw events from Kafka.

Consumes from raw.events.v1, performs text cleaning, deduplication,
and publishes to events.normalized.v1 for downstream processing.
"""

import asyncio
import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Dict, List, Optional
from html import unescape

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
import redis
from loguru import logger
from prometheus_client import Counter, Histogram, Gauge
from bs4 import BeautifulSoup


# Prometheus metrics
EVENTS_CONSUMED = Counter(
    'normalizer_events_consumed_total',
    'Total events consumed from Kafka'
)
EVENTS_NORMALIZED = Counter(
    'normalizer_events_normalized_total',
    'Total events normalized',
    ['source']
)
EVENTS_DEDUPLICATED = Counter(
    'normalizer_events_deduplicated_total',
    'Total duplicate events filtered'
)
EVENTS_PUBLISHED = Counter(
    'normalizer_events_published_total',
    'Total normalized events published',
    ['status']
)
NORMALIZATION_DURATION = Histogram(
    'normalizer_duration_seconds',
    'Time to normalize an event'
)
NORMALIZER_LAG = Gauge(
    'normalizer_consumer_lag',
    'Kafka consumer lag'
)


class Normalizer:
    """
    Event normalizer with text cleaning and deduplication.
    
    Features:
    - Strips HTML tags
    - Normalizes Unicode characters
    - Removes URLs
    - Converts timestamps to UTC
    - Bloom filter deduplication via Redis
    - Publishes to normalized events topic
    """
    
    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        input_topic: str = "raw.events.v1",
        output_topic: str = "events.normalized.v1",
        consumer_group: str = "normalizer-group",
        redis_url: str = "redis://localhost:6379",
        dedup_ttl: int = 172800  # 48 hours
    ):
        """
        Initialize Normalizer.
        
        Args:
            kafka_bootstrap_servers: Kafka broker addresses
            input_topic: Input Kafka topic
            output_topic: Output Kafka topic
            consumer_group: Kafka consumer group
            redis_url: Redis connection URL
            dedup_ttl: Deduplication TTL in seconds (default 48h)
        """
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.input_topic = input_topic
        self.output_topic = output_topic
        self.consumer_group = consumer_group
        self.redis_url = redis_url
        self.dedup_ttl = dedup_ttl
        
        # Redis client for deduplication
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        
        # Running state
        self._running = False
        
        logger.info(
            f"Normalizer initialized: {input_topic} -> {output_topic}, "
            f"dedup_ttl={dedup_ttl}s"
        )
    
    def _generate_content_hash(self, text: str) -> str:
        """
        Generate SHA256 hash of content for deduplication.
        
        Args:
            text: Text content
            
        Returns:
            Hash string
        """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def _is_duplicate(self, content_hash: str) -> bool:
        """
        Check if content hash exists in Redis (Bloom filter).
        
        Args:
            content_hash: Content hash
            
        Returns:
            True if duplicate, False otherwise
        """
        try:
            key = f"dedup:{content_hash}"
            exists = self.redis_client.exists(key)
            
            if exists:
                EVENTS_DEDUPLICATED.inc()
                return True
            
            # Mark as seen
            self.redis_client.setex(key, self.dedup_ttl, "1")
            return False
            
        except Exception as e:
            logger.error(f"Redis dedup check failed: {e}")
            # If Redis fails, don't block processing
            return False
    
    def _strip_html(self, text: str) -> str:
        """
        Remove HTML tags from text.
        
        Args:
            text: Input text
            
        Returns:
            Text without HTML tags
        """
        try:
            # Unescape HTML entities
            text = unescape(text)
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(text, 'html.parser')
            
            # Get text content
            clean_text = soup.get_text(separator=' ', strip=True)
            
            return clean_text
            
        except Exception as e:
            logger.warning(f"HTML stripping failed: {e}")
            return text
    
    def _normalize_unicode(self, text: str) -> str:
        """
        Normalize Unicode characters to NFKC form.
        
        Args:
            text: Input text
            
        Returns:
            Normalized text
        """
        try:
            # Normalize to NFKC (compatibility decomposition + canonical composition)
            normalized = unicodedata.normalize('NFKC', text)
            
            # Remove zero-width characters
            normalized = re.sub(r'[\u200b-\u200f\u202a-\u202e]', '', normalized)
            
            return normalized
            
        except Exception as e:
            logger.warning(f"Unicode normalization failed: {e}")
            return text
    
    def _remove_urls(self, text: str) -> str:
        """
        Remove URLs from text.
        
        Args:
            text: Input text
            
        Returns:
            Text without URLs
        """
        try:
            # Remove http/https URLs
            text = re.sub(r'https?://\S+', '', text)
            
            # Remove www URLs
            text = re.sub(r'www\.\S+', '', text)
            
            # Clean up extra whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            
            return text
            
        except Exception as e:
            logger.warning(f"URL removal failed: {e}")
            return text
    
    def _normalize_timestamp(self, timestamp_str: str) -> str:
        """
        Convert timestamp to UTC ISO 8601 format.
        
        Args:
            timestamp_str: Timestamp string (various formats)
            
        Returns:
            UTC ISO 8601 timestamp
        """
        try:
            # Try parsing ISO 8601
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            
            # Convert to UTC if not already
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            
            return dt.isoformat()
            
        except Exception as e:
            logger.warning(f"Timestamp normalization failed: {e}")
            # Return current UTC time as fallback
            return datetime.now(timezone.utc).isoformat()
    
    def normalize_event(self, raw_event: Dict) -> Optional[Dict]:
        """
        Normalize a raw event.
        
        Args:
            raw_event: Raw event dictionary
            
        Returns:
            Normalized event dictionary or None if duplicate
        """
        try:
            with NORMALIZATION_DURATION.time():
                # Extract fields
                source = raw_event.get('source', '')
                url = raw_event.get('url', '')
                text = raw_event.get('text', '')
                timestamp = raw_event.get('timestamp', '')
                metadata = raw_event.get('metadata', {})
                
                # Check for duplicate before processing
                content_hash = self._generate_content_hash(text)
                if self._is_duplicate(content_hash):
                    logger.debug(f"Duplicate event filtered: {url}")
                    return None
                
                # Clean text
                clean_text = text
                clean_text = self._strip_html(clean_text)
                clean_text = self._normalize_unicode(clean_text)
                clean_text = self._remove_urls(clean_text)
                
                # Skip if text is too short after cleaning
                if len(clean_text.strip()) < 10:
                    logger.debug(f"Event text too short after cleaning: {url}")
                    return None
                
                # Normalize timestamp
                normalized_timestamp = self._normalize_timestamp(timestamp)
                
                # Create normalized event
                normalized_event = {
                    'event_id': content_hash[:16],  # Short ID for reference
                    'source': source,
                    'url': url,
                    'text': clean_text,
                    'text_length': len(clean_text),
                    'timestamp': normalized_timestamp,
                    'processed_at': datetime.now(timezone.utc).isoformat(),
                    'metadata': metadata,
                    'content_hash': content_hash
                }
                
                EVENTS_NORMALIZED.labels(source=source).inc()
                
                return normalized_event
                
        except Exception as e:
            logger.error(f"Event normalization failed: {e}")
            return None
    
    async def consume_and_normalize(self):
        """
        Consume events from Kafka, normalize, and publish to output topic.
        """
        consumer = AIOKafkaConsumer(
            self.input_topic,
            bootstrap_servers=self.kafka_bootstrap_servers,
            group_id=self.consumer_group,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            enable_auto_commit=True,
            auto_commit_interval_ms=5000
        )
        
        producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        await consumer.start()
        await producer.start()
        
        logger.info(f"Started consuming from {self.input_topic}")
        
        try:
            async for msg in consumer:
                if not self._running:
                    break
                
                try:
                    EVENTS_CONSUMED.inc()
                    
                    # Normalize event
                    raw_event = msg.value
                    normalized_event = self.normalize_event(raw_event)
                    
                    # Skip duplicates and invalid events
                    if normalized_event is None:
                        continue
                    
                    # Publish to output topic
                    await producer.send(
                        self.output_topic,
                        value=normalized_event
                    )
                    
                    EVENTS_PUBLISHED.labels(status='success').inc()
                    
                    logger.debug(
                        f"Normalized and published event: "
                        f"{normalized_event['event_id']} from {normalized_event['source']}"
                    )
                    
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    EVENTS_PUBLISHED.labels(status='error').inc()
                    continue
                
        finally:
            await consumer.stop()
            await producer.stop()
            logger.info("Stopped consuming")
    
    async def run(self):
        """
        Run the normalizer.
        """
        self._running = True
        logger.info("Normalizer started")
        
        try:
            await self.consume_and_normalize()
        except Exception as e:
            logger.error(f"Normalizer error: {e}")
        finally:
            self._running = False
            logger.info("Normalizer stopped")
    
    def start(self):
        """Mark normalizer as running."""
        self._running = True
    
    def stop(self):
        """Stop the normalizer."""
        self._running = False
    
    def is_running(self) -> bool:
        """Check if normalizer is running."""
        return self._running


async def main():
    """
    Main entry point for normalizer.
    """
    # Initialize normalizer
    normalizer = Normalizer(
        kafka_bootstrap_servers=os.getenv('KAFKA_BROKERS', 'localhost:9092'),
        redis_url=os.getenv('REDIS_URL', 'redis://localhost:6379')
    )
    
    # Run normalizer
    try:
        await normalizer.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        normalizer.stop()


if __name__ == '__main__':
    asyncio.run(main())
