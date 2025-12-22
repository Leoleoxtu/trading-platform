# Reddit Ingestion Service

## Overview

The Reddit ingestor is a service that polls Reddit submissions and comments via PRAW (Python Reddit API Wrapper), stores raw data in MinIO, and publishes RawEvent v1 messages to Kafka for downstream processing.

## Architecture

```
Reddit API → Reddit Ingestor → MinIO (raw-events bucket)
                    ↓
             Kafka (raw.events.v1 topic)
```

## Features

- **Multi-subreddit polling**: Configure multiple subreddits via environment variable
- **Flexible mode**: Collect submissions, comments, or both
- **Configurable polling**: Set custom polling intervals (default: 60 seconds)
- **Deduplication**: Persistent tracking to avoid re-processing same posts/comments
- **Schema validation**: All events validated against `raw_event.v1.json` schema
- **Idempotent**: Safe to restart without duplicating events
- **Health checks**: HTTP endpoints for monitoring
- **Prometheus metrics**: Comprehensive observability
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
| `REDDIT_CLIENT_ID` | **(required)** | Reddit API client ID |
| `REDDIT_CLIENT_SECRET` | **(required)** | Reddit API client secret |
| `REDDIT_USER_AGENT` | `trading-platform-ingestor/1.0` | User agent for Reddit API (required) |
| `REDDIT_SUBREDDITS` | `wallstreetbets,stocks` | Comma-separated list of subreddits |
| `REDDIT_MODE` | `submissions` | Collection mode: `submissions`, `comments`, or `both` |
| `REDDIT_POLL_SECONDS` | `60` | Polling interval in seconds |
| `REDDIT_LIMIT_PER_POLL` | `50` | Maximum items to fetch per poll per subreddit |
| `REDDIT_PRIORITY` | `MEDIUM` | Event priority: `HIGH`, `MEDIUM`, or `LOW` |
| `HEALTH_PORT` | `8000` | Port for health check endpoint |
| `DEDUP_STATE_FILE` | `/data/seen_items.json` | Path to deduplication state file |

### Getting Reddit API Credentials

1. Go to https://www.reddit.com/prefs/apps
2. Click "Create App" or "Create Another App"
3. Select "script" as the app type
4. Fill in name and redirect URI (can be http://localhost)
5. Copy the client ID (under the app name) and secret

### Configuring Reddit Ingestor

Edit `infra/.env` (copy from `infra/.env.example`) and set:

```bash
REDDIT_CLIENT_ID=your_actual_client_id_here
REDDIT_CLIENT_SECRET=your_actual_client_secret_here
REDDIT_USER_AGENT=trading-platform-ingestor/1.0
REDDIT_SUBREDDITS=wallstreetbets,stocks,investing,cryptocurrency
REDDIT_MODE=submissions
REDDIT_POLL_SECONDS=60
REDDIT_LIMIT_PER_POLL=50
```

**Important Notes:**
- `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` are **required**
- `REDDIT_USER_AGENT` is **required** by Reddit's API terms
- Multiple subreddits are comma-separated, no spaces
- Reddit API rate limits apply (approximately 60 requests per minute)

## Deployment

### Via Docker Compose (Recommended)

```bash
cd infra

# Start with apps profile (includes infrastructure + apps)
docker compose --profile apps up -d

# Check logs
docker compose logs -f reddit-ingestor

# Check health
curl http://localhost:8003/health
```

### Build Manually

```bash
cd services/ingestors/reddit

# Build image
docker build -t reddit-ingestor:latest .

# Run container
docker run -d \
  --name reddit-ingestor \
  --network infra_trading-platform \
  -e KAFKA_BOOTSTRAP_SERVERS=redpanda:29092 \
  -e MINIO_ENDPOINT=http://minio:9000 \
  -e REDDIT_CLIENT_ID=your_id \
  -e REDDIT_CLIENT_SECRET=your_secret \
  -e REDDIT_SUBREDDITS=wallstreetbets,stocks \
  -v reddit_data:/data \
  -p 8003:8000 \
  reddit-ingestor:latest
```

## Operation

### Health Check

```bash
curl http://localhost:8003/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "reddit-ingestor",
  "subreddits": ["wallstreetbets", "stocks"],
  "mode": "submissions",
  "seen_items": 127
}
```

### Metrics Endpoint

```bash
curl http://localhost:8003/metrics
```

Available metrics:
- `reddit_ingestor_items_fetched_total{kind="submission|comment"}` - Total items fetched
- `reddit_ingestor_raw_events_published_total` - Total events published
- `reddit_ingestor_raw_events_failed_total{reason="minio|kafka|schema|api"}` - Failed events by reason
- `reddit_ingestor_dedup_hits_total` - Deduplicated items
- `reddit_ingestor_poll_duration_seconds` - Polling duration histogram
- `reddit_ingestor_minio_put_duration_seconds` - MinIO upload duration histogram
- `reddit_ingestor_kafka_produce_duration_seconds` - Kafka produce duration histogram
- `reddit_ingestor_last_success_timestamp` - Last successful poll timestamp

### View Logs

```bash
# Follow logs
docker compose logs -f reddit-ingestor

# Last 100 lines
docker compose logs --tail=100 reddit-ingestor

# Since specific time
docker compose logs --since 2024-01-15T10:00:00 reddit-ingestor
```

### Restart Service

```bash
cd infra
docker compose restart reddit-ingestor
```

### Check Produced Events

View events in Kafka:

```bash
# List recent events with source_type=reddit
docker exec -it redpanda rpk topic consume raw.events.v1 -n 10 | grep -A 20 '"source_type":"reddit"'

# Follow new events
docker exec -it redpanda rpk topic consume raw.events.v1 -f
```

View in Kafka UI: http://localhost:8080
- Navigate to Topics → `raw.events.v1` → Messages
- Filter by `source_type: "reddit"`

### Check MinIO Storage

View objects in MinIO Console: http://localhost:9001
- Login: `minioadmin` / `minioadmin123`
- Navigate to `raw-events` bucket
- Check `source=reddit/dt=YYYY-MM-DD/` partitions

Or via CLI:
```bash
docker run --rm --network infra_trading-platform minio/mc \
  sh -c 'mc alias set local http://minio:9000 minioadmin minioadmin123 && \
         mc ls --recursive local/raw-events/source=reddit/'
```

## Data Flow

### 1. Reddit Polling

Every `REDDIT_POLL_SECONDS` (default 60s):
1. Service polls configured subreddits
2. Fetches submissions and/or comments based on `REDDIT_MODE`
3. Respects `REDDIT_LIMIT_PER_POLL` limit

### 2. Deduplication

For each item:
1. Calculate dedup key: `reddit:{kind}:{reddit_id}`
   - Example: `reddit:submission:abc123` or `reddit:comment:xyz789`
2. Check if already seen (in-memory set + persistent file)
3. Skip if duplicate

### 3. Raw Storage

For new items:
1. Generate UUID `event_id` and `correlation_id`
2. Create JSON document with all Reddit fields:
   - Submissions: id, permalink, url, title, selftext, author, created_utc, subreddit, score, num_comments
   - Comments: id, permalink, body, author, created_utc, subreddit, score
3. Calculate SHA-256 hash of content
4. Upload to MinIO: `s3://raw-events/source=reddit/dt=YYYY-MM-DD/{event_id}.json`

### 4. Event Publication

1. Create RawEvent v1 message with:
   - `event_id`, `source_type=reddit`, `source_name={subreddit}`, timestamps
   - `raw_uri` (S3 path), `raw_hash`
   - `priority` (configurable, default MEDIUM), `correlation_id`
   - `metadata`: subreddit, kind (submission/comment), reddit_id, permalink
2. Validate against `raw_event.v1.json` schema
3. Publish to Kafka topic `raw.events.v1`
4. Wait for broker acknowledgment

## Deduplication Strategy

The ingestor uses a hybrid deduplication approach:

### In-Memory
- Fast lookups during runtime
- Set of seen `reddit:{kind}:{reddit_id}` keys
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
- Metric `reddit_ingestor_raw_events_failed_total{reason="schema"}` incremented
- Service continues (does not crash)

## Reddit API Rate Limits

Reddit API has rate limits:
- **60 requests per minute** for OAuth apps
- Polling 4 subreddits every 60 seconds = 4 requests/minute (safe)
- If you poll more frequently or more subreddits, adjust accordingly

**Best practices:**
- Keep `REDDIT_POLL_SECONDS` >= 60 for most use cases
- Limit number of subreddits if polling very frequently
- Monitor `reddit_ingestor_raw_events_failed_total{reason="api"}` for rate limit errors

## Observability

### Grafana Dashboard

The Reddit ingestor has dedicated panels in the "Pipeline Health" dashboard:

1. **Reddit Ingestor - Throughput**: Rate of events published
2. **Reddit Ingestor - Errors**: Rate of failures by reason
3. **Reddit Ingestor - Dedup Hits**: Rate of duplicate detections
4. **Reddit Ingestor - Last Success Age**: Time since last successful poll

Access: http://localhost:3001 (admin/admin)

### Prometheus Queries

Example queries:

```promql
# Throughput (events/sec)
rate(reddit_ingestor_raw_events_published_total[5m])

# Error rate by reason
rate(reddit_ingestor_raw_events_failed_total[5m])

# Submissions vs comments ratio
rate(reddit_ingestor_items_fetched_total{kind="submission"}[5m]) / 
rate(reddit_ingestor_items_fetched_total[5m])

# Average poll duration
rate(reddit_ingestor_poll_duration_seconds_sum[5m]) / 
rate(reddit_ingestor_poll_duration_seconds_count[5m])

# Time since last success (alert if > 300s)
time() - reddit_ingestor_last_success_timestamp
```

## Troubleshooting

### Service Won't Start

**Check dependencies:**
```bash
cd infra
docker compose ps
```

Ensure `redpanda` and `minio` are healthy.

**Check credentials:**
```bash
docker compose logs reddit-ingestor | grep -i "credentials\|client_id"
```

Verify `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` are set.

**Check logs:**
```bash
docker compose logs reddit-ingestor
```

### No Events Being Produced

**Check if Reddit API is reachable:**
```bash
docker exec -it reddit-ingestor python -c "
import praw
reddit = praw.Reddit(
    client_id='your_id',
    client_secret='your_secret',
    user_agent='test'
)
print(list(reddit.subreddit('wallstreetbets').new(limit=1)))
"
```

**Check Kafka connectivity:**
```bash
docker exec -it reddit-ingestor python -c "
from kafka import KafkaProducer
p = KafkaProducer(bootstrap_servers='redpanda:29092')
print('OK')
"
```

**Check MinIO connectivity:**
```bash
docker exec -it reddit-ingestor python -c "
import boto3
s3 = boto3.client('s3', endpoint_url='http://minio:9000', 
                   aws_access_key_id='minioadmin', 
                   aws_secret_access_key='minioadmin123')
print(s3.list_buckets())
"
```

### Reddit API Rate Limiting

If you see errors with `reason="api"`:

```bash
# Check error logs
docker compose logs reddit-ingestor | grep -i "rate\|429\|error"
```

**Solutions:**
- Increase `REDDIT_POLL_SECONDS` (e.g., to 120 or 180)
- Reduce number of subreddits
- Reduce `REDDIT_LIMIT_PER_POLL`

### All Items Marked as Duplicates

**Reset deduplication state:**
```bash
# Stop service
docker compose stop reddit-ingestor

# Remove state file
docker volume rm infra_reddit_ingestor_data

# Restart
docker compose --profile apps up -d reddit-ingestor
```

### High Memory Usage

If the seen items set grows too large:

**Option 1**: Restart periodically (state is saved, but set recreated from file)

**Option 2**: Manually trim seen_items.json:
```bash
# Keep only last 10000 items
docker exec -it reddit-ingestor python -c "
import json
with open('/data/seen_items.json', 'r') as f:
    items = json.load(f)
with open('/data/seen_items.json', 'w') as f:
    json.dump(items[-10000:], f)
"
```

## Performance

### Throughput
- **Polling**: ~2-5 seconds per subreddit (depends on API latency)
- **Processing**: ~50-100 items/second
- **Bottleneck**: Reddit API rate limits and network I/O

### Resource Usage
- **Memory**: ~100-200 MB (depends on seen items count)
- **CPU**: < 5% idle, ~10-20% during polling
- **Disk**: Only for state file (~1-10 MB)

### Scaling

Currently single-instance. For higher throughput:

1. **Vertical**: Increase polling frequency or add more subreddits
2. **Horizontal**: Run multiple instances with different subreddit subsets
3. **Shared state**: Use Redis for deduplication across instances

## Collection Modes

### Submissions Only (default)
```bash
REDDIT_MODE=submissions
```
Collects only new posts/submissions. Best for:
- News aggregation
- Market sentiment from post titles
- Lower volume requirements

### Comments Only
```bash
REDDIT_MODE=comments
```
Collects only comments. Best for:
- Detailed sentiment analysis
- Discussion tracking
- Higher volume requirements

### Both
```bash
REDDIT_MODE=both
```
Collects both submissions and comments. Best for:
- Complete subreddit coverage
- Comprehensive analysis
- Highest volume

**Note**: `both` mode doubles API requests, so adjust polling interval accordingly.

## Example Logs

Successful submission processing:
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "service": "reddit-ingestor",
  "message": {
    "message": "Published RawEvent",
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "correlation_id": "660e8400-e29b-41d4-a716-446655440001",
    "reddit_id": "abc123",
    "kind": "submission",
    "topic": "raw.events.v1"
  }
}
```

Duplicate detection:
```json
{
  "timestamp": "2024-01-15T10:31:00Z",
  "level": "DEBUG",
  "service": "reddit-ingestor",
  "message": {
    "message": "Item already seen, skipping",
    "reddit_id": "abc123",
    "kind": "submission"
  }
}
```

## Next Steps

After the Reddit ingestor is running:
1. Check that raw events appear in `raw.events.v1` topic with `source_type="reddit"`
2. Verify raw JSON files are stored in MinIO `raw-events` bucket under `source=reddit/`
3. Verify normalizer processes Reddit events correctly
4. Monitor Grafana dashboard for Reddit metrics
5. Adjust polling settings based on your needs

See `docs/20_normalization.md` for normalizer documentation.
