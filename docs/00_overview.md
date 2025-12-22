# Overview - Trading Platform Local Infrastructure

## Architecture

This repository contains the local infrastructure setup (Phase 1) for a real-time data trading platform. The infrastructure is designed to be local-first, plug-and-play, and ready for connecting data ingestion services later.

## Data Contracts (Schemas)

All events in the platform follow versioned JSON Schema contracts:

- **`schemas/raw_event.v1.json`**: Schema for raw events from all sources
- **`schemas/normalized_event.v1.json`**: Schema for normalized events
- **`schemas/enriched_event.v1.json`**: Schema for NLP-enriched events

See [`schemas/README.md`](../schemas/README.md) for detailed schema documentation, versioning strategy, and validation.

## Components

### Core Services

1. **Redpanda** - Kafka-compatible streaming platform
   - Port: 9092 (Kafka protocol - binary, not HTTP)
   - Purpose: Message broker for event streaming
   - Configuration: Optimized for local development with overprovisioning

2. **MinIO** - S3-compatible object storage
   - Port 9000: S3 API
   - Port 9001: Web Console (UI)
   - Purpose: Storage for raw events and pipeline artifacts

3. **Kafka UI** - Web interface for Kafka/Redpanda
   - Port: 8080
   - Purpose: Browse topics, messages, and cluster status
   - Cluster name: `local-redpanda`

### Initialization Services

4. **init-topics** - Automatic topic creation
   - Runs once at startup
   - Creates all required Kafka topics idempotently
   
5. **init-minio** - Automatic bucket creation
   - Runs once at startup
   - Creates all required S3 buckets idempotently

### Application Services (Phase 1)

6. **rss-ingestor** - RSS feed ingestion service
   - Port: 8001 (health endpoint)
   - Purpose: Poll RSS feeds, store raw content, publish raw events
   - Profile: `apps`
   - See: `docs/10_ingestion.md`

7. **normalizer** - Data normalization service
   - Port: 8002 (health endpoint)
   - Purpose: Normalize raw events, detect language, extract symbols
   - Profile: `apps`
   - See: `docs/20_normalization.md`

8. **nlp-enricher** - NLP enrichment service
   - Port: 8004 (health endpoint)
   - Purpose: Extract entities, resolve tickers, analyze sentiment, categorize events
   - Profile: `apps`
   - See: `docs/30_enrichment.md`

## Data Flow (Target Architecture)

The platform is designed to handle the following data flow:

```
External Sources → Raw Events → Normalized Events → Enriched Events → Analytics
                      ↓              ↓                    ↓
                   raw.events.v1  events.normalized.v1  events.enriched.v1
                      ↓              ↓                    ↓
                   S3: raw-events  S3: pipeline-artifacts  S3: pipeline-artifacts
```

### Stage Descriptions

1. **Raw Events** - Unprocessed events from various sources (RSS, Twitter, Reddit, Market, Finnhub)
2. **Normalized Events** - Standardized schema and format with language detection and deduplication
3. **Enriched Events** - Enhanced with NLP: entities, tickers, sentiment, categorization
4. **Analytics** - (Future) Aggregated and analyzed data

## Topics

All topics are created automatically at startup:

| Topic Name | Partitions | Purpose |
|------------|------------|---------|
| `raw.events.v1` | 6 | Raw events from all sources |
| `raw.events.dlq.v1` | 1 | Dead Letter Queue for raw events that failed processing |
| `events.normalized.v1` | 6 | Normalized events in standard schema |
| `events.normalized.dlq.v1` | 1 | Dead Letter Queue for normalization failures |
| `events.enriched.v1` | 6 | Enriched events with NLP (entities, sentiment, tickers) |
| `events.enriched.dlq.v1` | 1 | Dead Letter Queue for enrichment failures |

### Topic Naming Convention

- Format: `<stage>.<entity>.<version>`
- DLQ suffix: `.dlq` before version
- Versions: `v1`, `v2`, etc. for schema evolution

## S3 Buckets

All buckets are created automatically at startup:

| Bucket Name | Purpose |
|-------------|---------|
| `raw-events` | Long-term storage of raw events |
| `pipeline-artifacts` | Intermediate data, models, and pipeline outputs |

### S3 Path Convention

For raw events stored in S3:
```
raw-events/
  source=<source_type>/
    dt=YYYY-MM-DD/
      <event_id>.json
```

Examples:
- `raw-events/source=twitter/dt=2024-01-15/evt_123456.json`
- `raw-events/source=finnhub/dt=2024-01-15/evt_789012.json`

## Access URLs

| Service | URL | Notes |
|---------|-----|-------|
| Kafka UI | http://localhost:8080 | Web interface for Kafka |
| MinIO Console | http://localhost:9001 | Web interface for S3 (login: minioadmin/minioadmin123) |
| RSS Ingestor Health | http://localhost:8001/health | Health check endpoint |
| Normalizer Health | http://localhost:8002/health | Health check endpoint |
| NLP Enricher Health | http://localhost:8004/health | Health check endpoint (Note: conflicts with Market Ingestor in README) |
| Redpanda Kafka | localhost:9092 | Binary protocol (not HTTP) - use Kafka clients or rpk CLI |
| MinIO S3 API | localhost:9000 | S3-compatible API endpoint |

## Important Notes

### Kafka/Redpanda Port (9092)

⚠️ **Port 9092 is NOT HTTP** - It uses the Kafka binary protocol. You cannot access it from a web browser.

To interact with Kafka:
- Use **Kafka UI** at http://localhost:8080 (web interface)
- Use **rpk** CLI tool (Redpanda's native client)
- Use any Kafka client library in your application code

### Environment Configuration

Configuration is externalized in `infra/.env` (not committed to git):
- Copy `infra/.env.example` to `infra/.env` to customize
- Default values work out of the box
- You can change ports, credentials, and resource limits

## Future Enhancements

This Phase 1 infrastructure is ready for:
- Twitter/X API ingestion service
- Reddit API ingestion service
- Market data ingestion service
- Finnhub financial data ingestion service
- Data enrichment service (symbol validation, company info, sentiment)
- Stream processing applications (real-time aggregations, alerts)
- Observability stack (Prometheus, Grafana) - Phase 1.2 (optional)

Current implementation (Phase 1 + 1.5):
- ✅ RSS feed ingestion
- ✅ Reddit feed ingestion
- ✅ Market data ingestion (TimescaleDB)
- ✅ Data normalization with deduplication
- ✅ NLP enrichment (entities, sentiment, tickers, categorization)
- ✅ Dead Letter Queue for error handling
- ✅ Contract-first with versioned schemas
- ✅ Observability with Prometheus and Grafana

## Design Principles

1. **Local-First** - No Kubernetes, runs on Docker Desktop + WSL2
2. **Plug-and-Play** - One command to start everything
3. **Idempotent** - Safe to restart and re-run initialization
4. **Production-Like** - Uses the same tools and patterns as production
5. **Developer-Friendly** - Clear logs, easy debugging, web UIs
