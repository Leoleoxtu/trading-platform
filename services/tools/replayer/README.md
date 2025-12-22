# Replayer Tool

Replay/Backfill tool for republishing raw events from MinIO storage back into the Kafka pipeline with replay metadata flags.

## Purpose

The replayer allows you to:
- Replay historical events from MinIO storage back into the pipeline
- Backfill data for specific time periods
- Test pipeline reproducibility
- Recompute normalized and enriched outputs with updated logic

## Usage

### Docker Compose (Recommended)

```bash
# Dry run mode (default) - list files without publishing
docker compose --profile tools run --rm replayer \
  --source rss \
  --date 2025-12-21 \
  --dry-run true

# Actual replay with rate limiting
docker compose --profile tools run --rm replayer \
  --source rss \
  --date 2025-12-21 \
  --rate 50 \
  --dry-run false

# Replay date range
docker compose --profile tools run --rm replayer \
  --source reddit \
  --date-from 2025-12-20 \
  --date-to 2025-12-21 \
  --rate 200 \
  --dry-run false

# Replay with limit
docker compose --profile tools run --rm replayer \
  --source rss \
  --date 2025-12-21 \
  --limit 1000 \
  --rate 50 \
  --dry-run false
```

### Command Line Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--source` | Yes | - | Source type (rss, reddit, finnhub, market, etc.) |
| `--date` | Yes* | - | Single date (YYYY-MM-DD) |
| `--date-from` | Yes* | - | Start date for range (YYYY-MM-DD) |
| `--date-to` | Yes* | - | End date for range (YYYY-MM-DD) |
| `--limit` | No | - | Maximum number of files to process |
| `--rate` | No | 50 | Rate limit (messages/second) |
| `--dry-run` | No | true | Dry run mode (true/false) |
| `--log-level` | No | INFO | Log level (DEBUG, INFO, WARNING, ERROR) |
| `--replay-reason` | No | backfill | Reason for replay |
| `--replay-id` | No | auto | Custom replay ID |
| `--compare` | No | false | Enable comparison mode |

*Either `--date` OR both `--date-from` and `--date-to` must be provided.

## Features

### Replay Metadata

All replayed events include metadata flags:
```json
{
  "metadata": {
    "is_replay": true,
    "replay_id": "<uuid>",
    "replay_reason": "backfill",
    "replay_source_prefix": "raw-events/source=rss/",
    "replay_published_at_utc": "2025-12-22T10:30:00Z"
  }
}
```

### Rate Limiting

Controlled replay rate prevents overwhelming the pipeline:
- Default: 50 messages/second
- Adjustable via `--rate` parameter
- Safe for production use

### Dry Run Mode

Test before replaying:
- Lists files that would be processed
- Shows statistics without publishing
- Default mode for safety

### Summary Statistics

End-of-run summary includes:
- Files found and processed
- Messages published
- Error count
- Duration and throughput

## Environment Variables

The following environment variables are configured automatically in Docker Compose:

- `KAFKA_BOOTSTRAP_SERVERS`: Kafka broker address (default: redpanda:9092)
- `MINIO_ENDPOINT`: MinIO endpoint (default: http://minio:9000)
- `MINIO_ACCESS_KEY`: MinIO access key (default: minioadmin)
- `MINIO_SECRET_KEY`: MinIO secret key (default: minioadmin123)
- `MINIO_BUCKET_RAW`: Raw events bucket (default: raw-events)
- `KAFKA_TOPIC_RAW`: Raw events topic (default: raw.events.v1)

## Examples

### Replay Yesterday's RSS Events
```bash
docker compose --profile tools run --rm replayer \
  --source rss \
  --date $(date -d "yesterday" +%Y-%m-%d) \
  --dry-run false
```

### Backfill Last Week
```bash
docker compose --profile tools run --rm replayer \
  --source reddit \
  --date-from $(date -d "7 days ago" +%Y-%m-%d) \
  --date-to $(date -d "yesterday" +%Y-%m-%d) \
  --rate 100 \
  --dry-run false
```

### Test with Small Sample
```bash
docker compose --profile tools run --rm replayer \
  --source rss \
  --date 2025-12-21 \
  --limit 10 \
  --dry-run false
```

## Troubleshooting

### No objects found
- Check the source name matches MinIO path (e.g., `source=rss`)
- Verify date format is YYYY-MM-DD
- Check MinIO bucket has data for that date/source

### Connection errors
- Ensure infrastructure is running: `docker compose --profile infra up -d`
- Check network connectivity to redpanda and minio containers

### Schema validation errors
- Ensure schemas directory is mounted: `/app/schemas`
- Check raw_event.v1.json schema is available

### Rate limit too high
- Reduce `--rate` parameter
- Monitor consumer lag in Kafka UI

## Integration with Pipeline

Replayed events flow through the normal pipeline:

```
Replayer → raw.events.v1 → Normalizer → events.normalized.v1 → NLP Enricher → events.enriched.v1
```

The `is_replay` flag in metadata allows downstream consumers to:
- Track replayed vs live events
- Implement different processing logic if needed
- Monitor replay campaigns separately
