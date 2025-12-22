# RSS Ingestion Service

## Overview

The RSS ingestor is a service that polls RSS/Atom feeds, downloads content, stores raw data in MinIO, and publishes RawEvent v1 messages to Kafka for downstream processing.

## Architecture

```
RSS Feeds → RSS Ingestor → MinIO (raw-events bucket)
                ↓
         Kafka (raw.events.v1 topic)
```

## Features

- **Multi-feed polling**: Configure multiple RSS feeds via environment variable
- **Configurable polling**: Set custom polling intervals (default: 60 seconds)
- **Deduplication**: In-memory tracking with persistent storage to avoid re-processing
- **Schema validation**: All events validated against `raw_event.v1.json` schema
- **Idempotent**: Safe to restart without duplicating events
- **Health checks**: HTTP endpoint for monitoring
- **Structured logging**: JSON logs with correlation IDs for tracing

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `redpanda:9092` | Kafka broker addresses (comma-separated) |
| `KAFKA_TOPIC_RAW` | `raw.events.v1` | Target Kafka topic for raw events |
| `MINIO_ENDPOINT` | `http://minio:9000` | MinIO S3 API endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin123` | MinIO secret key |
| `MINIO_BUCKET_RAW` | `raw-events` | MinIO bucket for raw event storage |
| `RSS_FEEDS` | TechCrunch feed | Comma-separated list of RSS feed URLs |
| `RSS_POLL_SECONDS` | `60` | Polling interval in seconds |
| `HEALTH_PORT` | `8000` | Port for health check endpoint |
| `DEDUP_STATE_FILE` | `/data/seen_items.json` | Path to deduplication state file |

### Configuring RSS Feeds

Edit `infra/.env` (copy from `infra/.env.example`) and set:

```bash
RSS_FEEDS=https://feeds.feedburner.com/TechCrunch/,https://hnrss.org/newest,https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml
```

Multiple feeds are comma-separated, no spaces.

## Deployment

### Via Docker Compose (Recommended)

```bash
cd infra

# Start with apps profile (includes infrastructure + apps)
docker compose --profile apps up -d

# Check logs
docker compose logs -f rss-ingestor

# Check health
curl http://localhost:8001/health
```

### Build Manually

```bash
cd services/ingestors/rss

# Build image
docker build -t rss-ingestor:latest .

# Run container
docker run -d \
  --name rss-ingestor \
  --network infra_trading-platform \
  -e KAFKA_BOOTSTRAP_SERVERS=redpanda:29092 \
  -e MINIO_ENDPOINT=http://minio:9000 \
  -e RSS_FEEDS=https://feeds.feedburner.com/TechCrunch/ \
  -v rss_data:/data \
  -p 8001:8000 \
  rss-ingestor:latest
```

## Operation

### Health Check

```bash
curl http://localhost:8001/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "rss-ingestor",
  "feeds_count": 2,
  "seen_items": 42
}
```

### View Logs

```bash
# Follow logs
docker compose logs -f rss-ingestor

# Last 100 lines
docker compose logs --tail=100 rss-ingestor

# Since specific time
docker compose logs --since 2024-01-15T10:00:00 rss-ingestor
```

### Restart Service

```bash
cd infra
docker compose restart rss-ingestor
```

### Check Produced Events

View events in Kafka:

```bash
# List recent events
docker exec -it redpanda rpk topic consume raw.events.v1 -n 5

# Follow new events
docker exec -it redpanda rpk topic consume raw.events.v1 -f
```

View in Kafka UI: http://localhost:8080
- Navigate to Topics → `raw.events.v1` → Messages

### Check MinIO Storage

View objects in MinIO Console: http://localhost:9001
- Login: `minioadmin` / `minioadmin123`
- Navigate to `raw-events` bucket
- Check `source=rss/dt=YYYY-MM-DD/` partitions

Or via CLI:
```bash
docker run --rm --network infra_trading-platform minio/mc \
  sh -c 'mc alias set local http://minio:9000 minioadmin minioadmin123 && \
         mc ls --recursive local/raw-events/source=rss/'
```

## Data Flow

### 1. Feed Polling

Every `RSS_POLL_SECONDS` (default 60s):
1. Service polls all configured RSS feeds
2. Parses RSS/Atom XML
3. Extracts items (articles, posts, etc.)

### 2. Deduplication

For each item:
1. Calculate dedup key: `{url}|{published_date}`
2. Check if already seen (in-memory set + persistent file)
3. Skip if duplicate

### 3. Raw Storage

For new items:
1. Generate UUID `event_id`
2. Create JSON document with all item fields
3. Calculate SHA-256 hash of content
4. Upload to MinIO: `s3://raw-events/source=rss/dt=YYYY-MM-DD/{event_id}.json`

### 4. Event Publication

1. Create RawEvent v1 message with:
   - `event_id`, `source_type=rss`, `source_name`, timestamps
   - `raw_uri` (S3 path), `raw_hash`
   - `priority=MEDIUM`, `correlation_id`
2. Validate against `raw_event.v1.json` schema
3. Publish to Kafka topic `raw.events.v1`
4. Wait for broker acknowledgment

## Deduplication Strategy

The ingestor uses a hybrid deduplication approach:

### In-Memory
- Fast lookups during runtime
- Set of seen `{url}|{published_date}` keys
- Cleared on restart if state file missing

### Persistent
- Saved to `/data/seen_items.json` periodically
- Loaded on startup
- Survives container restarts via Docker volume

### Limitations
- Memory grows with number of unique items
- No TTL expiration (all items remembered forever)
- State is local to this instance (not shared across replicas)

**Future improvements**: Use Redis or database for shared, distributed deduplication with TTL.

## Schema Validation

All events are validated against `schemas/raw_event.v1.json` before publication.

If validation fails:
- Event is NOT published
- Error logged with details
- Service continues (does not crash)

Example error log:
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "ERROR",
  "service": "rss-ingestor",
  "message": {
    "error": "Schema validation failed",
    "path": ["raw_uri"],
    "message": "'s3://raw-events/...' does not match '^s3://[a-z0-9-]+/.+'"
  }
}
```

## Troubleshooting

### Service Won't Start

**Check dependencies:**
```bash
cd infra
docker compose ps
```

Ensure `redpanda` and `minio` are healthy.

**Check logs:**
```bash
docker compose logs rss-ingestor
```

### No Events Being Produced

**Check if feeds are reachable:**
```bash
docker exec -it rss-ingestor python -c "import feedparser; print(feedparser.parse('https://feeds.feedburner.com/TechCrunch/'))"
```

**Check Kafka connectivity:**
```bash
docker exec -it rss-ingestor python -c "from kafka import KafkaProducer; p = KafkaProducer(bootstrap_servers='redpanda:29092'); print('OK')"
```

**Check MinIO connectivity:**
```bash
docker exec -it rss-ingestor python -c "import boto3; s3 = boto3.client('s3', endpoint_url='http://minio:9000', aws_access_key_id='minioadmin', aws_secret_access_key='minioadmin123'); print(s3.list_buckets())"
```

### All Items Marked as Duplicates

**Reset deduplication state:**
```bash
# Stop service
docker compose stop rss-ingestor

# Remove state file
docker volume rm infra_rss_ingestor_data

# Restart
docker compose --profile apps up -d rss-ingestor
```

### High Memory Usage

If the seen items set grows too large:

**Option 1**: Restart periodically (state is saved, but set recreated from file)

**Option 2**: Reduce polling frequency:
```bash
# In infra/.env
RSS_POLL_SECONDS=300  # Poll every 5 minutes instead of 1
```

**Option 3**: Manually trim seen_items.json:
```bash
# Keep only last 10000 items
docker exec -it rss-ingestor python -c "
import json
with open('/data/seen_items.json', 'r') as f:
    items = json.load(f)
with open('/data/seen_items.json', 'w') as f:
    json.dump(items[-10000:], f)
"
```

## Performance

### Throughput
- **Polling**: ~1-2 seconds per feed (depends on feed size)
- **Processing**: ~100-200 items/second
- **Bottleneck**: Network I/O to MinIO and Kafka

### Resource Usage
- **Memory**: ~100-200 MB (depends on seen items count)
- **CPU**: < 5% idle, ~20-30% during polling
- **Disk**: Only for state file (~1-10 MB)

### Scaling

Currently single-instance. For higher throughput:

1. **Vertical**: Increase polling frequency or add more feeds
2. **Horizontal**: Run multiple instances with different feed subsets
3. **Future**: Implement consumer group pattern with feed assignment

## Example Logs

Successful item processing:
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "service": "rss-ingestor",
  "message": {
    "message": "Published RawEvent",
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "correlation_id": "660e8400-e29b-41d4-a716-446655440001",
    "url": "https://techcrunch.com/2024/01/15/example-article",
    "topic": "raw.events.v1"
  }
}
```

Duplicate detection:
```json
{
  "timestamp": "2024-01-15T10:31:00Z",
  "level": "DEBUG",
  "service": "rss-ingestor",
  "message": {
    "message": "Item already seen, skipping",
    "url": "https://techcrunch.com/2024/01/15/example-article"
  }
}
```

## Next Steps

After the RSS ingestor is running:
1. Check that raw events appear in `raw.events.v1` topic
2. Verify raw JSON files are stored in MinIO `raw-events` bucket
3. Start the normalizer service to process raw events
4. Monitor health endpoints and logs

See `docs/20_normalization.md` for normalizer documentation.
