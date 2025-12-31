#!/usr/bin/env python3
"""
Triage Stage 2 - NLP Enrichment Service
Consumes events from Stage 1 and enriches with:
- spaCy NER (entities)
- FinBERT sentiment analysis
- Advanced scoring with explainable reasons
- Adaptive thresholds based on market and load regimes
"""

import os
import sys
import asyncio
import json
import hashlib
import time
import re
import csv
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

import yaml
import redis
import spacy
import torch
import numpy as np
from loguru import logger
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiohttp import web
from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, REGISTRY
)
from transformers import AutoTokenizer, AutoModelForSequenceClassification


# ==============================================================================
# PROMETHEUS METRICS
# ==============================================================================

# Counters
events_consumed = Counter(
    'triage_stage2_events_consumed_total',
    'Total events consumed from Stage 1'
)
events_triaged = Counter(
    'triage_stage2_events_triaged_total',
    'Total events triaged and published',
    ['priority']
)
events_failed = Counter(
    'triage_stage2_events_failed_total',
    'Total events failed',
    ['reason']
)
dlq_total = Counter(
    'triage_stage2_dlq_total',
    'Total events sent to DLQ'
)
entities_extracted = Counter(
    'triage_stage2_entities_extracted_total',
    'Total entities extracted',
    ['type']
)

# Histograms
processing_duration = Histogram(
    'triage_stage2_processing_duration_seconds',
    'Processing time per event',
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)
score_distribution = Histogram(
    'triage_stage2_score_distribution',
    'Distribution of triage scores',
    buckets=[0, 20, 40, 60, 80, 100]
)
sentiment_score_hist = Histogram(
    'triage_stage2_sentiment_score',
    'Distribution of sentiment scores',
    buckets=[-1.0, -0.5, -0.25, 0, 0.25, 0.5, 1.0]
)

# Gauges
last_success = Gauge(
    'triage_stage2_last_success_timestamp',
    'Timestamp of last successful processing'
)
sentiment_mean = Gauge(
    'triage_stage2_sentiment_mean',
    'Rolling mean sentiment score'
)
market_regime_gauge = Gauge(
    'triage_stage2_market_regime',
    'Current market regime (0=CALM, 1=NORMAL, 2=STRESS)'
)
load_regime_gauge = Gauge(
    'triage_stage2_load_regime',
    'Current load regime (0=LOW, 1=NORMAL, 2=HIGH)'
)


# ==============================================================================
# DATA CLASSES
# ==============================================================================

@dataclass
class Entity:
    """Named entity from spaCy NER"""
    type: str
    text: str
    confidence: float
    start: int = 0
    end: int = 0

@dataclass
class Ticker:
    """Validated ticker symbol"""
    symbol: str
    confidence: float
    method: str  # whitelist, entity_match, regex, inherited

@dataclass
class Sentiment:
    """Sentiment analysis result"""
    score: float  # -1 to 1
    confidence: float  # 0 to 1
    model: str
    label: str  # positive, negative, neutral

@dataclass
class ScoreBreakdown:
    """Detailed score components"""
    keywords: float = 0
    source_quality: float = 0
    ticker_confidence: float = 0
    entity_strength: float = 0
    sentiment_impact: float = 0

@dataclass
class Regime:
    """Market and pipeline load regimes"""
    market_regime: str  # CALM, NORMAL, STRESS
    load_regime: str    # LOW_LOAD, NORMAL_LOAD, HIGH_LOAD
    vix_value: Optional[float] = None
    consumer_lag: Optional[int] = None
    p95_latency_ms: Optional[float] = None

@dataclass
class Thresholds:
    """Priority thresholds"""
    T0: float
    T1: float
    T2: float


# ==============================================================================
# TRIAGE STAGE 2 SERVICE
# ==============================================================================

class TriageStage2:
    """
    NLP-based triage service with:
    - spaCy NER for entity extraction
    - FinBERT for financial sentiment
    - Explainable scoring (0-100)
    - Adaptive thresholds based on regimes
    """
    
    def __init__(
        self,
        config_path: str = "config/triage_stage2.yaml",
        kafka_bootstrap_servers: str = "localhost:9092",
        redis_url: str = "redis://localhost:6379"
    ):
        """Initialize Triage Stage 2 service"""
        self.config = self._load_config(config_path)
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.redis_url = redis_url
        self.redis_client = None
        self.running = False
        
        # NLP models
        self.spacy_models = {}
        self.finbert_tokenizer = None
        self.finbert_model = None
        
        # Ticker whitelist
        self.ticker_whitelist = set()
        
        # Sentiment rolling average
        self.sentiment_history = []
        self.sentiment_window_size = 100
        
        logger.info(f"Triage Stage 2 initialized")
    
    def _load_config(self, path: str) -> dict:
        """Load YAML configuration"""
        with open(path, 'r') as f:
            config = yaml.safe_load(f)
        logger.info(f"Loaded config from {path}")
        return config
    
    async def initialize(self):
        """Initialize all models and resources"""
        logger.info("Initializing NLP models...")
        
        # Load spaCy models
        for lang, model_name in self.config['nlp']['spacy_models'].items():
            try:
                logger.info(f"Loading spaCy model: {model_name}")
                self.spacy_models[lang] = spacy.load(model_name)
            except Exception as e:
                logger.error(f"Failed to load spaCy model {model_name}: {e}")
                if lang == self.config['nlp']['spacy_models']['default']:
                    raise
        
        # Load FinBERT
        logger.info("Loading FinBERT model...")
        finbert_config = self.config['nlp']['finbert']
        self.finbert_tokenizer = AutoTokenizer.from_pretrained(finbert_config['model_name'])
        self.finbert_model = AutoModelForSequenceClassification.from_pretrained(
            finbert_config['model_name']
        )
        self.finbert_model.eval()
        if torch.cuda.is_available() and finbert_config['device'] == 'cuda':
            self.finbert_model.to('cuda')
            logger.info("FinBERT loaded on CUDA")
        else:
            logger.info("FinBERT loaded on CPU")
        
        # Load ticker whitelist
        ticker_file = self.config['tickers']['whitelist_file']
        with open(ticker_file, 'r') as f:
            reader = csv.DictReader(f)
            self.ticker_whitelist = {row['symbol'] for row in reader}
        logger.info(f"Loaded {len(self.ticker_whitelist)} tickers from whitelist")
        
        # Initialize Redis
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        self.redis_client.ping()
        logger.info("Redis connected")
        
        logger.info("Initialization complete")
    
    # -------------------------------------------------------------------------
    # NLP PIPELINE
    # -------------------------------------------------------------------------
    
    def extract_entities(self, text: str, lang: str) -> List[Entity]:
        """Extract named entities using spaCy NER"""
        # Select model
        model_key = lang if lang in self.spacy_models else 'default'
        nlp = self.spacy_models.get(model_key, self.spacy_models.get('default'))
        
        # Process text
        doc = nlp(text[:self.config['nlp']['max_text_length']])
        
        entities = []
        for ent in doc.ents:
            # Map spaCy entity types
            if ent.label_ in ['ORG', 'PERSON', 'PRODUCT', 'GPE', 'DATE', 'EVENT']:
                entity = Entity(
                    type=ent.label_,
                    text=ent.text,
                    confidence=0.9,  # spaCy doesn't provide confidence, use default
                    start=ent.start_char,
                    end=ent.end_char
                )
                entities.append(entity)
                entities_extracted.labels(type=ent.label_).inc()
        
        # Extract MONEY and PERCENT via regex if not from model
        money_pattern = r'\$\d+(?:\.\d+)?[BMK]?'
        percent_pattern = r'\d+(?:\.\d+)?%'
        
        for match in re.finditer(money_pattern, text):
            entity = Entity(
                type='MONEY',
                text=match.group(),
                confidence=0.85,
                start=match.start(),
                end=match.end()
            )
            entities.append(entity)
            entities_extracted.labels(type='MONEY').inc()
        
        for match in re.finditer(percent_pattern, text):
            entity = Entity(
                type='PERCENT',
                text=match.group(),
                confidence=0.85,
                start=match.start(),
                end=match.end()
            )
            entities.append(entity)
            entities_extracted.labels(type='PERCENT').inc()
        
        return entities
    
    def analyze_sentiment(self, text: str) -> Sentiment:
        """Analyze sentiment using FinBERT"""
        finbert_config = self.config['nlp']['finbert']
        
        # Truncate text
        text_truncated = text[:finbert_config['max_length']]
        
        # Tokenize
        inputs = self.finbert_tokenizer(
            text_truncated,
            return_tensors='pt',
            truncation=True,
            max_length=finbert_config['max_length'],
            padding=True
        )
        
        if torch.cuda.is_available() and finbert_config['device'] == 'cuda':
            inputs = {k: v.to('cuda') for k, v in inputs.items()}
        
        # Inference
        with torch.no_grad():
            outputs = self.finbert_model(**inputs)
            logits = outputs.logits
            probs = torch.nn.functional.softmax(logits, dim=-1)
        
        # Map to sentiment
        # FinBERT: [negative, neutral, positive]
        negative, neutral, positive = probs[0].cpu().numpy()
        
        # Determine label
        max_prob = max(negative, neutral, positive)
        if max_prob == positive:
            label = 'positive'
            score = positive - negative  # Range: -1 to 1
        elif max_prob == negative:
            label = 'negative'
            score = negative - positive
        else:
            label = 'neutral'
            score = 0.0
        
        # Normalize score to [-1, 1]
        score = float(np.clip(score, -1.0, 1.0))
        confidence = float(max_prob)
        
        sentiment = Sentiment(
            score=score,
            confidence=confidence,
            model='finbert',
            label=label
        )
        
        # Track sentiment
        sentiment_score_hist.observe(score)
        self.sentiment_history.append(score)
        if len(self.sentiment_history) > self.sentiment_window_size:
            self.sentiment_history.pop(0)
        sentiment_mean.set(np.mean(self.sentiment_history))
        
        return sentiment
    
    def validate_tickers(
        self,
        text: str,
        entities: List[Entity],
        symbols_candidates: Optional[List[str]] = None
    ) -> List[Ticker]:
        """Validate and extract tickers"""
        tickers = []
        seen = set()
        
        # From inherited symbols_candidates
        if symbols_candidates:
            for symbol in symbols_candidates:
                if symbol in self.ticker_whitelist and symbol not in seen:
                    tickers.append(Ticker(
                        symbol=symbol,
                        confidence=0.95,
                        method='inherited'
                    ))
                    seen.add(symbol)
        
        # From ORG entities
        for entity in entities:
            if entity.type == 'ORG':
                # Try to match entity text to ticker (simple heuristic)
                entity_text = entity.text.upper().replace(' INC.', '').replace(' CORP', '')
                # Check if it's a known ticker
                for ticker in self.ticker_whitelist:
                    if ticker in entity_text or entity_text.startswith(ticker[:3]):
                        if ticker not in seen:
                            tickers.append(Ticker(
                                symbol=ticker,
                                confidence=0.75,
                                method='entity_match'
                            ))
                            seen.add(ticker)
                            break
        
        # Regex extraction (uppercase 1-5 letters)
        ticker_pattern = r'\b[A-Z]{1,5}\b'
        for match in re.finditer(ticker_pattern, text):
            symbol = match.group()
            if symbol in self.ticker_whitelist and symbol not in seen:
                tickers.append(Ticker(
                    symbol=symbol,
                    confidence=0.65,
                    method='regex'
                ))
                seen.add(symbol)
        
        # Filter by confidence threshold
        threshold = self.config['tickers']['confidence_threshold']
        tickers = [t for t in tickers if t.confidence >= threshold]
        
        # Limit number of tickers
        max_tickers = self.config['tickers']['max_tickers_per_event']
        tickers = sorted(tickers, key=lambda t: t.confidence, reverse=True)[:max_tickers]
        
        return tickers
    
    # -------------------------------------------------------------------------
    # SCORING ENGINE
    # -------------------------------------------------------------------------
    
    def calculate_score(
        self,
        text: str,
        entities: List[Entity],
        tickers: List[Ticker],
        sentiment: Sentiment,
        source_type: str,
        source_name: str,
        stage1_score: Optional[float] = None
    ) -> Tuple[float, List[str], ScoreBreakdown]:
        """
        Calculate triage score (0-100) with explainable reasons
        Returns: (score, reasons, breakdown)
        """
        reasons = []
        breakdown = ScoreBreakdown()
        
        # 1. Keywords (0-30)
        keyword_score = self._score_keywords(text, reasons)
        breakdown.keywords = keyword_score
        
        # 2. Source quality (0-25)
        source_score = self._score_source_quality(source_type, source_name, stage1_score, reasons)
        breakdown.source_quality = source_score
        
        # 3. Ticker confidence (0-20)
        ticker_score = self._score_tickers(tickers, reasons)
        breakdown.ticker_confidence = ticker_score
        
        # 4. Entity strength (0-10)
        entity_score = self._score_entities(entities, reasons)
        breakdown.entity_strength = entity_score
        
        # 5. Sentiment impact (0-15)
        sentiment_score = self._score_sentiment(sentiment, reasons)
        breakdown.sentiment_impact = sentiment_score
        
        # Total score
        total_score = (
            keyword_score +
            source_score +
            ticker_score +
            entity_score +
            sentiment_score
        )
        
        # Clamp to 0-100
        total_score = max(0, min(100, total_score))
        
        # Text length flags
        if len(text) < self.config['nlp']['min_text_length']:
            reasons.append('SHORT_TEXT')
        elif len(text) > self.config['nlp']['max_text_length']:
            reasons.append('LONG_TEXT')
        
        return total_score, reasons, breakdown
    
    def _score_keywords(self, text: str, reasons: List[str]) -> float:
        """Score based on impact keywords"""
        config = self.config['scoring']
        keywords_config = self.config['keywords']['impact']
        
        score = 0
        text_lower = text.lower()
        
        # High-impact keywords
        for category, keyword_list in keywords_config.items():
            for keyword in keyword_list:
                if keyword.lower() in text_lower:
                    score += config['keyword_scores']['impact_keyword']
                    reasons.append(f'KEYWORD_{category.upper()}')
                    break  # Count category once
        
        # Weak keywords (lower score)
        weak_keywords = self.config['keywords']['weak']
        for keyword in weak_keywords:
            if keyword.lower() in text_lower:
                score += config['keyword_scores']['weak_keyword']
                break
        
        # Cap at max
        score = min(score, config['weights']['keywords_max'])
        return score
    
    def _score_source_quality(
        self,
        source_type: str,
        source_name: str,
        stage1_score: Optional[float],
        reasons: List[str]
    ) -> float:
        """Score based on source quality"""
        config = self.config['scoring']
        source_quality = self.config['source_quality']
        
        # Get source reliability
        type_sources = source_quality.get(source_type, {})
        source_info = type_sources.get(source_name, type_sources.get('default', {'reliability': 0.5}))
        reliability = source_info['reliability']
        
        # Scale to max points
        score = reliability * config['weights']['source_quality_max']
        
        # Add reason
        if reliability >= 0.85:
            reasons.append('HIGH_SOURCE_QUALITY')
        elif reliability <= 0.50:
            reasons.append('LOW_SOURCE_QUALITY')
        
        return score
    
    def _score_tickers(self, tickers: List[Ticker], reasons: List[str]) -> float:
        """Score based on ticker validation"""
        config = self.config['scoring']
        
        if not tickers:
            reasons.append('NO_TICKER')
            return 0
        
        # Average confidence
        avg_confidence = sum(t.confidence for t in tickers) / len(tickers)
        score = avg_confidence * config['weights']['ticker_confidence_max']
        
        reasons.append('HAS_VALID_TICKER')
        return score
    
    def _score_entities(self, entities: List[Entity], reasons: List[str]) -> float:
        """Score based on entity strength"""
        config = self.config['scoring']
        
        if not entities:
            reasons.append('NER_EMPTY')
            return 0
        
        # Score by entity type
        entity_scores_config = config['entity_scores']
        score = 0
        for entity in entities:
            entity_score = entity_scores_config.get(entity.type, 1)
            score += entity_score * entity.confidence
        
        # Cap at max
        score = min(score, config['weights']['entity_strength_max'])
        
        if score >= 7:
            reasons.append('STRONG_ENTITIES')
        elif score <= 2:
            reasons.append('WEAK_ENTITIES')
        
        return score
    
    def _score_sentiment(self, sentiment: Sentiment, reasons: List[str]) -> float:
        """Score based on sentiment magnitude and confidence"""
        config = self.config['scoring']
        sentiment_config = config['sentiment']
        
        # Magnitude of sentiment
        magnitude = abs(sentiment.score)
        
        # Check confidence
        if sentiment.confidence < sentiment_config['conf_threshold']:
            reasons.append('LOW_SENTIMENT_CONF')
            # Penalty
            return max(0, config['weights']['sentiment_impact_max'] - sentiment_config['penalty_low_conf'])
        
        # Strong sentiment bonus
        if magnitude >= sentiment_config['strong_threshold']:
            reasons.append('STRONG_SENTIMENT')
        else:
            reasons.append('WEAK_SENTIMENT')
        
        # Score proportional to magnitude * confidence
        score = magnitude * sentiment.confidence * config['weights']['sentiment_impact_max']
        return score
    
    # -------------------------------------------------------------------------
    # REGIME DETECTION
    # -------------------------------------------------------------------------
    
    def detect_market_regime(self) -> str:
        """Detect market regime: CALM, NORMAL, or STRESS"""
        config = self.config['market_regime']
        
        try:
            # Try to get VIX from Redis cache (updated by external service)
            vix_key = "market:vix:current"
            vix_str = self.redis_client.get(vix_key)
            
            if vix_str:
                vix = float(vix_str)
                logger.debug(f"VIX: {vix}")
                
                if vix >= config['vix_thresholds']['STRESS']:
                    return 'STRESS'
                elif vix < config['vix_thresholds']['CALM']:
                    return 'CALM'
                else:
                    return 'NORMAL'
        except Exception as e:
            logger.warning(f"Failed to get VIX: {e}")
        
        # Fallback: assume NORMAL
        return 'NORMAL'
    
    def detect_load_regime(self, consumer_lag: int, p95_latency: float) -> str:
        """Detect pipeline load regime: LOW_LOAD, NORMAL_LOAD, or HIGH_LOAD"""
        config = self.config['load_regime']
        
        # Check multiple signals
        high_load_signals = 0
        normal_load_signals = 0
        
        # Consumer lag
        if consumer_lag > config['consumer_lag_threshold']['HIGH_LOAD']:
            high_load_signals += 1
        elif consumer_lag > config['consumer_lag_threshold']['NORMAL_LOAD']:
            normal_load_signals += 1
        
        # Latency p95
        if p95_latency > config['latency_p95_threshold_ms']['HIGH_LOAD']:
            high_load_signals += 1
        elif p95_latency > config['latency_p95_threshold_ms']['NORMAL_LOAD']:
            normal_load_signals += 1
        
        # Determine regime
        if high_load_signals >= 1:
            return 'HIGH_LOAD'
        elif normal_load_signals >= 1:
            return 'NORMAL_LOAD'
        else:
            return 'LOW_LOAD'
    
    def calculate_thresholds(self, regime: Regime) -> Thresholds:
        """Calculate adaptive thresholds based on regimes"""
        config = self.config['thresholds']
        
        # Baseline
        T0 = config['baseline']['P0']
        T1 = config['baseline']['P1']
        T2 = config['baseline']['P2']
        
        # Market regime adjustment
        market_adj = config['market_regime'][regime.market_regime]
        T0 += market_adj['P0']
        T1 += market_adj['P1']
        T2 += market_adj['P2']
        
        # Load regime adjustment
        load_adj = config['load_regime'][regime.load_regime]
        T0 += load_adj['P0']
        T1 += load_adj['P1']
        T2 += load_adj['P2']
        
        return Thresholds(T0=T0, T1=T1, T2=T2)
    
    def assign_priority(self, score: float, thresholds: Thresholds, reasons: List[str]) -> str:
        """Assign priority based on score and thresholds"""
        if score >= thresholds.T0:
            return 'P0'
        elif score >= thresholds.T1:
            return 'P1'
        elif score >= thresholds.T2:
            return 'P2'
        else:
            return 'P3'
    
    # -------------------------------------------------------------------------
    # KAFKA PROCESSING
    # -------------------------------------------------------------------------
    
    async def process_event(self, raw_event: dict) -> Optional[dict]:
        """Process a single event through NLP pipeline"""
        start_time = time.time()
        
        try:
            # Extract fields
            event_id = raw_event.get('event_id')
            text = raw_event.get('normalized_text', raw_event.get('text', ''))
            lang = raw_event.get('lang', 'en')
            source_type = raw_event.get('source_type')
            source_name = raw_event.get('source_name')
            stage1_score = raw_event.get('triage_score_stage1')
            stage1_bucket = raw_event.get('triage_bucket')
            symbols_candidates = raw_event.get('symbols_candidates', [])
            
            quality_flags = []
            
            # Check text length
            if len(text) < self.config['nlp']['min_text_length']:
                quality_flags.append('LOW_TEXT')
            
            if len(text) > self.config['nlp']['max_text_length']:
                quality_flags.append('TEXT_TRUNCATED')
                text = text[:self.config['nlp']['max_text_length']]
            
            # NLP Pipeline
            entities = self.extract_entities(text, lang)
            sentiment = self.analyze_sentiment(text)
            tickers = self.validate_tickers(text, entities, symbols_candidates)
            
            if not entities:
                quality_flags.append('NO_ENTITIES')
            
            # Scoring
            score, reasons, breakdown = self.calculate_score(
                text, entities, tickers, sentiment,
                source_type, source_name, stage1_score
            )
            
            # Regime detection
            consumer_lag = 0  # TODO: Get from Kafka consumer metrics
            p95_latency = (time.time() - start_time) * 1000
            
            market_regime = self.detect_market_regime()
            load_regime = self.detect_load_regime(consumer_lag, p95_latency)
            
            regime = Regime(
                market_regime=market_regime,
                load_regime=load_regime,
                vix_value=None,
                consumer_lag=consumer_lag,
                p95_latency_ms=p95_latency
            )
            
            # Adaptive thresholds
            thresholds = self.calculate_thresholds(regime)
            priority = self.assign_priority(score, thresholds, reasons)
            
            # Add regime reasons
            if regime.market_regime == 'STRESS':
                reasons.append('STRESS_REGIME_BOOST')
            if regime.load_regime == 'HIGH_LOAD':
                reasons.append('HIGH_LOAD_PENALTY')
            
            # Build output event
            output_event = {
                'schema_version': 'triaged_event.v1',
                'event_id': event_id,
                'triaged_at_utc': datetime.now(timezone.utc).isoformat(),
                'pipeline_version': os.getenv('PIPELINE_VERSION', 'triage-stage2.v1.0'),
                'source_type': source_type,
                'source_name': source_name,
                'canonical_url': raw_event.get('canonical_url'),
                'event_time_utc': raw_event.get('event_time_utc'),
                'lang': lang,
                'dedup_key': raw_event.get('dedup_key'),
                'normalized_text': text,
                'normalized_text_hash': hashlib.sha256(text.encode()).hexdigest(),
                'entities': [asdict(e) for e in entities],
                'money_mentions': {
                    'present': any(e.type == 'MONEY' for e in entities),
                    'amounts': []
                },
                'percent_mentions': {
                    'present': any(e.type == 'PERCENT' for e in entities),
                    'values': []
                },
                'tickers': [asdict(t) for t in tickers],
                'sentiment': asdict(sentiment),
                'triage_score': round(score, 2),
                'priority': priority,
                'triage_reasons': reasons,
                'score_breakdown': asdict(breakdown),
                'thresholds': asdict(thresholds),
                'regime': asdict(regime),
                'quality_flags': quality_flags,
                'stage1_score': stage1_score,
                'stage1_bucket': stage1_bucket,
                'processing_time_ms': round((time.time() - start_time) * 1000, 2)
            }
            
            # Metrics
            processing_duration.observe(time.time() - start_time)
            score_distribution.observe(score)
            events_triaged.labels(priority=priority).inc()
            last_success.set(time.time())
            
            # Update regime gauges
            regime_map = {'CALM': 0, 'NORMAL': 1, 'STRESS': 2}
            market_regime_gauge.set(regime_map.get(market_regime, 1))
            
            load_map = {'LOW_LOAD': 0, 'NORMAL_LOAD': 1, 'HIGH_LOAD': 2}
            load_regime_gauge.set(load_map.get(load_regime, 1))
            
            return output_event
            
        except Exception as e:
            logger.error(f"Error processing event {raw_event.get('event_id')}: {e}")
            events_failed.labels(reason='processing_error').inc()
            raise
    
    async def consume_and_route(self):
        """Main consumer loop"""
        kafka_config = self.config['kafka']
        
        # Create consumer
        consumer = AIOKafkaConsumer(
            *kafka_config['input_topic'].split(','),
            bootstrap_servers=self.kafka_bootstrap_servers,
            group_id=kafka_config['input_group'],
            enable_auto_commit=kafka_config['enable_auto_commit'],
            auto_offset_reset='latest',
            max_poll_records=kafka_config['max_poll_records'],
            consumer_timeout_ms=kafka_config['consumer_timeout_ms']
        )
        
        # Create producer
        producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_bootstrap_servers,
            compression_type='snappy'
        )
        
        await consumer.start()
        await producer.start()
        
        logger.info(f"Started consuming from {kafka_config['input_topic']}")
        
        try:
            async for msg in consumer:
                if not self.running:
                    break
                
                try:
                    # Parse input
                    raw_event = json.loads(msg.value.decode('utf-8'))
                    events_consumed.inc()
                    
                    # Process
                    triaged_event = await self.process_event(raw_event)
                    
                    if triaged_event:
                        # Publish to output topic
                        await producer.send(
                            kafka_config['output_topic'],
                            value=json.dumps(triaged_event).encode('utf-8')
                        )
                        
                        logger.debug(f"Triaged event {triaged_event['event_id']}: "
                                   f"score={triaged_event['triage_score']}, "
                                   f"priority={triaged_event['priority']}")
                    
                    # Manual commit
                    if not kafka_config['enable_auto_commit']:
                        await consumer.commit()
                
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    
                    # Send to DLQ
                    try:
                        dlq_event = {
                            'event_id': raw_event.get('event_id', 'unknown'),
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'failed_stage': 'triage_stage2',
                            'input_event': raw_event,
                            'failed_at_utc': datetime.now(timezone.utc).isoformat()
                        }
                        await producer.send(
                            kafka_config['dlq_topic'],
                            value=json.dumps(dlq_event).encode('utf-8')
                        )
                        dlq_total.inc()
                    except Exception as dlq_error:
                        logger.error(f"Failed to send to DLQ: {dlq_error}")
        
        finally:
            logger.info("Stopped consuming")
            await consumer.stop()
            await producer.stop()
    
    # -------------------------------------------------------------------------
    # HTTP SERVER (HEALTH & METRICS)
    # -------------------------------------------------------------------------
    
    async def handle_health(self, request):
        """Health check endpoint"""
        return web.json_response({
            'status': 'ok' if self.running else 'stopped',
            'running': self.running,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    async def handle_metrics(self, request):
        """Prometheus metrics endpoint"""
        metrics = generate_latest(REGISTRY)
        return web.Response(body=metrics, content_type='text/plain')
    
    async def start_http_server(self, port: int):
        """Start HTTP server for health and metrics"""
        app = web.Application()
        app.router.add_get('/health', self.handle_health)
        app.router.add_get('/metrics', self.handle_metrics)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        logger.info(f"HTTP server started on port {port}")
        return runner
    
    # -------------------------------------------------------------------------
    # MAIN
    # -------------------------------------------------------------------------
    
    async def run(self):
        """Run the triage service"""
        self.running = True
        logger.info("Triage Stage 2 started")
        
        try:
            await self.consume_and_route()
        except Exception as e:
            logger.error(f"Triage error: {e}")
            raise
        finally:
            self.running = False
            logger.info("Triage Stage 2 stopped")
    
    def stop(self):
        """Stop the service"""
        self.running = False


# ==============================================================================
# ENTRY POINT
# ==============================================================================

async def main():
    """Main entry point"""
    triage = TriageStage2(
        config_path=os.getenv('CONFIG_PATH', 'config/triage_stage2.yaml'),
        kafka_bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
        redis_url=os.getenv('REDIS_URL', 'redis://localhost:6379')
    )
    
    # Initialize models
    await triage.initialize()
    
    # Start HTTP server
    http_port = int(os.getenv('HEALTH_PORT', '8007'))
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
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=os.getenv('LOG_LEVEL', 'INFO')
    )
    
    # Run
    asyncio.run(main())
