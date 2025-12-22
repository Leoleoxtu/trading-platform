# Replay & Backfill Capability

## Overview

The Replay & Backfill capability allows you to republish historical raw events from MinIO storage back into the Kafka pipeline. This is essential for:

- **Reproducibility Testing**: Verify that pipeline changes produce consistent outputs
- **Backfilling**: Reprocess historical data after fixing bugs or updating logic
- **Data Recovery**: Replay events after pipeline issues
- **Development**: Test with production-like data in development environments

## Architecture

### Data Flow

```
MinIO (raw-events bucket)
  └─> Replayer Tool
       └─> Kafka (raw.events.v1 topic)
            └─> Normalizer → events.normalized.v1
                 └─> NLP Enricher → events.enriched.v1
```

The replayer reads raw JSON files stored in MinIO and reconstructs valid RawEvent v1 messages with special replay metadata flags. These messages flow through the normal pipeline, allowing you to regenerate normalized and enriched outputs.

### Replay Metadata

All replayed events include a `metadata` object with replay-specific flags:

```json
{
  "schema_version": "raw_event.v1",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "source_type": "rss",
  "source_name": "TechCrunch",
  "captured_at_utc": "2025-12-22T10:30:00Z",
  "raw_uri": "s3://raw-events/source=rss/dt=2025-12-21/550e8400-e29b-41d4-a716-446655440000.json",
  "raw_hash": "a3b2c1...",
  "content_type": "application/json",
  "priority": "MEDIUM",
  "correlation_id": "660f9511-f39c-51e5-b827-557766551111",
  "metadata": {
    "is_replay": true,
    "replay_id": "770g0622-g40d-62f6-c938-668877662222",
    "replay_reason": "backfill",
    "replay_source_prefix": "raw-events/source=rss/",
    "replay_published_at_utc": "2025-12-22T10:30:00Z"
  }
}
```

**Replay Metadata Fields:**

- `is_replay` (boolean): Always `true` for replayed events
- `replay_id` (UUID): Unique identifier for the replay run (all events in one replay share this ID)
- `replay_reason` (string): Why the replay was initiated (e.g., "backfill", "recompute", "testing")
- `replay_source_prefix` (string): MinIO prefix where the events were sourced from
- `replay_published_at_utc` (timestamp): When the replay was performed

These flags allow downstream consumers to:
- Distinguish between live and replayed events
- Track replay campaigns
- Implement different processing logic if needed
- Monitor replay progress

## How to Use

### Prerequisites

1. Infrastructure must be running:
   ```bash
   cd infra
   docker compose --profile infra up -d
   ```

2. Raw events must exist in MinIO in the expected path structure:
   ```
   raw-events/
     source=<source_type>/
       dt=YYYY-MM-DD/
         <event_id>.json
   ```

### Basic Usage

#### 1. Dry Run (Recommended First Step)

Always start with a dry run to see what would be replayed:

```bash
docker compose --profile tools run --rm replayer \
  --source rss \
  --date 2025-12-21 \
  --dry-run true
```

This will:
- List all matching files in MinIO
- Show statistics
- **NOT publish** any messages to Kafka

#### 2. Replay a Single Day

```bash
docker compose --profile tools run --rm replayer \
  --source rss \
  --date 2025-12-21 \
  --rate 50 \
  --dry-run false
```

This replays all RSS events from December 21, 2025 at 50 messages/second.

#### 3. Replay a Date Range

```bash
docker compose --profile tools run --rm replayer \
  --source reddit \
  --date-from 2025-12-20 \
  --date-to 2025-12-21 \
  --rate 100 \
  --dry-run false
```

This replays Reddit events from December 20-21, 2025.

#### 4. Replay with Limit

```bash
docker compose --profile tools run --rm replayer \
  --source rss \
  --date 2025-12-21 \
  --limit 1000 \
  --rate 50 \
  --dry-run false
```

This replays only the first 1000 events.

### Common Scenarios

#### Replay Yesterday's Data

```bash
# Linux/Mac
docker compose --profile tools run --rm replayer \
  --source rss \
  --date $(date -d "yesterday" +%Y-%m-%d) \
  --dry-run false

# Or manually specify the date
docker compose --profile tools run --rm replayer \
  --source rss \
  --date 2025-12-21 \
  --dry-run false
```

#### Backfill Last Week

```bash
docker compose --profile tools run --rm replayer \
  --source reddit \
  --date-from 2025-12-15 \
  --date-to 2025-12-21 \
  --rate 200 \
  --replay-reason "weekly_backfill" \
  --dry-run false
```

#### Recompute with Updated Pipeline

After fixing a bug or updating enrichment logic:

```bash
# 1. Stop the consumers temporarily
docker compose stop normalizer nlp-enricher

# 2. Replay the data
docker compose --profile tools run --rm replayer \
  --source rss \
  --date-from 2025-12-01 \
  --date-to 2025-12-21 \
  --rate 100 \
  --replay-reason "recompute_after_fix" \
  --dry-run false

# 3. Restart consumers to process replayed events
docker compose start normalizer nlp-enricher
```

#### Test with Small Sample

```bash
docker compose --profile tools run --rm replayer \
  --source rss \
  --date 2025-12-21 \
  --limit 10 \
  --rate 10 \
  --dry-run false
```

## Command Reference

### Required Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| `--source` | Source type to replay | `--source rss` |
| `--date` | Single date (YYYY-MM-DD) | `--date 2025-12-21` |
| `--date-from` + `--date-to` | Date range | `--date-from 2025-12-20 --date-to 2025-12-21` |

**Note:** You must provide either `--date` OR both `--date-from` and `--date-to`.

### Optional Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--limit` | (none) | Maximum files to process |
| `--rate` | 50 | Messages per second |
| `--dry-run` | true | Dry run mode (true/false) |
| `--log-level` | INFO | Log level (DEBUG/INFO/WARNING/ERROR) |
| `--replay-reason` | backfill | Reason for replay |
| `--replay-id` | (auto) | Custom replay ID (UUID) |
| `--compare` | false | Enable comparison mode |

### Supported Source Types

- `rss` - RSS feed ingestion
- `reddit` - Reddit API ingestion
- `market` - Market data ingestion
- `finnhub` - Finnhub API ingestion
- `scrape` - Web scraping
- `twitter` - Twitter/X API (if configured)
- `newsapi` - NewsAPI ingestion (if configured)
- `manual` - Manually added events

## Output Comparison (Reproducibility Testing)

### Purpose

After replaying events, you can verify that the pipeline produces consistent outputs. This is useful for:
- Testing pipeline changes don't break reproducibility
- Validating bug fixes produce correct outputs
- Comparing different pipeline versions

### How It Works

The comparison feature (when enabled with `--compare`) compares outputs from replayed events against expected results:

1. **Normalized Events**: Compares `dedup_key`, `lang`, and `normalized_text` hash
2. **Enriched Events**: Compares `normalized_text_hash`, `event_category`, `sentiment.score`, and `tickers`

### Usage

```bash
docker compose --profile tools run --rm replayer \
  --source rss \
  --date 2025-12-21 \
  --limit 100 \
  --compare \
  --dry-run false
```

### Comparison Report

Reports are stored in:
```
s3://pipeline-artifacts/replay-reports/<replay_id>.json
```

Example report:
```json
{
  "replay_id": "770g0622-g40d-62f6-c938-668877662222",
  "source": "rss",
  "date": "2025-12-21",
  "timestamp": "2025-12-22T10:35:00Z",
  "events_compared": 100,
  "identical": 98,
  "divergent": 2,
  "divergences": [
    {
      "event_id": "550e8400-e29b-41d4-a716-446655440000",
      "field": "sentiment.score",
      "expected": 0.85,
      "actual": 0.87
    }
  ]
}
```

### Tolerance

Some fields may have acceptable variation:
- **Sentiment scores**: ±0.05 is considered acceptable
- **Entity confidence**: Small variations are normal for non-deterministic models
- **Timestamps**: Will always differ as they reflect processing time

**Note**: Full comparison implementation is available in future versions. Currently, the `--compare` flag is accepted but reports "not yet implemented".

## Monitoring

### Progress Logs

The replayer outputs structured JSON logs:

```json
{"timestamp":"2025-12-22T10:30:00Z","level":"INFO","service":"replayer","message":{"event":"replay_started","replay_id":"770g0622-..."}}
{"timestamp":"2025-12-22T10:30:05Z","level":"INFO","service":"replayer","message":{"event":"objects_found","count":1523}}
{"timestamp":"2025-12-22T10:31:00Z","level":"INFO","service":"replayer","message":{"event":"progress","messages_published":100}}
```

### Summary Statistics

At the end of each run, a summary is displayed:

```
============================================================
REPLAY SUMMARY
============================================================
Replay ID:            770g0622-g40d-62f6-c938-668877662222
Source:               rss
Dry Run:              false
Files Found:          1523
Files Processed:      1523
Messages Published:   1523
Errors:               0
Duration:             30.45 seconds
Rate:                 50.03 messages/sec
============================================================
```

### Kafka Monitoring

View replayed messages in Kafka UI:
1. Open http://localhost:8080
2. Navigate to Topics → raw.events.v1
3. View messages
4. Filter by `metadata.is_replay = true`

## Troubleshooting

### No Objects Found

**Problem**: Replayer reports "0 files found"

**Solutions**:
1. Check the source name matches MinIO path structure:
   ```bash
   # List available sources
   docker run --rm --network infra_trading-platform \
     --entrypoint /bin/sh minio/mc -c \
     'mc alias set local http://minio:9000 minioadmin minioadmin123 && \
      mc ls local/raw-events/'
   ```

2. Verify date format is correct (YYYY-MM-DD)

3. Check if data exists for that date:
   ```bash
   docker run --rm --network infra_trading-platform \
     --entrypoint /bin/sh minio/mc -c \
     'mc alias set local http://minio:9000 minioadmin minioadmin123 && \
      mc ls local/raw-events/source=rss/dt=2025-12-21/'
   ```

### Connection Errors

**Problem**: "Connection refused" or "Network error"

**Solutions**:
1. Ensure infrastructure is running:
   ```bash
   docker compose --profile infra ps
   ```

2. Check Redpanda health:
   ```bash
   docker exec redpanda rpk cluster health --brokers redpanda:29092
   ```

3. Check MinIO health:
   ```bash
   docker exec minio mc admin info local
   ```

4. Verify network exists:
   ```bash
   docker network ls | grep trading-platform
   ```

### Schema Validation Errors

**Problem**: "Schema validation failed"

**Solutions**:
1. Ensure schemas are mounted:
   ```bash
   docker compose config | grep -A 5 "replayer:"
   ```

2. Check schema file exists:
   ```bash
   ls -la schemas/raw_event.v1.json
   ```

3. Validate schema syntax:
   ```bash
   python3 scripts/validate_schema_samples.py
   ```

### Rate Limit Too High

**Problem**: Consumers can't keep up, lag increases

**Solutions**:
1. Reduce replay rate:
   ```bash
   --rate 25  # or lower
   ```

2. Monitor consumer lag in Kafka UI (http://localhost:8080)

3. Increase consumer replicas (if supported in your setup)

4. Pause replay until lag decreases

### Duplicate Events

**Problem**: Events appear to be processed twice

**Explanation**: This is expected behavior! The normalizer has deduplication logic based on `dedup_key`. Replayed events with the same content will be deduplicated and won't create duplicate normalized events.

**Verification**:
Check normalizer logs for dedup hits:
```bash
docker logs normalizer | grep dedup_hits
```

### Docker Compose Profile Not Found

**Problem**: "Service 'replayer' not found"

**Solutions**:
1. Ensure you're using the `--profile tools` flag:
   ```bash
   docker compose --profile tools run --rm replayer ...
   ```

2. Verify replayer service is in docker-compose.yml:
   ```bash
   grep -A 10 "replayer:" infra/docker-compose.yml
   ```

3. Rebuild the service:
   ```bash
   docker compose --profile tools build replayer
   ```

## Best Practices

### 1. Always Start with Dry Run

Before replaying large amounts of data, always do a dry run:
```bash
--dry-run true
```

### 2. Use Appropriate Rate Limits

- Small replays (< 1000 events): `--rate 100`
- Medium replays (1000-10000): `--rate 50`
- Large replays (> 10000): `--rate 25-50`

### 3. Monitor Consumer Lag

Watch consumer lag in Kafka UI to ensure consumers can keep up.

### 4. Use Meaningful Replay Reasons

Document why you're replaying:
```bash
--replay-reason "bug_fix_2025_12_21"
--replay-reason "weekly_backfill"
--replay-reason "testing_new_enricher"
```

### 5. Limit Initial Tests

Test with small samples first:
```bash
--limit 10  # Start small
--limit 100  # Then medium
# Then full replay
```

### 6. Track Replay IDs

Keep a log of replay runs:
```bash
# Save replay ID for tracking
REPLAY_ID=$(uuidgen)
docker compose --profile tools run --rm replayer \
  --replay-id $REPLAY_ID \
  ... | tee replay_${REPLAY_ID}.log
```

## Integration with CI/CD

### Automated Testing

Include replay tests in your CI pipeline:

```yaml
# .github/workflows/test.yml
- name: Test Replay Functionality
  run: |
    cd infra && docker compose --profile infra up -d
    sleep 30  # Wait for infrastructure
    python3 scripts/test_replay_backfill.py
```

### Scheduled Backfills

Use cron or scheduled jobs for regular backfills:

```bash
# Daily backfill of yesterday's data
0 2 * * * cd /path/to/repo && docker compose --profile tools run --rm replayer \
  --source rss \
  --date $(date -d "yesterday" +\%Y-\%m-\%d) \
  --dry-run false \
  --replay-reason "daily_backfill"
```

## Security Considerations

1. **Credentials**: MinIO credentials are in environment variables. Don't commit `.env` files.
2. **Rate Limiting**: Prevents overwhelming the pipeline
3. **Dry Run Default**: Prevents accidental replays
4. **Network Isolation**: Replayer runs in the same Docker network, no external access needed

## Future Enhancements

Potential improvements in future versions:
- Advanced comparison with detailed diff reports
- Parallel processing for faster replays
- Resume capability for interrupted replays
- Metrics export to Prometheus
- Web UI for replay management
- Automated replay scheduling
- Smart rate limiting based on consumer lag

## Related Documentation

- [Overview](./00_overview.md) - Platform architecture
- [Ingestion](./10_ingestion.md) - How raw events are created
- [Normalization](./20_normalization.md) - How events are normalized
- [Enrichment](./30_enrichment.md) - How events are enriched
- [Operations](./90_operations.md) - Operational procedures
