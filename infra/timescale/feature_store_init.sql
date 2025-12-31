-- Feature Store Schema for TimescaleDB
-- Stores calculated technical indicators and features

-- Create features table
CREATE TABLE IF NOT EXISTS features (
    time TIMESTAMPTZ NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    
    -- VWAP indicators
    vwap_1h NUMERIC,
    vwap_1d NUMERIC,
    
    -- RSI
    rsi_14 NUMERIC,
    
    -- MACD
    macd NUMERIC,
    macd_signal NUMERIC,
    macd_histogram NUMERIC,
    
    -- Bollinger Bands
    bb_upper NUMERIC,
    bb_middle NUMERIC,
    bb_lower NUMERIC,
    
    -- ATR
    atr_14 NUMERIC,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    PRIMARY KEY (time, ticker)
);

-- Convert to hypertable
SELECT create_hypertable('features', 'time', if_not_exists => TRUE);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_features_ticker ON features(ticker, time DESC);
CREATE INDEX IF NOT EXISTS idx_features_time ON features(time DESC);

-- Add retention policy (keep 1 year of features)
SELECT add_retention_policy('features', INTERVAL '1 year', if_not_exists => TRUE);

-- Compression policy (compress data older than 7 days)
ALTER TABLE features SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'ticker'
);

SELECT add_compression_policy('features', INTERVAL '7 days', if_not_exists => TRUE);

COMMENT ON TABLE features IS 'Technical indicators and calculated features';
