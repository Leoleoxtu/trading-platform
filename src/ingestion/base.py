"""
Base classes and interfaces for data collectors.
Provides abstract Collector interface and RawEvent data model.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
import json


@dataclass
class RawEvent:
    """
    Raw event structure for all collected data.
    
    Attributes:
        source: Source identifier (e.g., 'rss', 'twitter', 'reddit')
        url: Original URL of the event
        text: Raw text content
        timestamp: ISO 8601 timestamp of the event
        metadata: Additional metadata (source_name, priority, quality, etc.)
    """
    source: str
    url: str
    text: str
    timestamp: str
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'source': self.source,
            'url': self.url,
            'text': self.text,
            'timestamp': self.timestamp,
            'metadata': self.metadata
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'RawEvent':
        """Create RawEvent from dictionary."""
        return cls(
            source=data['source'],
            url=data['url'],
            text=data['text'],
            timestamp=data['timestamp'],
            metadata=data.get('metadata', {})
        )


class Collector(ABC):
    """
    Abstract base class for all data collectors.
    
    Collectors are responsible for:
    - Fetching data from external sources
    - Converting to RawEvent format
    - Publishing to Kafka
    - Archiving to MinIO
    - Emitting metrics
    """
    
    def __init__(self, collector_name: str):
        """
        Initialize collector.
        
        Args:
            collector_name: Unique name for this collector instance
        """
        self.collector_name = collector_name
        self._is_running = False
    
    @abstractmethod
    async def collect(self) -> List[RawEvent]:
        """
        Collect raw events from source.
        
        Returns:
            List of RawEvent objects
            
        Raises:
            Exception: On collection failure
        """
        pass
    
    @abstractmethod
    async def publish_to_kafka(self, events: List[RawEvent]) -> int:
        """
        Publish events to Kafka topic.
        
        Args:
            events: List of RawEvent objects
            
        Returns:
            Number of successfully published events
        """
        pass
    
    @abstractmethod
    async def archive_to_minio(self, events: List[RawEvent]) -> bool:
        """
        Archive events to MinIO/S3.
        
        Args:
            events: List of RawEvent objects
            
        Returns:
            True if archiving succeeded
        """
        pass
    
    async def run_once(self) -> Dict:
        """
        Execute one collection cycle.
        
        Returns:
            Dictionary with collection statistics
        """
        stats = {
            'collector': self.collector_name,
            'timestamp': datetime.utcnow().isoformat(),
            'collected': 0,
            'published': 0,
            'archived': False,
            'errors': []
        }
        
        try:
            # Collect events
            events = await self.collect()
            stats['collected'] = len(events)
            
            if not events:
                return stats
            
            # Publish to Kafka
            published_count = await self.publish_to_kafka(events)
            stats['published'] = published_count
            
            # Archive to MinIO
            archived = await self.archive_to_minio(events)
            stats['archived'] = archived
            
        except Exception as e:
            stats['errors'].append(str(e))
        
        return stats
    
    async def start(self):
        """Start the collector (for continuous operation)."""
        self._is_running = True
    
    async def stop(self):
        """Stop the collector gracefully."""
        self._is_running = False
    
    @property
    def is_running(self) -> bool:
        """Check if collector is running."""
        return self._is_running
