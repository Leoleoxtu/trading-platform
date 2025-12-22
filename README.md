# Trading Platform - Local Infrastructure

Real-time data trading platform infrastructure based on Redpanda (Kafka) and MinIO (S3).

## Quick Start

```bash
# 1. Copy environment configuration
cd infra
cp .env.example .env

# 2. Start all services
docker compose up -d

# 3. Verify services are running
docker compose ps
```

## Access Points

| Service | URL | Purpose |
|---------|-----|---------|
| **Kafka UI** | http://localhost:8080 | Browse topics, view messages |
| **MinIO Console** | http://localhost:9001 | Browse S3 buckets (login: minioadmin/minioadmin123) |
| **Redpanda (Kafka)** | localhost:9092 | Kafka API for applications |
| **MinIO S3 API** | localhost:9000 | S3 API for applications |
| **RSS Ingestor** | http://localhost:8001 | Health/metrics endpoints |
| **Normalizer** | http://localhost:8002 | Health/metrics endpoints |
| **Reddit Ingestor** | http://localhost:8003 | Health/metrics endpoints |
| **Market Ingestor** | http://localhost:8004 | Health/metrics endpoints |
| **TimescaleDB** | localhost:5432 | PostgreSQL with TimescaleDB extension |
| **Prometheus** | http://localhost:9090 | Metrics and queries |
| **Grafana** | http://localhost:3001 | Dashboards (admin/admin) |

## What's Included

### Services
- **Redpanda**: Kafka-compatible streaming platform
- **MinIO**: S3-compatible object storage
- **Kafka UI**: Web interface for Kafka
- **Auto-initialization**: Topics and buckets created automatically

### Topics (Auto-created)
- `raw.events.v1` (6 partitions) - Raw events from all sources
- `raw.events.dlq.v1` (1 partition) - Dead letter queue for raw events
- `events.normalized.v1` (6 partitions) - Normalized events
- `events.normalized.dlq.v1` (1 partition) - Dead letter queue for normalized events

### S3 Buckets (Auto-created)
- `raw-events` - Long-term storage of raw events
- `pipeline-artifacts` - Intermediate data and pipeline outputs

## Documentation

- **[Overview](docs/00_overview.md)** - Architecture, data flow, and conventions
- **[Ingestion - RSS](docs/10_ingestion.md)** - RSS feed ingestion service
- **[Ingestion - Reddit](docs/15_reddit_ingestion.md)** - Reddit submissions and comments ingestion
- **[Ingestion - Market Data](services/ingestors/market/README.md)** - OHLCV market data from Yahoo Finance
- **[Normalization](docs/20_normalization.md)** - Event normalization service
- **[Operations Guide](docs/90_operations.md)** - Commands, troubleshooting, and acceptance tests

## System Requirements

- Docker Desktop with WSL2 (Windows) or Docker Engine (Linux/Mac)
- At least 4GB available RAM
- Docker Compose V2

## Architecture

```
External Sources → Redpanda (Kafka) → Processing Services
                       ↓
                   MinIO (S3) - Long-term storage
```

Data flows through stages:
1. **Raw Events** - Unprocessed data from sources
2. **Normalized Events** - Standardized schema
3. **(Future) Enriched Events** - Enhanced with additional data

## Common Commands

```bash
# Start services
cd infra
docker compose up -d

# Stop services
docker compose down

# Stop and remove all data
docker compose down -v

# View logs
docker compose logs -f

# Check topics
docker exec -it redpanda rpk topic list --brokers redpanda:29092

# Check status
docker compose ps
```

## Development

This infrastructure is ready for connecting:
- Data ingestion services (RSS, Reddit, Twitter, Market data, Finnhub)
- Stream processing applications
- Data normalization services
- Analytics and visualization tools

### Implemented Services (Phase 1)
- **RSS Ingestor**: Polls RSS feeds and publishes to Kafka
- **Reddit Ingestor**: Collects Reddit submissions/comments via PRAW
- **Normalizer**: Normalizes events from various sources
- **Market Ingestor**: Fetches OHLCV market data from Yahoo Finance into TimescaleDB
- **Observability**: Prometheus + Grafana with comprehensive dashboards

## Support

For detailed troubleshooting, see [docs/90_operations.md](docs/90_operations.md).

## License

See LICENSE file for details.
