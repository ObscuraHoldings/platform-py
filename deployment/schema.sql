-- Defines the schema for the event store in TimescaleDB.

CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY,
    event_type VARCHAR(255) NOT NULL,
    event_version INT NOT NULL,
    aggregate_id UUID NOT NULL,
    aggregate_type VARCHAR(255) NOT NULL,
    aggregate_version INT NOT NULL,
    business_timestamp TIMESTAMPTZ NOT NULL,
    system_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB,
    metadata JSONB,
    signature TEXT,
    signer_public_key TEXT,
    hash TEXT,
    UNIQUE(aggregate_id, aggregate_version)
);

-- Create a hypertable for time-series data
SELECT create_hypertable('events', 'business_timestamp', if_not_exists => TRUE);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_events_aggregate_id ON events (aggregate_id);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_aggregate_type ON events (aggregate_type);

