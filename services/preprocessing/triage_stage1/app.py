"""
Triage Stage 1 Service - Deterministic event routing.

Consumes normalized events and routes to FAST/STANDARD/COLD/DROP_HARD buckets.
Ultra-fast, stateless processing with explicit scoring and routing.
"""

import asyncio
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path

import redis
import yaml
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from loguru import logger
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from aiohttp import web


# Prometheus metrics
EVENTS_CONSUMED = Counter(
    'triage_stage1_events_consumed_total',
    'Total events consumed'
)
EVENTS_ROUTED = Counter(
    'triage_stage1_events_routed_total',
    'Events routed by bucket',
    ['bucket']
)
EVENTS_FAILED = Counter(
    'triage_stage1_events_failed_total',
    'Events that failed processing',
    ['reason']
)
DEDUP_HITS = Counter(
    'triage_stage1_dedup_hits_total',
    'Duplicate events detected'
)
PROCESSING_DURATION = Histogram(
    'triage_stage1_processing_duration_seconds',
    'Time to process event'
)
SCORE_HISTOGRAM = Histogram(
    'triage_stage1_score_distribution',
    'Distribution of triage scores',
    buckets=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
)
LAST_SUCCESS = Gauge(
    'triage_stage1_last_success_timestamp',
    'Timestamp of last successful processing'
)


class TriageStage1:
    """
    Stage 1 Triage processor - deterministic and fast.
    
    Features:
    - Consumes normalized events from Kafka
    - Extracts cheap signals (keywords, tickers, numbers, etc.)
    - Calculates triage score (0-100)
    - Routes to FAST/STANDARD/COLD/DROP_HARD buckets
    - Deduplication via Redis
    - Prometheus metrics
    """
    
    def __init__(
        self,
        config_path: str = "config/triage_stage1.yaml",
        kafka_bootstrap_servers: str = "localhost:9092",
        input_topic: str = "events.normalized.v1",
        output_topics: Optional[Dict[str, str]] = None,
        redis_url: str = "redis://localhost:6379",
        pipeline_version: str = "1.0.0"
    ):
        """
        Initialize Triage Stage 1.
        
        Args:
            config_path: Path to triage configuration
            kafka_bootstrap_servers: Kafka broker addresses
            input_topic: Input topic (normalized events)
            output_topics: Output topics by bucket
            redis_url: Redis connection URL
            pipeline_version: Pipeline version string
        """
        self.config_path = Path(config_path)
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.input_topic = input_topic
        self.pipeline_version = pipeline_version
        
        # Output topics
        self.output_topics = output_topics or {
            'FAST': 'events.stage1.fast.v1',
            'STANDARD': 'events.stage1.standard.v1',
            'COLD': 'events.stage1.cold.v1',
            'DROP_HARD': 'events.stage1.dropped.v1',
            'ERROR': 'events.stage1.dlq.v1'
        }
        
        # Redis client for deduplication
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        
        # Load configuration
        self.config = self._load_config()
        
        # Running state
        self._running = False
        
        logger.info(f"Triage Stage 1 initialized: {input_topic} → buckets")
    
    def _load_config(self) -> Dict:
        """Load configuration from YAML."""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded config from {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise
    
    def _extract_signals(self, normalized_event: Dict) -> Dict:
        """
        Extract cheap signals from normalized event.
        
        Args:
            normalized_event: Normalized event from Stage 0
            
        Returns:
            Dictionary of extracted signals
        """
        text = normalized_event.get('text', '').lower()
        url = normalized_event.get('url', '')
        source = normalized_event.get('source', '')
        metadata = normalized_event.get('metadata', {})
        
        # Text length
        text_length = len(text)
        
        # Numerical indicators
        has_numbers = bool(re.search(r'\d', text))
        has_percent = bool(re.search(r'%|\bpercent\b', text))
        has_money = bool(re.search(r'\$|€|¥|£|billion|million|thousand|b\b|m\b|k\b', text))
        
        # Ticker candidates
        ticker_candidates = self._extract_tickers(text)
        
        # Keyword hits
        keyword_hits = self._match_keywords(text)
        
        # Recency
        event_time = normalized_event.get('timestamp')
        recency_seconds = self._calculate_recency(event_time)
        
        # Source scores
        source_type = metadata.get('source_type', source)
        source_name = metadata.get('source_name', source)
        source_reliability, source_noise = self._get_source_scores(source_type, source_name)
        
        signals = {
            'text_length': min(text_length, self.config['text_analysis']['max_length']),
            'has_ticker_candidate': len(ticker_candidates) > 0,
            'ticker_candidates': ticker_candidates if ticker_candidates else None,
            'ticker_candidates_count': len(ticker_candidates),
            'has_numbers': has_numbers,
            'has_percent': has_percent,
            'has_money': has_money,
            'keyword_hits': keyword_hits if keyword_hits else None,
            'source_reliability': source_reliability,
            'source_noise': source_noise,
            'recency_seconds': recency_seconds
        }
        
        return signals
    
    def _extract_tickers(self, text: str) -> List[str]:
        """
        Extract stock ticker candidates from text.
        
        Args:
            text: Text to search
            
        Returns:
            List of ticker candidates
        """
        if not self.config['features']['enable_ticker_extraction']:
            return []
        
        pattern = self.config['ticker_detection']['regex_pattern']
        exclude_words = set(self.config['ticker_detection']['exclude_words'])
        
        matches = re.findall(pattern, text)
        
        # Filter out excluded words
        tickers = [m.upper() for m in matches if m.upper() not in exclude_words]
        
        # Remove duplicates and limit to 10
        return list(set(tickers))[:10]
    
    def _match_keywords(self, text: str) -> List[str]:
        """
        Match keywords in text.
        
        Args:
            text: Text to search
            
        Returns:
            List of keyword categories matched
        """
        hits = []
        
        # Strong keywords
        for kw in self.config['keywords']['strong']:
            if f' {kw} ' in f' {text} ' or text.startswith(kw) or text.endswith(kw):
                hits.append('strong')
                break
        
        # Weak keywords
        if self.config['features']['enable_weak_keywords']:
            for kw in self.config['keywords']['weak']:
                if f' {kw} ' in f' {text} ' or text.startswith(kw) or text.endswith(kw):
                    hits.append('weak')
                    break
        
        # Clickbait
        if self.config['features']['enable_clickbait_detection']:
            for kw in self.config['keywords']['clickbait']:
                if kw in text:
                    hits.append('clickbait')
                    break
        
        return list(set(hits))
    
    def _calculate_recency(self, event_time: Optional[str]) -> int:
        """
        Calculate seconds since event.
        
        Args:
            event_time: Event timestamp (ISO 8601)
            
        Returns:
            Seconds since event
        """
        if not event_time:
            return 999999
        
        try:
            event_dt = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            delta = now - event_dt
            return max(0, int(delta.total_seconds()))
        except Exception as e:
            logger.warning(f"Recency calculation failed: {e}")
            return 999999
    
    def _get_source_scores(self, source_type: str, source_name: str) -> Tuple[float, float]:
        """
        Get reliability and noise scores for source.
        
        Args:
            source_type: Type of source (rss, reddit, etc.)
            source_name: Name of source (bloomberg, etc.)
            
        Returns:
            Tuple of (reliability, noise) scores
        """
        try:
            source_config = self.config['source_scores'].get(source_type, {})
            
            if source_name in source_config:
                scores = source_config[source_name]
            else:
                scores = source_config.get('default', self.config['source_scores']['default'])
            
            return (scores['reliability'], scores['noise'])
        except Exception as e:
            logger.warning(f"Source scoring failed: {e}")
            default = self.config['source_scores']['default']
            return (default['reliability'], default['noise'])
    
    def _calculate_score(self, signals: Dict, normalized_event: Dict) -> Tuple[int, List[str]]:
        """
        Calculate triage score (0-100) with reasons.
        
        Args:
            signals: Extracted signals
            normalized_event: Original normalized event
            
        Returns:
            Tuple of (score, reasons_list)
        """
        score = 50  # Start at neutral
        reasons = []
        
        # Source reliability (strong weight)
        reliability = signals['source_reliability']
        reliability_points = int(reliability * self.config['scoring']['source_reliability_weight'])
        score += reliability_points
        if reliability > 0.8:
            reasons.append('HIGH_SOURCE_RELIABILITY')
        elif reliability < 0.4:
            reasons.append('UNKNOWN_SOURCE')
        
        # Keyword hits
        keyword_hits = signals['keyword_hits'] or []
        if 'strong' in keyword_hits:
            score += self.config['scoring']['strong_keywords_weight']
            reasons.append('STRONG_KEYWORDS')
        elif 'weak' in keyword_hits:
            score += 5
            reasons.append('WEAK_KEYWORDS')
        
        # Ticker candidates
        ticker_count = signals['ticker_candidates_count']
        if ticker_count > 0:
            ticker_points = min(
                self.config['scoring']['ticker_candidates_weight'],
                ticker_count * 5
            )
            score += ticker_points
            reasons.append('HAS_TICKER_CANDIDATES')
            if ticker_count > 1:
                reasons.append('MULTIPLE_TICKERS')
        
        # Numbers/money/percent
        if signals['has_money'] or signals['has_percent']:
            score += self.config['scoring']['numbers_money_weight']
            reasons.append('HAS_MONEY_OR_PERCENT')
        elif signals['has_numbers']:
            score += 5
        
        # Recency
        recency = signals['recency_seconds']
        if recency < self.config['recency']['very_recent_seconds']:
            score += self.config['scoring']['recency_weight']
            reasons.append('VERY_RECENT')
        elif recency < self.config['recency']['recent_seconds']:
            score += 5
            reasons.append('RECENT')
        
        # Penalties
        # Source noise
        noise = signals['source_noise']
        if noise > 0.4:
            score -= self.config['scoring']['source_noise_penalty']
            reasons.append('HIGH_SOURCE_NOISE')
        
        # Clickbait
        if 'clickbait' in keyword_hits:
            score -= self.config['scoring']['clickbait_penalty']
            reasons.append('CLICKBAIT_SUSPECT')
        
        # Text length
        text_len = signals['text_length']
        if text_len < self.config['text_analysis']['min_length']:
            score -= self.config['scoring']['short_text_penalty']
            reasons.append('SHORT_TEXT')
        elif text_len > self.config['text_analysis']['max_length']:
            score -= self.config['text_analysis']['truncation_penalty']
            reasons.append('LONG_TEXT_TRUNCATED')
        
        # Language
        lang = normalized_event.get('metadata', {}).get('language')
        if lang and lang not in ['en', 'en-US']:
            score -= self.config['scoring']['lang_unknown_penalty']
            reasons.append('LANG_UNKNOWN')
        
        # Clamp score to 0-100
        score = max(0, min(100, score))
        
        return score, reasons
    
    def _check_duplicate(self, normalized_event: Dict) -> bool:
        """
        Check if event is duplicate (recently seen).
        
        Args:
            normalized_event: Normalized event
            
        Returns:
            True if duplicate, False otherwise
        """
        if not self.config['deduplication']['enabled']:
            return False
        
        dedup_key = normalized_event.get('dedup_key')
        if not dedup_key:
            return False
        
        try:
            key = f"stage1_dedup:{dedup_key}"
            exists = self.redis_client.exists(key)
            
            if exists:
                DEDUP_HITS.inc()
                return True
            
            # Mark as seen
            ttl = self.config['deduplication']['ttl_seconds']
            self.redis_client.setex(key, ttl, "1")
            return False
            
        except Exception as e:
            logger.warning(f"Dedup check failed: {e}")
            return False
    
    def _assign_bucket(self, score: int, reasons: List[str]) -> str:
        """
        Assign event to bucket based on score.
        
        Args:
            score: Triage score
            reasons: List of triage reasons
            
        Returns:
            Bucket name
        """
        # Check DROP_HARD conditions
        if 'SPAM_INDICATORS' in reasons:
            # Count spam indicators
            spam_count = sum(1 for r in reasons if 'SPAM' in r or 'CLICKBAIT' in r)
            if spam_count >= 2 and score < 30:
                return 'DROP_HARD'
        
        # FAST bucket
        if score >= self.config['thresholds']['fast_score_min']:
            return 'FAST'
        
        # STANDARD bucket
        if score >= self.config['thresholds']['standard_score_min']:
            return 'STANDARD'
        
        # COLD bucket (default)
        return 'COLD'
    
    def _assign_priority(self, bucket: str, score: int) -> str:
        """
        Assign priority hint.
        
        Args:
            bucket: Bucket name
            score: Triage score
            
        Returns:
            Priority hint (P0-P3)
        """
        priority_config = self.config['priority_hints']
        
        if bucket == 'FAST':
            threshold = self.config['thresholds']['fast_score_min'] + 15
            return 'P0' if score >= threshold else 'P1'
        elif bucket == 'STANDARD':
            threshold = self.config['thresholds']['standard_score_min'] + 10
            return 'P1' if score >= threshold else 'P2'
        else:  # COLD
            return 'P3'
    
    def _create_stage1_event(
        self,
        normalized_event: Dict,
        score: int,
        bucket: str,
        priority: str,
        reasons: List[str],
        signals: Dict
    ) -> Dict:
        """
        Create Stage 1 event object.
        
        Args:
            normalized_event: Normalized event
            score: Triage score
            bucket: Bucket assignment
            priority: Priority hint
            reasons: Triage reasons
            signals: Extracted signals
            
        Returns:
            Stage 1 event object
        """
        # Calculate quality flags
        quality_flags = []
        if signals['text_length'] < self.config['text_analysis']['min_length']:
            quality_flags.append('LOW_TEXT')
        if 'LANG_UNKNOWN' in reasons:
            quality_flags.append('LANG_UNKNOWN')
        if 'CLICKBAIT_SUSPECT' in reasons:
            quality_flags.append('CLICKBAIT_SUSPECT')
        if 'HIGH_SOURCE_NOISE' in reasons:
            quality_flags.append('SPAM_SUSPECT')
        
        # Create event
        event = {
            'schema_version': 'stage1_event.v1',
            'event_id': str(uuid.uuid4()),
            'triaged_at_utc': datetime.now(timezone.utc).isoformat(),
            'pipeline_version': self.pipeline_version,
            'source_type': normalized_event.get('metadata', {}).get('source_type', normalized_event.get('source')),
            'source_name': normalized_event.get('metadata', {}).get('source_name', 'unknown'),
            'event_time_utc': normalized_event.get('timestamp'),
            'canonical_url': normalized_event.get('url'),
            'lang': normalized_event.get('metadata', {}).get('language'),
            'dedup_key': normalized_event.get('dedup_key'),
            'normalized_text_hash': hashlib.sha256(
                normalized_event.get('text', '').encode()
            ).hexdigest(),
            'triage_score_stage1': score,
            'triage_bucket': bucket,
            'priority_hint': priority,
            'triage_reasons': reasons,
            'signals': signals,
            'quality_flags': quality_flags,
            'normalized_event': {
                'event_id': normalized_event.get('event_id', ''),
                'text': normalized_event.get('text', '')[:200],
                'url': normalized_event.get('url'),
                'source': normalized_event.get('source')
            }
        }
        
        return event
    
    async def process_event(self, normalized_event: Dict) -> Tuple[Optional[Dict], str]:
        """
        Process a single normalized event.
        
        Args:
            normalized_event: Normalized event from Stage 0
            
        Returns:
            Tuple of (stage1_event, bucket) or (None, 'ERROR')
        """
        try:
            with PROCESSING_DURATION.time():
                # Check duplicate
                if self._check_duplicate(normalized_event):
                    logger.debug(f"Duplicate event filtered")
                    return None, 'DROP_HARD'
                
                # Extract signals
                signals = self._extract_signals(normalized_event)
                
                # Calculate score
                score, reasons = self._calculate_score(signals, normalized_event)
                
                # Assign bucket
                bucket = self._assign_bucket(score, reasons)
                
                # Assign priority
                priority = self._assign_priority(bucket, score)
                
                # Create event
                event = self._create_stage1_event(
                    normalized_event, score, bucket, priority, reasons, signals
                )
                
                # Record metrics
                EVENTS_ROUTED.labels(bucket=bucket).inc()
                SCORE_HISTOGRAM.observe(score)
                LAST_SUCCESS.set_to_current_time()
                
                logger.debug(
                    f"Triaged event: score={score}, bucket={bucket}, "
                    f"priority={priority}, reasons={reasons}"
                )
                
                return event, bucket
                
        except Exception as e:
            logger.error(f"Event processing failed: {e}")
            EVENTS_FAILED.labels(reason=type(e).__name__).inc()
            return None, 'ERROR'
    
    async def consume_and_route(self):
        """
        Consume from Kafka and route to output topics.
        """
        consumer = AIOKafkaConsumer(
            self.input_topic,
            bootstrap_servers=self.kafka_bootstrap_servers,
            group_id='triage-stage1-v1',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            enable_auto_commit=True
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
                
                EVENTS_CONSUMED.inc()
                
                try:
                    normalized_event = msg.value
                    stage1_event, bucket = await self.process_event(normalized_event)
                    
                    if stage1_event is None:
                        continue
                    
                    # Publish to output topic
                    output_topic = self.output_topics.get(bucket, self.output_topics['ERROR'])
                    await producer.send(output_topic, value=stage1_event)
                    
                    logger.debug(f"Published to {output_topic}")
                    
                except Exception as e:
                    logger.error(f"Error routing message: {e}")
                    EVENTS_FAILED.labels(reason='produce').inc()
                    continue
                
        finally:
            await consumer.stop()
            await producer.stop()
            logger.info("Stopped consuming")
    
    async def run(self):
        """Run the triage service."""
        self._running = True
        logger.info("Triage Stage 1 started")
        
        try:
            await self.consume_and_route()
        except Exception as e:
            logger.error(f"Triage error: {e}")
        finally:
            self._running = False
            logger.info("Triage Stage 1 stopped")
    
    async def health_handler(self, request):
        """Health check endpoint."""
        return web.json_response({
            'status': 'ok',
            'running': self._running,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    async def metrics_handler(self, request):
        """Prometheus metrics endpoint."""
        return web.Response(body=generate_latest(), content_type='text/plain')
    
    async def start_http_server(self, port: int = 8006):
        """Start HTTP server for health and metrics."""
        app = web.Application()
        app.router.add_get('/health', self.health_handler)
        app.router.add_get('/metrics', self.metrics_handler)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        logger.info(f"HTTP server started on port {port}")
        return runner
    
    def stop(self):
        """Stop the service."""
        self._running = False


async def main():
    """Main entry point."""
    triage = TriageStage1(
        config_path=os.getenv('CONFIG_PATH', 'config/triage_stage1.yaml'),
        kafka_bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
        redis_url=os.getenv('REDIS_URL', 'redis://localhost:6379')
    )
    
    # Start HTTP server
    http_port = int(os.getenv('HEALTH_PORT', '8006'))
    http_runner = await triage.start_http_server(http_port)
    
    try:
        # Run triage
        await triage.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        triage.stop()
    finally:
        await http_runner.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
