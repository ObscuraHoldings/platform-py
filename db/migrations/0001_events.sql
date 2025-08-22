-- TimescaleDB events hypertable for topic-based event envelopes
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS events (
    time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    causation_id TEXT NULL,
    version INT NOT NULL DEFAULT 1,
    payload JSONB NOT NULL,
    -- Composite primary key includes the partitioning column `time` to satisfy
    -- TimescaleDB requirement that the partitioning column be part of any
    -- unique constraint/primary key on the hypertable.
    PRIMARY KEY (event_id, time)
);

-- Create hypertable
SELECT create_hypertable('events', 'time', if_not_exists => TRUE);

-- Useful indexes
CREATE INDEX IF NOT EXISTS idx_events_topic_time ON events (topic, time DESC);
CREATE INDEX IF NOT EXISTS idx_events_corr_time ON events (correlation_id, time DESC);
