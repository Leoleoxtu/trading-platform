# Market Data Ingestor

Market data ingestor service that fetches OHLCV (Open, High, Low, Close, Volume) data from Yahoo Finance and stores it in TimescaleDB for ground truth market data.

## Features

- **Multi-ticker support**: Fetch data for multiple stock tickers simultaneously
- **Multiple timeframes**: Support for 1m, 5m, 15m, 1h, 1d, and other intervals
- **Quality monitoring**: Detects missing candles and data gaps
- **Idempotent operations**: Safe to re-run without duplicating data
- **UTC timestamps**: All timestamps normalized to UTC
- **Adjusted vs Non-adjusted**: Configurable data adjustment for splits/dividends
- **Observability**: Prometheus metrics and health endpoints

## Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_HOST` | TimescaleDB hostname | `timescaledb` |
| `POSTGRES_PORT` | TimescaleDB port | `5432` |
| `POSTGRES_DB` | Database name | `market` |
| `POSTGRES_USER` | Database user | `market` |
| `POSTGRES_PASSWORD` | Database password | `market_secret_change_me` |
| `MARKET_TICKERS` | Comma-separated list of tickers | `AAPL,MSFT,TSLA` |
| `MARKET_TIMEFRAMES` | Comma-separated list of timeframes | `1m,5m,1d` |
| `MARKET_LOOKBACK_DAYS` | Days of historical data to fetch | `30` |
| `MARKET_REFRESH_SECONDS` | Seconds between refresh cycles | `300` |
| `MARKET_ADJUSTED` | Use adjusted prices (true/false) | `true` |
| `HEALTH_PORT` | Health check endpoint port | `8000` |

### Adjusted vs Non-Adjusted Data

**MARKET_ADJUSTED=true** (Default, Recommended):
- Prices are adjusted for stock splits and dividends
- Provides continuous price series for accurate historical analysis
- Recommended for most use cases including backtesting and analysis
- Yahoo Finance automatically adjusts historical prices when splits/dividends occur

**MARKET_ADJUSTED=false**:
- Raw prices as they were on the actual trading day
- Useful for matching exact historical newspaper prices
- May have discontinuities when splits occur (e.g., 2:1 split shows 50% price drop)

**Our Choice**: We default to **adjusted=true** because:
1. Most trading analysis requires continuous price series
2. Prevents artificial signals at split/dividend dates
3. Industry standard for quantitative analysis
4. Yahoo Finance handles adjustments automatically and reliably

## Supported Timeframes

- **Minute intervals**: `1m`, `2m`, `5m`, `15m`, `30m`, `60m` (limited to last 60 days by Yahoo Finance)
- **Hourly**: `1h`, `90m`
- **Daily and higher**: `1d`, `5d`, `1wk`, `1mo`, `3mo`

Note: Intraday data (minute intervals) is limited by Yahoo Finance to approximately 60 days of history.

## API Endpoints

### Health Check
```bash
GET /health
```

Returns service health status and recent data statistics:
```json
{
  "status": "healthy",
  "service": "market-ingestor",
  "tickers": ["AAPL", "MSFT", "TSLA"],
  "timeframes": ["1m", "5m", "1d"],
  "adjusted": true,
  "recent_data": {
    "tickers_updated": 3,
    "timeframes_updated": 3,
    "latest_candle": "2025-12-22T18:00:00+00:00"
  }
}
```

### Metrics
```bash
GET /metrics
```

Prometheus-formatted metrics including:

**Counters:**
- `market_ingestor_candles_upserted_total{timeframe}` - Total candles written
- `market_ingestor_fetch_failed_total{reason}` - Failed fetch attempts by reason
- `market_ingestor_missing_candles_detected_total{timeframe}` - Missing candles detected

**Histograms:**
- `market_ingestor_fetch_duration_seconds{timeframe}` - API fetch latency
- `market_ingestor_db_upsert_duration_seconds{timeframe}` - Database write latency

**Gauges:**
- `market_ingestor_last_success_timestamp` - Last successful fetch timestamp
- `market_ingestor_last_candle_timestamp{timeframe}` - Most recent candle timestamp per timeframe

## Data Quality

The ingestor performs several quality checks:

1. **Timestamp normalization**: All timestamps converted to UTC
2. **Monotonicity check**: Ensures timestamps are in order
3. **Gap detection**: Identifies missing candles in the time series
4. **Duplicate handling**: Idempotent upserts prevent duplicates

### Missing Candles

Missing candles are normal and expected in several scenarios:
- Market closed hours (overnight, weekends)
- Market holidays
- Low-volume periods (especially for less liquid tickers)
- API rate limiting or temporary failures

The service logs and counts missing candles but continues operation.

## Database Schema

The service uses a single `ohlcv` table in TimescaleDB:

```sql
CREATE TABLE ohlcv (
    instrument_id TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    open NUMERIC(20, 8) NOT NULL,
    high NUMERIC(20, 8) NOT NULL,
    low NUMERIC(20, 8) NOT NULL,
    close NUMERIC(20, 8) NOT NULL,
    volume NUMERIC(20, 8) NOT NULL,
    source TEXT NOT NULL DEFAULT 'yfinance',
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ohlcv_unique_candle UNIQUE (instrument_id, timeframe, ts)
);
```

The table is converted to a TimescaleDB hypertable with 7-day chunks for optimal query performance.

## Example Queries

### Get latest 100 candles for a ticker
```sql
SELECT * FROM ohlcv
WHERE instrument_id = 'AAPL' AND timeframe = '1d'
ORDER BY ts DESC
LIMIT 100;
```

### Check data freshness
```sql
SELECT instrument_id, timeframe, MAX(ts) as latest_candle
FROM ohlcv
GROUP BY instrument_id, timeframe
ORDER BY latest_candle DESC;
```

### Find gaps in data
```sql
SELECT 
    instrument_id,
    timeframe,
    ts,
    LEAD(ts) OVER (PARTITION BY instrument_id, timeframe ORDER BY ts) - ts as gap
FROM ohlcv
WHERE timeframe = '1d'
HAVING gap > INTERVAL '3 days'
ORDER BY gap DESC;
```

## Monitoring

Monitor the service using:

1. **Health endpoint**: Quick status check
2. **Prometheus metrics**: Detailed performance metrics
3. **Grafana dashboard**: Visual monitoring (see "Market Health" dashboard)
4. **Database queries**: Direct data quality checks

### Key Metrics to Monitor

- `market_ingestor_last_success_timestamp`: Should update regularly
- `market_ingestor_fetch_failed_total`: Should remain low
- `market_ingestor_missing_candles_detected_total`: Expected for intraday, should be low for daily data
- Candle age: `time() - market_ingestor_last_candle_timestamp` should be reasonable

## Limitations

1. **Yahoo Finance rate limits**: Service includes 0.5s delay between requests
2. **Intraday data retention**: Yahoo Finance only provides ~60 days of minute-level data
3. **Market hours**: No data during market closed hours (normal)
4. **Ticker validity**: Invalid tickers will log errors but won't crash the service

## Troubleshooting

### No data being ingested
- Check database connectivity: `docker exec timescaledb psql -U market -d market -c "SELECT COUNT(*) FROM ohlcv;"`
- Verify tickers are valid: Check Yahoo Finance website
- Check logs: `docker logs market-ingestor`

### Missing candles for intraday data
- Normal during non-market hours
- Check if ticker is actively traded
- Verify timeframe is supported for the ticker

### High fetch failure rate
- Check network connectivity
- Verify Yahoo Finance is accessible
- Check for rate limiting (increase MARKET_REFRESH_SECONDS)

## Development

Build and run locally:

```bash
cd services/ingestors/market
docker build -t market-ingestor .
docker run --rm \
  -e POSTGRES_HOST=localhost \
  -e MARKET_TICKERS=AAPL \
  -e MARKET_TIMEFRAMES=1d \
  -p 8004:8000 \
  market-ingestor
```

## License

Same as parent project.
