# Normalization Service

## Overview

The normalizer consumes raw events from Kafka, downloads raw content from MinIO, normalizes and enriches the data, and publishes NormalizedEvent v1 messages. Failed events are sent to a Dead Letter Queue (DLQ).

## Architecture

```
Kafka (raw.events.v1) → Normalizer → Kafka (events.normalized.v1)
         ↓                   ↓
    MinIO (raw-events)    DLQ (events.normalized.dlq.v1)
```

## Features

- **Schema validation**: Validates both input and output against schemas
- **Content normalization**: Cleans and standardizes text
- **Language detection**: Automatically detects content language
- **Symbol extraction**: Identifies potential ticker symbols (e.g., AAPL, MSFT)
- **Deduplication**: SQLite-based persistent deduplication with `dedup_key`
- **Source scoring**: Assigns quality scores based on content completeness
- **Dead Letter Queue**: Failed events sent to DLQ with error details
- **Idempotent**: Same event won't be processed twice
- **Health checks**: HTTP endpoint for monitoring

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `redpanda:9092` | Kafka broker addresses |
| `KAFKA_TOPIC_RAW` | `raw.events.v1` | Input topic (raw events) |
| `KAFKA_TOPIC_NORMALIZED` | `events.normalized.v1` | Output topic (normalized events) |
| `KAFKA_TOPIC_DLQ` | `events.normalized.dlq.v1` | Dead Letter Queue topic |
| `KAFKA_CONSUMER_GROUP` | `normalizer-v1` | Consumer group ID |
| `MINIO_ENDPOINT` | `http://minio:9000` | MinIO S3 API endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin123` | MinIO secret key |
| `HEALTH_PORT` | `8000` | Port for health check endpoint |
| `DEDUP_DB_PATH` | `/data/dedup.db` | Path to SQLite deduplication database |
| `PIPELINE_VERSION` | `normalizer.v1.0` | Pipeline version identifier |

## Deployment

### Via Docker Compose (Recommended)

```bash
cd infra

# Start with apps profile
docker compose --profile apps up -d

# Check logs
docker compose logs -f normalizer

# Check health
curl http://localhost:8002/health
```

### Build Manually

```bash
cd services/normalizer

# Build image
docker build -t normalizer:latest .

# Run container
docker run -d \
  --name normalizer \
  --network infra_trading-platform \
  -e KAFKA_BOOTSTRAP_SERVERS=redpanda:29092 \
  -e MINIO_ENDPOINT=http://minio:9000 \
  -v normalizer_data:/data \
  -p 8002:8000 \
  normalizer:latest
```

## Operation

### Health Check

```bash
curl http://localhost:8002/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "normalizer",
  "stats": {
    "processed": 123,
    "dedup_hits": 5,
    "dlq_count": 2,
    "errors": 0
  }
}
```

### View Logs

```bash
# Follow logs
docker compose logs -f normalizer

# Last 100 lines
docker compose logs --tail=100 normalizer

# Filter by level (requires jq)
docker compose logs normalizer | grep '"level":"ERROR"'
```

### Restart Service

```bash
cd infra
docker compose restart normalizer
```

### Check Normalized Events

View in Kafka:
```bash
# List recent normalized events
docker exec -it redpanda rpk topic consume events.normalized.v1 -n 5

# Follow new events
docker exec -it redpanda rpk topic consume events.normalized.v1 -f
```

View in Kafka UI: http://localhost:8080
- Navigate to Topics → `events.normalized.v1` → Messages

### Check DLQ

```bash
# View DLQ messages
docker exec -it redpanda rpk topic consume events.normalized.dlq.v1 -n 10
```

## Data Flow

### 1. Consume Raw Event

1. Consumer polls `raw.events.v1` topic
2. Deserializes JSON message
3. Validates against `raw_event.v1.json` schema
4. If invalid → send to DLQ

### 2. Download Raw Content

1. Extract `raw_uri` from event (e.g., `s3://raw-events/...`)
2. Download content from MinIO
3. Parse JSON
4. If download fails → send to DLQ

### 3. Normalize Content

1. Extract and concatenate `title` + `summary` + `content`
2. Remove excessive whitespace
3. Detect language using `langdetect`
4. Extract canonical URL from raw content
5. Extract potential ticker symbols using regex

### 4. Calculate Dedup Key

```
dedup_key = SHA256(normalized_text + canonical_url + source_name)
```

Check SQLite database:
- If exists → log "dedup_hit", skip processing (return success)
- If new → continue

### 5. Enrich Metadata

1. Calculate source score (0.0 to 1.0) based on:
   - Content quality (title length, summary length)
   - Metadata completeness (author, published date)
   - Source type bonus
2. Generate quality flags:
   - `has_symbols`: Ticker symbols found
   - `high_confidence`: source_score ≥ 0.7
   - `language_detected`: Language identified

### 6. Publish Normalized Event

1. Create NormalizedEvent v1 with all fields
2. Validate against `normalized_event.v1.json` schema
3. Publish to `events.normalized.v1` topic
4. Wait for broker acknowledgment
5. Store `dedup_key` in SQLite database
6. Commit Kafka offset

## Deduplication

### Strategy

The normalizer uses **content-based deduplication** via SHA-256 hash:

```
dedup_key = SHA256(normalized_text + "|" + canonical_url + "|" + source_name)
```

This means:
- **Same content from same source** → duplicate
- **Same content from different sources** → NOT duplicate (different source_name)
- **Different content from same URL** → NOT duplicate (different normalized_text)

### Storage

Dedup keys are stored in SQLite database at `/data/dedup.db`:

```sql
CREATE TABLE dedup_keys (
    dedup_key TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    processed_at TEXT NOT NULL
)
```

### Persistence

- Database stored in Docker volume `normalizer_data`
- Survives container restarts
- No TTL/expiration (keys stored forever)

### Reset Deduplication

To reset and reprocess all events:

```bash
# Stop service
docker compose stop normalizer

# Remove database
docker volume rm infra_normalizer_data

# Restart (will reprocess from last committed offset)
docker compose --profile apps up -d normalizer
```

### Dedup Hits

When a duplicate is detected:
- Event is NOT published again
- `stats.dedup_hits` counter incremented
- Kafka offset committed (event marked as processed)
- No error, it's expected behavior

## Dead Letter Queue (DLQ)

### Error Types

Events sent to DLQ with these error types:

| Error Type | Description | Failed Stage |
|------------|-------------|--------------|
| `schema_validation_error` | Raw or normalized event schema invalid | `validation` |
| `missing_field` | Required field missing (e.g., `raw_uri`) | `download` |
| `download_error` | Failed to download from MinIO | `download` |
| `normalization_error` | Empty normalized text | `normalization` |
| `processing_error` | Unexpected exception | `processing` |

### DLQ Message Format

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "correlation_id": "660e8400-e29b-41d4-a716-446655440001",
  "error_type": "download_error",
  "error_message": "Failed to download from MinIO: NoSuchKey",
  "failed_stage": "download",
  "failed_at_utc": "2024-01-15T10:30:00Z",
  "original_event": { ... }
}
```

### Handling DLQ Messages

1. **Investigate**: Use correlation_id to trace through logs
2. **Fix root cause**: Update raw data, fix bugs, etc.
3. **Replay**: Use Kafka consumer to replay DLQ messages

Example replay script:
```python
from kafka import KafkaConsumer, KafkaProducer

consumer = KafkaConsumer('events.normalized.dlq.v1', ...)
producer = KafkaProducer(...)

for msg in consumer:
    dlq_event = msg.value
    original = dlq_event['original_event']
    
    # Re-publish to raw.events.v1 for reprocessing
    producer.send('raw.events.v1', value=original)
```

## Schema Validation

### Input Validation

All incoming raw events validated against `schemas/raw_event.v1.json`:
- `schema_version` must be `"raw_event.v1"`
- All required fields present
- UUIDs valid format
- S3 URI format correct
- Timestamps in RFC3339 format

### Output Validation

All outgoing normalized events validated against `schemas/normalized_event.v1.json`:
- `schema_version` must be `"normalized_event.v1"`
- `dedup_key` present and valid SHA-256
- `source_score` in range [0, 1]
- Language code matches pattern (e.g., "en", "fr")

If validation fails → sent to DLQ, NOT published.

## Normalization Logic

### Text Normalization

```python
normalized_text = title + " " + summary
normalized_text = re.sub(r'\s+', ' ', normalized_text).strip()
```

- Concatenates title and summary
- Removes multiple spaces
- Trims whitespace

**Future enhancements**:
- HTML tag removal
- URL extraction and removal
- Entity extraction (companies, people, places)
- Sentiment analysis

### Language Detection

Uses `langdetect` library:
- Returns ISO 639-1 code (e.g., "en", "fr", "es")
- If detection fails → defaults to "en"
- Low confidence → "unknown"

### Symbol Extraction

Basic regex pattern: `\b[A-Z]{2,5}\b`

- Finds 2-5 uppercase letter sequences
- Filters out common words (THE, AND, etc.)
- Returns up to 10 candidates
- Case-sensitive

**Limitations**:
- Many false positives (acronyms, proper nouns)
- Misses crypto pairs (e.g., BTC/USD)
- No validation against real ticker lists

**Future enhancements**:
- Validate against actual ticker databases
- Support crypto pairs and forex
- Context-aware extraction

### Source Scoring

Base score: 0.5

Bonuses:
- +0.1 if source_type is "rss"
- +0.1 if title length > 10 chars
- +0.1 if summary length > 50 chars
- +0.05 if author present
- +0.05 if published date present

Max score: 1.0

**Future enhancements**:
- Historical source reliability tracking
- User feedback integration
- Machine learning model

## Troubleshooting

### Service Won't Start

**Check dependencies:**
```bash
cd infra
docker compose ps
```

Ensure `redpanda`, `minio`, and `rss-ingestor` are healthy.

**Check logs:**
```bash
docker compose logs normalizer
```

### No Events Being Processed

**Check if raw events exist:**
```bash
docker exec -it redpanda rpk topic consume raw.events.v1 -n 1
```

**Check consumer group lag:**
```bash
docker exec -it redpanda rpk group describe normalizer-v1
```

### All Events Going to DLQ

**Check schema versions:**
Ensure raw events have `schema_version: "raw_event.v1"`

**Check MinIO connectivity:**
```bash
docker exec -it normalizer python -c "import boto3; s3 = boto3.client('s3', endpoint_url='http://minio:9000', aws_access_key_id='minioadmin', aws_secret_access_key='minioadmin123'); print(s3.list_buckets())"
```

### Database Locked Errors

If SQLite errors occur:
```bash
# Stop service
docker compose stop normalizer

# Check database
docker exec -it normalizer sqlite3 /data/dedup.db "PRAGMA integrity_check;"

# If corrupted, reset
docker volume rm infra_normalizer_data
```

## Performance

### Throughput
- **Processing**: ~50-100 events/second (depends on MinIO latency)
- **Bottleneck**: MinIO download and language detection

### Resource Usage
- **Memory**: ~150-250 MB
- **CPU**: ~10-20% average
- **Disk**: SQLite database grows ~1KB per event

### Scaling

For higher throughput:

1. **Horizontal scaling**: Run multiple instances with same consumer group
2. **Increase partitions**: More partitions in `raw.events.v1` topic
3. **Optimize MinIO**: Use MinIO gateway or S3 for better performance

Example scaling:
```bash
# Create 3 normalizer instances
docker compose --profile apps up -d --scale normalizer=3
```

Kafka will auto-balance partitions across instances.

## Example Logs

Successful processing:
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "service": "normalizer",
  "message": {
    "message": "Published normalized event",
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "dedup_key": "b4c6d8e0f2a1b3c5d7e9f1a3b5c7d9e1...",
    "lang": "en",
    "symbols_count": 3,
    "topic": "events.normalized.v1"
  }
}
```

Duplicate detected:
```json
{
  "timestamp": "2024-01-15T10:31:00Z",
  "level": "INFO",
  "service": "normalizer",
  "message": {
    "message": "Duplicate event detected",
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "dedup_key": "b4c6d8e0f2a1b3c5d7e9f1a3b5c7d9e1..."
  }
}
```

DLQ message:
```json
{
  "timestamp": "2024-01-15T10:32:00Z",
  "level": "WARNING",
  "service": "normalizer",
  "message": {
    "message": "Sent to DLQ",
    "event_id": "660e8400-e29b-41d4-a716-446655440002",
    "error_type": "download_error",
    "topic": "events.normalized.dlq.v1"
  }
}
```

## Next Steps

After the normalizer is running:
1. Verify normalized events in `events.normalized.v1` topic
2. Monitor DLQ for errors
3. Check deduplication is working (dedup_hits counter)
4. Trace events using correlation_id from raw to normalized
5. Build downstream consumers for enrichment or analytics

See `docs/90_operations.md` for validation commands and end-to-end testing.
