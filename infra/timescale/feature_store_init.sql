-- Feature Store initialization script for TimescaleDB
-- Creates tables, hypertables, and indexes for feature vectors storage

-- Feature vectors table for versioned feature storage
-- Stores computed features combining market (OHLCV) and NLP/event data
CREATE TABLE IF NOT EXISTS feature_vectors (
    instrument_id TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    feature_set_version TEXT NOT NULL,
    features JSONB NOT NULL,
    quality_flags TEXT[] NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pipeline_version TEXT NOT NULL,
    -- Optional metadata for debugging and lineage
    sentiment_window_start TIMESTAMPTZ NULL,
    sentiment_window_end TIMESTAMPTZ NULL,
    event_count INT NULL,
    ohlcv_count INT NULL,
    -- Ensure unique features per instrument/timeframe/timestamp/version
    CONSTRAINT feature_vectors_unique UNIQUE (instrument_id, timeframe, ts, feature_set_version)
);

-- Convert to hypertable with time-based partitioning
-- Use 7-day chunks for optimal query performance
SELECT create_hypertable('feature_vectors', 'ts', 
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Create composite index for efficient queries by instrument and timeframe
-- Descending order on ts for latest features queries
CREATE INDEX IF NOT EXISTS idx_feature_vectors_instrument_timeframe_ts 
    ON feature_vectors (instrument_id, timeframe, ts DESC);

-- Create index on feature_set_version for filtering by version
CREATE INDEX IF NOT EXISTS idx_feature_vectors_version 
    ON feature_vectors (feature_set_version);

-- Create index on computed_at for monitoring freshness
CREATE INDEX IF NOT EXISTS idx_feature_vectors_computed_at 
    ON feature_vectors (computed_at DESC);

-- Optional: Create GIN index on features JSONB for flexible queries
-- Note: This can be enabled later if needed for specific feature value queries
-- CREATE INDEX IF NOT EXISTS idx_feature_vectors_features_gin 
--     ON feature_vectors USING GIN (features);

-- Optional: Create index on quality_flags for monitoring data quality
CREATE INDEX IF NOT EXISTS idx_feature_vectors_quality_flags 
    ON feature_vectors USING GIN (quality_flags);

-- Create materialized view for latest feature vector per instrument/timeframe/version
-- Useful for monitoring and quick access to most recent features
CREATE MATERIALIZED VIEW IF NOT EXISTS feature_vectors_latest AS
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

-- Create unique index on materialized view
CREATE UNIQUE INDEX IF NOT EXISTS idx_feature_vectors_latest_unique
    ON feature_vectors_latest (instrument_id, timeframe, feature_set_version);

-- Create function to refresh materialized view
-- Called periodically by the feature store or scheduled job
CREATE OR REPLACE FUNCTION refresh_feature_vectors_latest()
RETURNS VOID AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY feature_vectors_latest;
END;
$$ LANGUAGE plpgsql;

-- Table for tracking feature computation quality issues
CREATE TABLE IF NOT EXISTS feature_quality_log (
    id SERIAL PRIMARY KEY,
    instrument_id TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    feature_set_version TEXT NOT NULL,
    issue_type TEXT NOT NULL, -- 'MISSING_OHLCV', 'NO_EVENTS', 'LOW_CONFIDENCE', etc.
    issue_details JSONB,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ts_start TIMESTAMPTZ,
    ts_end TIMESTAMPTZ
);

-- Index for quality log queries
CREATE INDEX IF NOT EXISTS idx_feature_quality_log_detected_at
    ON feature_quality_log (detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_feature_quality_log_instrument_timeframe
    ON feature_quality_log (instrument_id, timeframe);

CREATE INDEX IF NOT EXISTS idx_feature_quality_log_issue_type
    ON feature_quality_log (issue_type);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON feature_vectors TO market;
GRANT SELECT, INSERT, UPDATE, DELETE ON feature_quality_log TO market;
GRANT SELECT ON feature_vectors_latest TO market;
GRANT USAGE, SELECT ON SEQUENCE feature_quality_log_id_seq TO market;

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'Feature Store initialization complete!';
    RAISE NOTICE 'Created tables: feature_vectors, feature_quality_log';
    RAISE NOTICE 'Created materialized view: feature_vectors_latest';
END $$;
