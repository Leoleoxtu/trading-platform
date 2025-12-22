-- TimescaleDB initialization script for Market Data
-- Creates tables, hypertables, and indexes for OHLCV data storage

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create OHLCV table for market data
-- Single table design with instrument_id and timeframe for flexibility
CREATE TABLE IF NOT EXISTS ohlcv (
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
    -- Ensure unique candles per instrument/timeframe/timestamp
    CONSTRAINT ohlcv_unique_candle UNIQUE (instrument_id, timeframe, ts)
);

-- Convert to hypertable with time-based partitioning
-- Use 7-day chunks for better query performance
SELECT create_hypertable('ohlcv', 'ts', 
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Create index for efficient queries by instrument and timeframe
-- Descending order on ts for latest data queries
CREATE INDEX IF NOT EXISTS idx_ohlcv_instrument_timeframe_ts 
    ON ohlcv (instrument_id, timeframe, ts DESC);

-- Create index on ingested_at for monitoring freshness
CREATE INDEX IF NOT EXISTS idx_ohlcv_ingested_at 
    ON ohlcv (ingested_at DESC);

-- Create index on source for filtering by data source
CREATE INDEX IF NOT EXISTS idx_ohlcv_source 
    ON ohlcv (source);

-- Optional: Create materialized view for latest candle per instrument/timeframe
-- Useful for monitoring and alerting on data freshness
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_latest AS
SELECT DISTINCT ON (instrument_id, timeframe)
    instrument_id,
    timeframe,
    ts AS last_candle_ts,
    ingested_at AS last_ingested_at,
    source
FROM ohlcv
ORDER BY instrument_id, timeframe, ts DESC;

-- Create index on materialized view
CREATE UNIQUE INDEX IF NOT EXISTS idx_ohlcv_latest_instrument_timeframe
    ON ohlcv_latest (instrument_id, timeframe);

-- Create function to refresh materialized view
-- Called periodically by the ingestor or scheduled job
CREATE OR REPLACE FUNCTION refresh_ohlcv_latest()
RETURNS VOID AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY ohlcv_latest;
END;
$$ LANGUAGE plpgsql;

-- Table for tracking data quality issues
CREATE TABLE IF NOT EXISTS ohlcv_quality_log (
    id SERIAL PRIMARY KEY,
    instrument_id TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    issue_type TEXT NOT NULL, -- 'missing_candles', 'duplicate', 'invalid_data', etc.
    issue_details JSONB,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ts_start TIMESTAMPTZ,
    ts_end TIMESTAMPTZ
);

-- Index for quality log queries
CREATE INDEX IF NOT EXISTS idx_quality_log_detected_at
    ON ohlcv_quality_log (detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_quality_log_instrument_timeframe
    ON ohlcv_quality_log (instrument_id, timeframe);

-- Grant permissions (adjust user as needed)
GRANT SELECT, INSERT, UPDATE, DELETE ON ohlcv TO market;
GRANT SELECT, INSERT, UPDATE, DELETE ON ohlcv_quality_log TO market;
GRANT SELECT ON ohlcv_latest TO market;
GRANT USAGE, SELECT ON SEQUENCE ohlcv_quality_log_id_seq TO market;

-- Enable compression on older chunks (optional, for production)
-- Compress data older than 30 days
-- 
-- Benefits:
--   - Reduces disk space usage by 90%+ for older data
--   - Minimal impact on query performance for compressed chunks
--   - Automatic compression in background
--
-- Considerations:
--   - Only enable after evaluating storage needs
--   - Compressed chunks are read-only (no updates/deletes)
--   - Monitor compression job performance
--
-- To enable:
-- SELECT add_compression_policy('ohlcv', INTERVAL '30 days');

-- Enable retention policy (optional, for production)
-- Drop chunks older than 2 years
--
-- Benefits:
--   - Automatic cleanup of old data
--   - Prevents unbounded growth
--   - Reduces maintenance overhead
--
-- Considerations:
--   - Ensure backup/archive strategy for dropped data
--   - Adjust interval based on requirements
--   - Consider regulatory/compliance needs
--
-- To enable:
-- SELECT add_retention_policy('ohlcv', INTERVAL '2 years');

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'TimescaleDB OHLCV initialization complete!';
    RAISE NOTICE 'Created tables: ohlcv, ohlcv_quality_log';
    RAISE NOTICE 'Created materialized view: ohlcv_latest';
END $$;

-- Include Feature Store initialization
\i /docker-entrypoint-initdb.d/feature_store_init.sql
