# Feature Store Service

Computes and stores versioned feature vectors combining market (OHLCV) and NLP (enriched events) features.

## Overview

This service implements a **batch/periodic compute** approach:
- Fetches OHLCV candles from TimescaleDB
- Consumes enriched events from Kafka (maintains in-memory cache)
- Computes features on a schedule
- Upserts to `feature_vectors` table with idempotency

## Features Computed

### Market Features
- `ret_1`: 1-period return
- `ret_5`: 5-period return
- `vol_20`: 20-period rolling volatility

### Event/NLP Features
- `event_count_1h`: Events in 1-hour window
- `sentiment_mean_1h`: Average sentiment
- `sentiment_conf_mean_1h`: Average sentiment confidence
- `sentiment_weighted_1h`: Confidence-weighted sentiment
- `sentiment_std_1h`: Sentiment standard deviation

## Configuration

See `.env.example` for all environment variables:
- `FEATURE_TICKERS`: Comma-separated list of instruments
- `FEATURE_TIMEFRAMES`: Comma-separated list of timeframes
- `FEATURE_SET_VERSION`: Immutable version identifier (e.g., `fs_v1`)
- `FEATURE_REFRESH_SECONDS`: Computation frequency
- `FEATURE_LOOKBACK_PERIODS`: OHLCV lookback for rolling features
- `FEATURE_EVENT_WINDOW_MINUTES`: Event aggregation window

## Endpoints

- `GET /health`: Health check and status
- `GET /metrics`: Prometheus metrics

## Architecture

```
┌─────────────┐
│  TimescaleDB│
│   (OHLCV)   │
└──────┬──────┘
       │
       ├──────────┐
       │          │
       ▼          ▼
┌──────────┐  ┌──────────┐
│  Kafka   │  │ Feature  │
│ (Events) │──►│  Store   │
└──────────┘  └──────┬───┘
                     │
                     ▼
              ┌──────────────┐
              │ TimescaleDB  │
              │(feature_vecs)│
              └──────────────┘
```

## Quality Flags

The service tracks data quality issues:
- `MISSING_OHLCV`: No OHLCV data
- `INSUFFICIENT_OHLCV`: Not enough candles for lookback
- `NO_EVENTS`: No events in window
- `LOW_SENTIMENT_CONFIDENCE`: Low average confidence

## Development

### Local Testing
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
# ... other vars

# Run
python app.py
```

### Docker Build
```bash
docker build -t feature-store:latest .
```

## Monitoring

Prometheus metrics exposed at `/metrics`:
- `feature_store_compute_runs_total`: Total compute cycles
- `feature_store_feature_vectors_upserted_total`: Vectors upserted
- `feature_store_compute_failed_total{reason}`: Failed computations
- `feature_store_quality_flag_total{flag}`: Quality flags raised
- `feature_store_compute_duration_seconds`: Compute time histogram
- `feature_store_db_upsert_duration_seconds`: DB upsert time histogram
- `feature_store_last_success_timestamp`: Last success timestamp
- `feature_store_last_feature_ts_timestamp{timeframe}`: Latest feature timestamp
- `feature_store_cached_events`: Events in cache

## See Also

- [Feature Store Documentation](../../../docs/50_feature_store.md)
- [Schema Definition](../../../schemas/features.v1.json)
