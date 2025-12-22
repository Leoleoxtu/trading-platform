# Feature Store v1

## Overview

The Feature Store is a critical component that bridges market data and NLP-enriched events to create versioned feature vectors for backtesting and trading agents. It computes and stores features that combine:

- **Market features**: OHLCV-based calculations (returns, volatility, volume metrics)
- **NLP/Event features**: Sentiment and event aggregations from enriched events

## Architecture

### Design Pattern: Batch/Periodic Compute (Approach 1)

The Feature Store uses a simple, reproducible batch compute approach:

1. **Every N seconds** (configurable via `FEATURE_REFRESH_SECONDS`):
   - Fetches latest OHLCV candles from TimescaleDB
   - Aggregates enriched events from an in-memory cache
   - Computes features for each (instrument, timeframe) pair
   - Upserts feature vectors to `feature_vectors` table

2. **Event Cache**: 
   - Consumes `events.enriched.v1` from Kafka continuously
   - Maintains a time-windowed cache of events per ticker
   - Provides fast lookups for feature computation

3. **Idempotency**:
   - Unique constraint on `(instrument_id, timeframe, ts, feature_set_version)`
   - Upsert operation ensures reproducibility
   - Same timestamp + version always produces same result

## Feature Set Versioning

### What is `feature_set_version`?

The `feature_set_version` (e.g., `fs_v1`, `fs_v1.1`) is an **immutable identifier** that guarantees:

- **Deterministic computation**: Same version = same formulas = same results
- **Reproducibility**: Can recompute features for any historical period
- **Evolution**: New versions can coexist with old ones for A/B testing

### When to Create a New Version

Create a new `feature_set_version` when:
- Changing feature formulas or parameters
- Adding/removing features
- Modifying window sizes or lookback periods
- Changing data sources or aggregation logic

**DO NOT** modify an existing version. Always create a new one.

## Features v1 Definition

### Market Features (OHLCV-based)

All computed from the `ohlcv` table with lookback of `FEATURE_LOOKBACK_PERIODS` (default: 200).

| Feature | Formula | Description |
|---------|---------|-------------|
| `ret_1` | `(close_t / close_{t-1}) - 1` | Simple return over 1 period |
| `ret_5` | `(close_t / close_{t-5}) - 1` | Simple return over 5 periods |
| `vol_20` | `std(ret_1[-20:])` | Rolling volatility (std dev of returns over 20 periods) |

### NLP/Event Features (Enriched Events)

Computed from `events.enriched.v1` within a time window ending at the candle timestamp.

Window size: `FEATURE_EVENT_WINDOW_MINUTES` (default: 60 minutes)

| Feature | Formula | Description |
|---------|---------|-------------|
| `event_count_1h` | `COUNT(events in window)` | Number of enriched events mentioning the ticker |
| `sentiment_mean_1h` | `MEAN(sentiment.score)` | Average sentiment score (-1 to +1) |
| `sentiment_conf_mean_1h` | `MEAN(sentiment.confidence)` | Average sentiment confidence (0 to 1) |
| `sentiment_weighted_1h` | `SUM(score * confidence) / SUM(confidence)` | Confidence-weighted sentiment |
| `sentiment_std_1h` | `STDEV(sentiment.score)` | Sentiment standard deviation (optional) |

## Quality Flags

The Feature Store tracks data quality issues via `quality_flags`:

| Flag | Meaning | Impact |
|------|---------|--------|
| `MISSING_OHLCV` | No OHLCV data available | Cannot compute market features |
| `INSUFFICIENT_OHLCV` | Not enough candles for lookback | Some features (ret_5, vol_20) missing |
| `NO_EVENTS` | No enriched events in window | Event features set to 0 or missing |
| `LOW_EVENT_COUNT` | Very few events (< threshold) | Event features less reliable |
| `LOW_SENTIMENT_CONFIDENCE` | Average sentiment confidence < 0.5 | Sentiment features less reliable |
| `TIMESTAMP_MISMATCH` | Data timestamp inconsistency | Possible data quality issue |
| `COMPUTATION_ERROR` | Exception during computation | Feature vector incomplete |

**Best Practice**: Filter or weight feature vectors based on quality flags in downstream models.

## Database Schema

### `feature_vectors` Table

Hypertable partitioned on `ts` with 7-day chunks.

```sql
CREATE TABLE feature_vectors (
    instrument_id TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    feature_set_version TEXT NOT NULL,
    features JSONB NOT NULL,
    quality_flags TEXT[] NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pipeline_version TEXT NOT NULL,
    sentiment_window_start TIMESTAMPTZ NULL,
    sentiment_window_end TIMESTAMPTZ NULL,
    event_count INT NULL,
    ohlcv_count INT NULL,
    UNIQUE (instrument_id, timeframe, ts, feature_set_version)
);
```

**Indexes**:
- `(instrument_id, timeframe, ts DESC)` - Fast queries for latest features
- `(feature_set_version)` - Version filtering
- `(computed_at DESC)` - Freshness monitoring
- GIN on `quality_flags` - Quality filtering

### `feature_vectors_latest` Materialized View

Provides quick access to the latest feature timestamp per instrument/timeframe/version:

```sql
CREATE MATERIALIZED VIEW feature_vectors_latest AS
SELECT DISTINCT ON (instrument_id, timeframe, feature_set_version)
    instrument_id,
    timeframe,
    feature_set_version,
    ts AS last_feature_ts,
    computed_at AS last_computed_at,
    quality_flags,
    event_count,
    pipeline_version
FROM feature_vectors
ORDER BY instrument_id, timeframe, feature_set_version, ts DESC;
```

Refresh periodically or on-demand:
```sql
SELECT refresh_feature_vectors_latest();
```

## Configuration

### Environment Variables

```bash
# Instruments to compute features for (CSV)
FEATURE_TICKERS=AAPL,MSFT,TSLA

# Timeframes to compute (CSV)
FEATURE_TIMEFRAMES=1m,1d

# Feature set version (immutable identifier)
FEATURE_SET_VERSION=fs_v1

# Compute frequency (seconds)
FEATURE_REFRESH_SECONDS=60

# OHLCV lookback for rolling features (periods)
FEATURE_LOOKBACK_PERIODS=200

# Event aggregation window (minutes)
FEATURE_EVENT_WINDOW_MINUTES=60

# Pipeline version for tracking
PIPELINE_VERSION=feature-store.v1.0

# Database connection
POSTGRES_HOST=timescaledb
POSTGRES_PORT=5432
POSTGRES_DB=market
POSTGRES_USER=market
POSTGRES_PASSWORD=***

# Kafka connection
KAFKA_BOOTSTRAP_SERVERS=redpanda:29092
ENRICHED_TOPIC=events.enriched.v1
```

### Typical Configuration Profiles

**Development** (fast iteration):
```bash
FEATURE_REFRESH_SECONDS=30
FEATURE_EVENT_WINDOW_MINUTES=30
```

**Production** (stable):
```bash
FEATURE_REFRESH_SECONDS=300  # 5 minutes
FEATURE_EVENT_WINDOW_MINUTES=60
```

**Backfill** (historical recompute):
- Use separate process with specific date range
- Same `feature_set_version` ensures consistency
- Future Phase integration

## Observability

### Health Endpoint

`GET http://localhost:8006/health`

```json
{
  "status": "healthy",
  "compute_active": false,
  "last_success_age_seconds": 45.2,
  "cached_events": 127,
  "feature_set_version": "fs_v1",
  "pipeline_version": "feature-store.v1.0"
}
```

### Prometheus Metrics

**Counters**:
- `feature_store_compute_runs_total` - Total computation cycles
- `feature_store_feature_vectors_upserted_total` - Total vectors upserted
- `feature_store_compute_failed_total{reason}` - Failed computations by reason
- `feature_store_quality_flag_total{flag}` - Quality flags raised

**Histograms**:
- `feature_store_compute_duration_seconds` - Computation time
- `feature_store_db_upsert_duration_seconds` - Database upsert time

**Gauges**:
- `feature_store_last_success_timestamp` - Last successful compute timestamp
- `feature_store_last_feature_ts_timestamp{timeframe}` - Latest feature timestamp
- `feature_store_cached_events` - Events in cache

### Grafana Dashboard

Access the **Feature Store Health** dashboard:
- URL: `http://localhost:3001`
- Dashboard: "Feature Store Health"

**Panels**:
1. Last Success Age
2. Compute Runs / sec
3. Feature Vectors Upserted / sec
4. Cached Events
5. Compute Duration (p95 & p50)
6. DB Upsert Duration (p95 & p50)
7. Last Feature Timestamp Age by Timeframe
8. Quality Flags Rate
9. Failed Computations by Reason

## Usage Examples

### Query Latest Features

```sql
-- Get latest feature vector for AAPL 1d
SELECT 
    ts,
    features,
    quality_flags,
    event_count
FROM feature_vectors
WHERE instrument_id = 'AAPL'
  AND timeframe = '1d'
  AND feature_set_version = 'fs_v1'
ORDER BY ts DESC
LIMIT 1;
```

### Get Features for Date Range

```sql
-- Get all features for AAPL 1d in December 2024
SELECT 
    ts,
    features->>'ret_1' as ret_1,
    features->>'vol_20' as vol_20,
    features->>'sentiment_mean_1h' as sentiment_mean,
    quality_flags
FROM feature_vectors
WHERE instrument_id = 'AAPL'
  AND timeframe = '1d'
  AND feature_set_version = 'fs_v1'
  AND ts >= '2024-12-01'
  AND ts < '2025-01-01'
ORDER BY ts ASC;
```

### Filter by Quality

```sql
-- Get high-quality features (no critical flags)
SELECT *
FROM feature_vectors
WHERE instrument_id = 'AAPL'
  AND feature_set_version = 'fs_v1'
  AND NOT ('MISSING_OHLCV' = ANY(quality_flags))
  AND NOT ('COMPUTATION_ERROR' = ANY(quality_flags))
ORDER BY ts DESC
LIMIT 100;
```

### Compare Feature Set Versions

```sql
-- Compare fs_v1 vs fs_v2 for same timestamp
SELECT 
    feature_set_version,
    features,
    quality_flags
FROM feature_vectors
WHERE instrument_id = 'AAPL'
  AND timeframe = '1d'
  AND ts = '2024-12-20 00:00:00+00'
  AND feature_set_version IN ('fs_v1', 'fs_v2');
```

## Recalculating Features

### Why Recalculate?

- **Backfilling**: Compute features for historical periods
- **Version Migration**: Recompute with new feature set version
- **Data Corrections**: Recompute after OHLCV or event data fixes

### How to Recalculate (Future Integration)

Phase 2 will include a recalculation tool. For now, manual approach:

1. **Stop the feature store** (to avoid conflicts)
2. **Run batch computation** for specific date range:
   ```python
   # Future: feature-store-replay tool
   # For now: modify compute_cycle() to iterate over date range
   ```
3. **Verify results** in database
4. **Restart feature store** for live computation

**Note**: Idempotent upserts ensure safe recomputation - same inputs always produce same outputs.

## Integration with Backtesting/Agents

### Phase 2+ Integration Points

1. **Direct SQL Access**:
   - Backtesting engine queries `feature_vectors` directly
   - Fast, no additional services needed

2. **Kafka Streaming** (optional):
   - Publish features to `features.v1` topic
   - Real-time consumption by agents
   - Requires additional setup (future)

3. **API Service** (future):
   - RESTful API for feature queries
   - Caching layer for performance
   - Authentication/authorization

### Feature Vector Consumer Pattern

```python
# Pseudocode for consuming features in backtest
def get_features(instrument_id, timeframe, start_date, end_date, version='fs_v1'):
    query = """
        SELECT ts, features, quality_flags
        FROM feature_vectors
        WHERE instrument_id = %s
          AND timeframe = %s
          AND feature_set_version = %s
          AND ts >= %s AND ts <= %s
        ORDER BY ts ASC
    """
    return execute_query(query, (instrument_id, timeframe, version, start_date, end_date))

# Use in strategy
for row in get_features('AAPL', '1d', '2024-01-01', '2024-12-31'):
    ret_1 = row['features']['ret_1']
    sentiment = row['features']['sentiment_mean_1h']
    
    # Filter low-quality data
    if 'MISSING_OHLCV' in row['quality_flags']:
        continue
    
    # Your strategy logic here
    signal = compute_signal(ret_1, sentiment, ...)
```

## Troubleshooting

### No Features Being Computed

**Check**:
1. Is TimescaleDB healthy? `docker ps`
2. Is there OHLCV data? `SELECT COUNT(*) FROM ohlcv WHERE instrument_id = 'AAPL'`
3. Is feature-store running? `curl http://localhost:8006/health`
4. Check logs: `docker logs feature-store`

### Missing Event Features

**Check**:
1. Are enriched events being published? Check Kafka UI
2. Is event cache populated? `curl http://localhost:8006/health | jq .cached_events`
3. Do events have matching tickers? Check `tickers` field in enriched events
4. Is `FEATURE_TICKERS` aligned with actual events?

### Quality Flags Always Present

**Investigate**:
- `INSUFFICIENT_OHLCV`: Increase `FEATURE_LOOKBACK_PERIODS` or fetch more history
- `NO_EVENTS`: Check if enriched events mention the ticker
- `LOW_SENTIMENT_CONFIDENCE`: NLP model may need tuning

### Slow Computation

**Optimize**:
1. Reduce `FEATURE_TICKERS` count
2. Increase `FEATURE_REFRESH_SECONDS`
3. Check database indexes
4. Monitor `feature_store_compute_duration_seconds` metric

## Future Enhancements (Phase 2+)

- [ ] Backfill/replay tool for historical computation
- [ ] Additional features (technical indicators, order book metrics)
- [ ] Multi-version parallel computation
- [ ] Feature importance tracking
- [ ] Automated feature selection
- [ ] Feature drift detection
- [ ] Real-time streaming mode (Approach 2)
- [ ] Feature serving API
- [ ] Integration with Lean/QuantConnect

## See Also

- [Market Data Ingestion](./90_operations.md#market-data)
- [NLP Enrichment](./30_enrichment.md)
- [Architecture Overview](./00_overview.md)
