# ADR 002: Redis Read Models

Status: Draft

## Summary

Define Redis key schemas for CQRS read models that back low-latency UI queries. State is rebuilt exclusively by the StateCoordinator from the event stream.

## Keys

- `intent:{intentId}`: JSON object
  - `state`: string; one of `Submitted|Accepted|Planned|Executing|Completed|Failed`
  - `last_event`: ULID of the last applied event
  - `latest_plan_id`: optional string
  - `updated_at`: ISO timestamp

- `plan:{planId}`: JSON object
  - `status`: string; one of `Planned|Executing|Completed|Failed`
  - `steps`: array of step objects `{venue, base, quote, amount_in, min_out}`
  - `progress`: number 0..1 (optional)
  - `updated_at`: ISO timestamp

- `positions:{strategyId}`: JSON object (optional for V1)
  - `summary`: object; free-form aggregated snapshot
  - `updated_at`: ISO timestamp

## Concurrency & Ordering

- Idempotency: `events:seen:{eventId}` → Redis string set via `SETNX`.
- Ordering: Maintain a per-correlation sequence `seq:{correlationId}` using `INCR`. The envelope `sequence` field is accepted if present; otherwise StateCoordinator computes and persists it for projections.

## Expiration

- No TTL for `intent:*` and `plan:*` in V1.
- Background compaction may archive completed items later.

## Rebuild Procedure

1. Read events by `correlation_id` ordered by time from TimescaleDB.
2. Reset Redis keys for that correlation.
3. Re-apply events sequentially to reconstruct aggregates.

