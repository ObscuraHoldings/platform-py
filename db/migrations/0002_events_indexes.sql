-- Add sequence column and performance indexes for events hypertable

-- Add sequence column to track per-correlation ordering (nullable for backfill)
ALTER TABLE IF EXISTS events
    ADD COLUMN IF NOT EXISTS sequence INT NULL;

-- B-tree indexes for common access patterns
CREATE INDEX IF NOT EXISTS idx_events_time_desc ON events (time DESC);
CREATE INDEX IF NOT EXISTS idx_events_version ON events (version);
CREATE INDEX IF NOT EXISTS idx_events_corr_seq_time ON events (correlation_id, sequence ASC, time DESC);

-- GIN index on JSONB payload for contains queries
-- Note: default operator class is preferred over jsonb_path_ops for general usage
CREATE INDEX IF NOT EXISTS idx_events_payload_gin ON events USING GIN (payload);
