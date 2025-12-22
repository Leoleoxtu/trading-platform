# NLP Enrichment Service

## Overview

The NLP Enrichment Service is a critical component in the trading platform pipeline that transforms normalized events into enriched events with additional intelligence extracted through Natural Language Processing (NLP) techniques.

## Purpose

- **Named Entity Recognition (NER)**: Extract organizations, persons, products, countries, and other entities
- **Ticker Resolution**: Validate and resolve trading symbols with confidence scoring
- **Sentiment Analysis**: Analyze text sentiment with financial market focus
- **Event Categorization**: Classify events into categories (macro, earnings, regulation, etc.)
- **Text Embeddings** (optional): Generate vector representations for similarity search

## Architecture

```
events.normalized.v1 → NLP Enricher → events.enriched.v1
                            ↓
                    events.enriched.dlq.v1 (errors)
                            ↓
                    MinIO: pipeline-artifacts (audit)
```

## Data Flow

1. **Consume**: Read normalized events from `events.normalized.v1`
2. **Validate**: Verify input against `schemas/normalized_event.v1.json`
3. **Enrich**: Apply NLP models and heuristics
4. **Audit**: Store enriched output in MinIO (optional, enabled by default)
5. **Produce**: Publish enriched events to `events.enriched.v1`
6. **Error Handling**: Send failures to `events.enriched.dlq.v1`

## Schema

All enriched events conform to `schemas/enriched_event.v1.json` with strict validation.

Key fields:
- `entities`: Extracted named entities (ORG, PERSON, PRODUCT, etc.)
- `tickers`: Validated trading symbols with confidence scores
- `sentiment`: Financial sentiment analysis (-1 to +1 scale)
- `event_category`: Event classification (macro, earnings, regulation, etc.)
- `embedding`: Optional vector representation metadata
- `quality_flags`: Data quality indicators

See [schemas/enriched_event.v1.json](../schemas/enriched_event.v1.json) for complete schema.

## NLP Models

### Named Entity Recognition (NER)
- **Primary**: spaCy with lightweight English model (en_core_web_sm)
- **Fallback**: Heuristic extraction (capitalized words, patterns)
- **Entity Types**: ORG, PERSON, PRODUCT, COUNTRY, EVENT, OTHER
- **Output**: Entities with confidence scores (0.0 to 1.0)

### Ticker Resolution
- **Method**: Multi-stage validation
  1. Extract candidates from `symbols_candidates` (from normalizer)
  2. Apply whitelist validation (TICKER_WHITELIST environment variable)
  3. Pattern matching for common formats
  4. Source-specific mapping (configured per source)
- **Confidence Scoring**: Based on validation method used
- **Goal**: Reduce false positives from all-caps words

### Sentiment Analysis
- **Model**: vaderSentiment (optimized for social media and news)
- **Alternative**: TextBlob (simpler, general-purpose)
- **Output**: 
  - `score`: -1.0 (very negative) to +1.0 (very positive)
  - `confidence`: 0.0 to 1.0
  - `model`: Model identifier used

### Event Categorization
- **Method**: Keyword-based heuristic classification
- **Categories**:
  - `macro`: Economic indicators, central bank decisions, policy changes
  - `earnings`: Company earnings reports, guidance, financial results
  - `regulation`: Legal, regulatory, compliance news
  - `security`: Security breaches, hacks, vulnerabilities
  - `product`: Product launches, updates, innovations
  - `market`: General market movements, trends
  - `company`: Company-specific news (M&A, leadership, etc.)
  - `crypto`: Cryptocurrency-specific events
  - `other`: Uncategorized events

### Text Embeddings (Optional)
- **Model**: sentence-transformers (e.g., all-MiniLM-L6-v2)
- **Purpose**: Enable semantic similarity search and clustering
- **Storage**: Metadata stored in event, vectors in separate store if needed
- **Status**: Disabled by default (set `ENABLE_EMBEDDINGS=true` to enable)

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `redpanda:29092` | Kafka broker address |
| `KAFKA_TOPIC_NORMALIZED` | `events.normalized.v1` | Input topic |
| `KAFKA_TOPIC_ENRICHED` | `events.enriched.v1` | Output topic |
| `KAFKA_TOPIC_DLQ` | `events.enriched.dlq.v1` | Dead letter queue |
| `KAFKA_CONSUMER_GROUP` | `nlp-enricher-v1` | Consumer group ID |
| `MINIO_ENDPOINT` | `http://minio:9000` | MinIO endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin123` | MinIO secret key |
| `MINIO_BUCKET_ARTIFACTS` | `pipeline-artifacts` | Audit bucket |
| `WRITE_ENRICHED_TO_MINIO` | `true` | Enable MinIO audit trail |
| `ENABLE_EMBEDDINGS` | `false` | Enable embedding generation |
| `TICKER_WHITELIST` | (see below) | Comma-separated ticker symbols |
| `PIPELINE_VERSION` | `nlp-enricher.v1.0` | Version identifier |
| `HEALTH_PORT` | `8000` | Health/metrics HTTP port (container) |
| `USE_SPACY` | `false` | Enable spaCy for NER (requires model download) |

### Ticker Whitelist

Default whitelist includes major US equities and crypto symbols:
```
AAPL,MSFT,GOOGL,GOOG,AMZN,TSLA,META,NVDA,BRK.A,BRK.B,JPM,JNJ,V,PG,UNH,
BTC,ETH,BNB,XRP,ADA,DOGE,SOL,DOT,MATIC
```

Override via `TICKER_WHITELIST` environment variable (comma-separated).

## MinIO Audit Trail

When enabled (`WRITE_ENRICHED_TO_MINIO=true`), every enriched event is stored in MinIO:

**Path Pattern**:
```
pipeline-artifacts/enriched/source=<source_type>/dt=YYYY-MM-DD/<event_id>.json
```

**Example**:
```
pipeline-artifacts/enriched/source=rss/dt=2024-01-15/550e8400-e29b-41d4-a716-446655440000.json
```

**Purpose**:
- Audit trail for compliance and debugging
- Replay capability for reprocessing
- Versioning and experiment tracking

## Observability

### Health Endpoint

**GET /health**
```json
{
  "status": "healthy",
  "service": "nlp-enricher",
  "stats": {
    "consumed": 1234,
    "enriched": 1200,
    "failed": 10,
    "dlq_count": 10
  }
}
```

### Metrics Endpoint

**GET /metrics** - Prometheus format

#### Key Metrics

**Counters**:
- `nlp_enricher_events_consumed_total`: Total events consumed
- `nlp_enricher_events_enriched_total`: Total events enriched successfully
- `nlp_enricher_events_failed_total{stage}`: Failures by stage
- `nlp_enricher_dlq_published_total`: Events sent to DLQ
- `nlp_enricher_low_confidence_total{kind}`: Low confidence detections
- `nlp_enricher_category_total{category}`: Events by category

**Histograms**:
- `nlp_enricher_processing_duration_seconds`: End-to-end processing time
- `nlp_enricher_sentiment_duration_seconds`: Sentiment analysis time
- `nlp_enricher_entities_duration_seconds`: Entity extraction time
- `nlp_enricher_embedding_duration_seconds`: Embedding generation time

**Gauges**:
- `nlp_enricher_last_success_timestamp`: Last successful processing timestamp
- `nlp_enricher_sentiment_mean`: Moving average of sentiment scores (drift detection)

### Grafana Dashboard

The "Pipeline Health" dashboard includes enrichment-specific panels:

1. **Enrichment Throughput**: Events enriched per second
2. **Enrichment DLQ Rate**: Failed events per second
3. **Enrichment Latency (p95)**: 95th percentile processing time
4. **Sentiment Drift**: Moving average of sentiment scores over time
5. **Event Categories**: Distribution of event classifications
6. **Processing Stages**: Failure breakdown by stage

Access at: http://localhost:3001/dashboards (login: admin/admin)

## Error Handling

### DLQ Structure

Failed events are sent to `events.enriched.dlq.v1` with metadata:

```json
{
  "event_id": "550e8400-...",
  "correlation_id": "660e8400-...",
  "failed_at_utc": "2024-01-15T10:30:00Z",
  "error_type": "SCHEMA_INVALID|NER_FAILED|SENTIMENT_FAILED|...",
  "error_message": "Detailed error description",
  "failed_stage": "schema|ner|tickers|sentiment|category|embed|produce|minio",
  "original_payload": {...}
}
```

### Error Types

- `SCHEMA_INVALID`: Input doesn't match normalized_event.v1.json
- `NER_FAILED`: Named entity extraction failure
- `TICKER_FAILED`: Ticker resolution error
- `SENTIMENT_FAILED`: Sentiment analysis error
- `CATEGORY_FAILED`: Categorization error
- `EMBED_FAILED`: Embedding generation error (if enabled)
- `PRODUCE_FAILED`: Kafka production error
- `MINIO_FAILED`: MinIO audit write error

## Quality Flags

The enricher adds quality flags to help downstream consumers:

- `LOW_TEXT`: Input text too short (< 20 chars)
- `LANG_UNKNOWN`: Language detection failed
- `TICKERS_UNCERTAIN`: Low confidence ticker matches
- `ENTITIES_UNCERTAIN`: Low confidence entity extractions
- `SENTIMENT_NEUTRAL`: No clear sentiment signal
- `CATEGORY_UNCERTAIN`: Couldn't confidently categorize

## Operational Commands

### Start the Service

```bash
cd infra
docker compose --profile apps --profile observability up -d
```

### Check Health

```bash
curl http://localhost:8005/health
```

### View Metrics

```bash
curl http://localhost:8005/metrics
```

### Consume Enriched Events

```bash
docker exec -it redpanda rpk topic consume events.enriched.v1 \
  --brokers redpanda:29092 -n 10
```

### Check DLQ

```bash
docker exec -it redpanda rpk topic consume events.enriched.dlq.v1 \
  --brokers redpanda:29092 -n 10
```

### View MinIO Artifacts

Browse to http://localhost:9001 (login: minioadmin/minioadmin123)
Navigate to: `pipeline-artifacts/enriched/`

### View Logs

```bash
docker compose logs -f nlp-enricher
```

## Performance Considerations

### Resource Usage
- **Memory**: ~500MB-1GB (depends on spaCy model)
- **CPU**: 1-2 cores recommended
- **Throughput**: ~100-500 events/second (depends on text length and models)

### Optimization Tips
1. Disable embeddings if not needed (saves CPU and memory)
2. Use lighter spaCy model or heuristic fallback for NER
3. Adjust batch size via Kafka consumer configuration
4. Consider disabling MinIO audit for very high throughput scenarios
5. Use ticker whitelist to reduce false positives

## Future Enhancements

- [ ] Integration with FinBERT for financial sentiment
- [ ] LLM-based entity extraction and categorization
- [ ] Vector database integration (Qdrant/Weaviate) for embeddings
- [ ] Real-time ticker validation via market data APIs
- [ ] Multi-language support beyond English
- [ ] Anomaly detection for drift monitoring
- [ ] A/B testing framework for model comparisons

## Troubleshooting

### Service Not Starting
- Check Docker logs: `docker compose logs nlp-enricher`
- Verify Kafka connectivity: `docker exec redpanda rpk cluster info`
- Verify MinIO connectivity: `docker exec -it nlp-enricher curl http://minio:9000/minio/health/live`

### No Events Being Enriched
- Check if normalizer is producing: `docker exec redpanda rpk topic consume events.normalized.v1 -n 1`
- Check consumer lag: `docker exec redpanda rpk group describe nlp-enricher-v1`
- Check service logs for errors

### High DLQ Rate
- Check DLQ messages for error patterns
- Verify input schema matches normalized_event.v1.json
- Check if models are loading correctly (spaCy, vaderSentiment)
- Verify resource limits aren't causing crashes

### Slow Processing
- Check Prometheus metrics for bottlenecks
- Verify CPU/memory usage: `docker stats nlp-enricher`
- Consider disabling embeddings
- Check MinIO latency if enabled

## References

- [NormalizedEvent Schema](../schemas/normalized_event.v1.json)
- [EnrichedEvent Schema](../schemas/enriched_event.v1.json)
- [Pipeline Overview](00_overview.md)
- [Operations Guide](90_operations.md)
