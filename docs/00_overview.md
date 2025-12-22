# Overview - Trading Platform Local Infrastructure

## Architecture

This repository contains the local infrastructure setup (Phase 1) for a real-time data trading platform. The infrastructure is designed to be local-first, plug-and-play, and ready for connecting data ingestion services later.

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

## Data Flow (Target Architecture)

The platform is designed to handle the following data flow:

```
External Sources → Raw Events → Normalized Events → Enriched Events → Analytics
                      ↓              ↓                    ↓
                   raw.events.v1  events.normalized.v1  (future)
                      ↓              ↓
                   S3: raw-events  S3: pipeline-artifacts
```

### Stage Descriptions

1. **Raw Events** - Unprocessed events from various sources (RSS, Twitter, Reddit, Market, Finnhub)
2. **Normalized Events** - Standardized schema and format
3. **Enriched Events** - (Future) Enhanced with additional data
4. **Analytics** - (Future) Aggregated and analyzed data

## Topics

All topics are created automatically at startup:

| Topic Name | Partitions | Purpose |
|------------|------------|---------|
| `raw.events.v1` | 6 | Raw events from all sources |
| `raw.events.dlq.v1` | 1 | Dead Letter Queue for raw events that failed processing |
| `events.normalized.v1` | 6 | Normalized events in standard schema |
| `events.normalized.dlq.v1` | 1 | Dead Letter Queue for normalization failures |

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
- RSS feed ingestion service
- Twitter/X API ingestion service
- Reddit API ingestion service
- Market data ingestion service
- Finnhub financial data ingestion service
- Data normalization service
- Data enrichment service
- Stream processing applications
- Observability stack (Prometheus, Grafana)

## Design Principles

1. **Local-First** - No Kubernetes, runs on Docker Desktop + WSL2
2. **Plug-and-Play** - One command to start everything
3. **Idempotent** - Safe to restart and re-run initialization
4. **Production-Like** - Uses the same tools and patterns as production
5. **Developer-Friendly** - Clear logs, easy debugging, web UIs
