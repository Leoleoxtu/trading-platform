# Triage Stage 2: NLP Enrichment

## Overview

Triage Stage 2 enriches Stage 1 events with advanced NLP analysis:
- **spaCy NER**: Named entity extraction (organizations, people, money, percentages)
- **FinBERT**: Financial sentiment analysis (-1 to +1)
- **Explainable Scoring**: 0-100 composite score with detailed breakdown
- **Adaptive Thresholds**: Priority assignment adjusted by market and load regimes

**Architecture**:
```
Stage 1 Events → NLP Pipeline → Triaged Events
                 ├─ Entity Extraction
                 ├─ Sentiment Analysis
                 ├─ Ticker Validation
                 ├─ Scoring Engine
                 └─ Regime Detection
```

---

## Scoring System

Triage score (0-100) is composed of 5 weighted components:

### 1. Keywords (0-30 points)
Matches high-impact terms in 6 categories:
- **earnings**: earnings, revenue, profit, guidance, EPS, beat, miss
- **regulation**: SEC, Fed, CFTC, investigation, fine, sanctions
- **macro**: inflation, GDP, unemployment, interest rate, Fed meeting
- **security**: breach, hack, cybersecurity, ransomware, data leak
- **merger**: merger, acquisition, M&A, buyout, takeover
- **bankruptcy**: bankruptcy, Chapter 11, default, liquidation

**Impact**: 5 points per category matched  
**Weak keywords**: 1 point (possible, could, might, rumor)

### 2. Source Quality (0-25 points)
Based on historical reliability and noise levels:
```yaml
bloomberg: 0.95 reliability → 23.75 points
reuters: 0.90 → 22.5 points
wsj: 0.88 → 22 points
reddit/wallstreetbets: 0.50 → 12.5 points
```

### 3. Ticker Confidence (0-20 points)
Average confidence of validated tickers:
- **Inherited** from Stage 1: 95% confidence
- **Entity match** (ORG → ticker): 75% confidence
- **Regex** extraction: 65% confidence

Only tickers in whitelist (`config/tickers_whitelist.csv`) are scored.

### 4. Entity Strength (0-10 points)
Quality and quantity of named entities:
- **ORG**: 3 points × confidence
- **PERSON**: 2 points × confidence
- **MONEY**: 2 points × confidence
- **PERCENT**: 1.5 points × confidence
- Others: 1 point × confidence

### 5. Sentiment Impact (0-15 points)
FinBERT sentiment magnitude × confidence:
- Score range: [-1, 1] (negative to positive)
- Confidence: [0, 1]
- **Strong sentiment** (|score| ≥ 0.5): Bonus reason
- **Low confidence** (< 0.3): Penalty (-5 points)

---

## Priority Assignment

### Baseline Thresholds
- **P0**: ≥ 80 points (critical)
- **P1**: ≥ 60 points (high)
- **P2**: ≥ 40 points (medium)
- **P3**: < 40 points (low)

### Regime Adjustments

#### Market Regime (VIX-based)
Detected from cached VIX value:
- **STRESS** (VIX ≥ 25): Lower all thresholds by 10 → More P0/P1
- **CALM** (VIX < 12): Raise all thresholds by 5 → Fewer P0/P1
- **NORMAL** (12 ≤ VIX < 25): No adjustment

Example: In STRESS regime, P0 threshold drops from 80 → 70.

#### Load Regime (Pipeline metrics)
Detected from consumer lag, p95 latency, DLQ rate:
- **HIGH_LOAD**: Raise thresholds by 5 → Reduce load on downstream
- **NORMAL_LOAD**: No adjustment
- **LOW_LOAD**: Lower thresholds by 3 → Process more events

**Signals**:
```yaml
HIGH_LOAD:
  - Consumer lag > 5000 messages
  - p95 latency > 500ms
  - DLQ rate > 5%
NORMAL_LOAD:
  - Lag > 1000 OR latency > 200ms OR DLQ > 1%
LOW_LOAD:
  - All metrics below normal thresholds
```

### Combined Example
```
Event base score: 78
Market regime: STRESS → P0 threshold: 80 - 10 = 70
Load regime: NORMAL_LOAD → P0 threshold: 70 + 0 = 70
Result: 78 ≥ 70 → P0 (would be P1 in NORMAL market)
```

---

## Triage Reasons

Each event includes explainable reasons (closed list):

**High Impact**:
- `KEYWORD_EARNINGS`, `KEYWORD_REGULATION`, `KEYWORD_MACRO`, `KEYWORD_SECURITY`, `KEYWORD_MERGER`, `KEYWORD_BANKRUPTCY`
- `HIGH_SOURCE_QUALITY` (reliability ≥ 0.85)
- `HAS_VALID_TICKER` (whitelist match)
- `STRONG_ENTITIES` (entity score ≥ 7)
- `STRONG_SENTIMENT` (|score| ≥ 0.5)
- `STRESS_REGIME_BOOST` (market stress adjustment applied)

**Low Impact**:
- `NO_TICKER` (no valid ticker found)
- `LOW_SOURCE_QUALITY` (reliability ≤ 0.50)
- `NER_EMPTY` (no entities extracted)
- `WEAK_ENTITIES` (entity score ≤ 2)
- `WEAK_SENTIMENT` (|score| < 0.5)
- `LOW_SENTIMENT_CONF` (confidence < 0.3)
- `SHORT_TEXT` (< 100 characters)
- `LONG_TEXT` (> 1000 characters, truncated)
- `HIGH_LOAD_PENALTY` (load regime adjustment applied)

---

## Dashboard Interpretation

### Panel 1: Throughput (events/sec)
**What**: Input vs output rates  
**Healthy**: Input ≈ Output, DLQ rate < 1%  
**Alert**: Growing gap → Processing lag or errors

### Panel 2: Latency p95
**What**: 95th percentile processing time  
**Healthy**: < 200ms  
**Warning**: 200-500ms  
**Critical**: > 500ms (check NLP model load or batching)

### Panel 3: Priority Distribution
**What**: Proportion of P0/P1/P2/P3 events  
**Typical**: P3 (40%), P2 (30%), P1 (20%), P0 (10%)  
**Skewed to P0/P1**: Market stress regime active OR high-quality sources  
**Skewed to P3**: Low-quality sources OR weak signal period

### Panel 4: DLQ Rate
**What**: % of events failing to process  
**Healthy**: < 1%  
**Warning**: 1-5% (check logs for schema errors)  
**Critical**: > 5% (NLP model issues or malformed events)

### Panel 5: Score Distribution
**What**: Quantiles of triage scores over time  
**Use**: Track signal quality trends  
**Anomaly**: Sudden drop in p95 → Source degradation or topic shift

### Panel 6: Sentiment Mean (rolling)
**What**: Average sentiment across recent events  
**Range**: -1 (very negative) to +1 (very positive)  
**Use**: Market mood indicator  
**Drift**: Sustained negative trend → Market pessimism, more downgrades

### Panel 7: Entities Extracted (Top 10)
**What**: Most frequent entity types  
**Typical**: ORG, PERSON, MONEY dominant  
**Anomaly**: Spike in GPE (locations) → Geopolitical events

### Panel 8-9: Regimes
**What**: Current market and load regimes  
**Market**: CALM (green), NORMAL (blue), STRESS (red)  
**Load**: LOW_LOAD (green), NORMAL_LOAD (blue), HIGH_LOAD (orange)  
**Use**: Understand threshold adjustments

---

## Configuration Tuning

### Adding Keywords
Edit `config/triage_stage2.yaml`:
```yaml
keywords:
  impact:
    custom_category:
      - "new_term_1"
      - "new_term_2"
```
Restart service to apply.

### Adjusting Source Quality
```yaml
source_quality:
  rss:
    new_source:
      reliability: 0.75
      noise: 0.30
```

### Updating Ticker Whitelist
Edit `config/tickers_whitelist.csv`:
```csv
symbol
AAPL
TSLA
NEW_TICKER
```
Service reloads on restart.

### Threshold Tuning
Baseline thresholds:
```yaml
thresholds:
  baseline:
    P0: 85  # Stricter (fewer P0)
    P1: 65
    P2: 45
```

Regime adjustments:
```yaml
thresholds:
  market_regime:
    STRESS:
      P0: -15  # More aggressive boost
```

---

## Troubleshooting

### Issue: No events in output topic
**Check**:
1. Stage 1 producing to `events.stage1.fast.v1` and `events.stage1.standard.v1`?
   ```bash
   docker exec redpanda rpk topic consume events.stage1.fast.v1 --num 1
   ```
2. Triage Stage 2 healthy?
   ```bash
   curl http://localhost:8007/health
   ```
3. Logs for errors:
   ```bash
   docker logs triage-stage2 --tail 100
   ```

### Issue: All events go to DLQ
**Cause**: Schema validation failure or NLP model crash  
**Fix**:
1. Check DLQ topic:
   ```bash
   docker exec redpanda rpk topic consume events.triaged.dlq.v1 --num 1
   ```
2. Check error messages in event
3. Verify input schema matches Stage 1 output
4. Restart service if model loading failed

### Issue: High latency (> 1s)
**Cause**: Large batch size or CPU bottleneck  
**Fix**:
1. Check FinBERT batch size in config:
   ```yaml
   nlp:
     finbert:
       batch_size: 4  # Reduce from 8
   ```
2. Scale horizontally (add consumer instances)
3. Consider GPU for FinBERT (set `device: cuda`)

### Issue: Incorrect sentiment scores
**Cause**: Text language mismatch or truncation  
**Check**:
1. Verify `lang` field (en/fr)
2. Check `quality_flags` for `TEXT_TRUNCATED`
3. Review `normalized_text` length (max 1000 chars)

### Issue: Missing tickers
**Cause**: Ticker not in whitelist or low confidence  
**Fix**:
1. Add ticker to `config/tickers_whitelist.csv`
2. Lower confidence threshold:
   ```yaml
   tickers:
     confidence_threshold: 0.50  # From 0.60
   ```

---

## Performance Targets

| Metric | Target | Measured |
|--------|--------|----------|
| Throughput | 100k events/day | p95 latency |
| Latency p95 | < 500ms | Prometheus |
| DLQ Rate | < 1% | Grafana |
| Entity Recall | > 85% | Manual review |
| Sentiment Accuracy | > 75% | Labeled dataset |

**Bottlenecks**:
- **FinBERT inference**: 100-300ms per event (use batching)
- **spaCy NER**: 20-50ms per event
- **Kafka roundtrip**: 10-30ms

**Optimization**:
- Batch inference: Process 8-16 events together
- Caching: VIX and whitelist loaded once
- Async I/O: Kafka producer/consumer non-blocking

---

## Output Schema

See [`schemas/triaged_event.v1.json`](../schemas/triaged_event.v1.json) for complete schema.

**Key Fields**:
```json
{
  "event_id": "unique-id",
  "triage_score": 85.2,
  "priority": "P0",
  "triage_reasons": ["KEYWORD_EARNINGS", "STRONG_SENTIMENT"],
  "score_breakdown": {
    "keywords": 25,
    "source_quality": 23.75,
    "ticker_confidence": 19,
    "entity_strength": 8.5,
    "sentiment_impact": 9
  },
  "entities": [
    {"type": "ORG", "text": "Apple Inc.", "confidence": 0.95}
  ],
  "tickers": [
    {"symbol": "AAPL", "confidence": 0.95, "method": "inherited"}
  ],
  "sentiment": {
    "score": 0.72,
    "confidence": 0.88,
    "model": "finbert",
    "label": "positive"
  },
  "regime": {
    "market_regime": "NORMAL",
    "load_regime": "LOW_LOAD"
  }
}
```

---

## Running Tests

```bash
# Ensure services are running
docker compose --profile apps --profile observability up -d

# Wait for Stage 2 to be ready
curl http://localhost:8007/health

# Run integration tests
python tests/integration/test_triage_stage2.py --bootstrap-servers localhost:9092

# Check Grafana dashboard
open http://localhost:3001/d/triage-stage2
```

**Expected Test Results**:
- Test 1 (French earnings): P0/P1, entities extracted, keyword match
- Test 2 (Nvidia ticker): P0/P1, NVDA ticker, positive sentiment
- Test 3 (Low entity): P3, NO_ENTITIES flag, low score
- Test 4 (SEC investigation): P0, regulatory keyword, negative sentiment
- Test 5 (Reddit low-quality): P3, LOW_SOURCE_QUALITY flag

---

## Next Steps

After Triage Stage 2, events flow to:
1. **Triage Stage 3**: Symbol resolution and market context
2. **Triage Stage 4**: Final enrichment before feature extraction
3. **Feature Store**: Time-series feature computation
4. **ML Pipeline**: Signal prediction and strategy generation

---

## References

- [spaCy Documentation](https://spacy.io/usage)
- [FinBERT Paper](https://arxiv.org/abs/1908.10063)
- [Triage Stage 1 README](triage_stage1.md)
- [Architecture Overview](00_overview.md)
