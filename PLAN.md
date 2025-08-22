# Backend Plan to Reach v1 State

## Phase 1 – Project Setup & Foundation

- Event envelope harmonization (schema-first)
  - [ ] Create `Platform/types/envelope.py`
    - `EventEnvelope` (Pydantic): `{ eventId: ULID, timestamp: datetime, topic: str, correlationId: str, causationId: str, payload: dict, version: int }`
    - `ulid()` generator; ensure lexicographically sortable IDs
    - Helper: `envelope(topic: str, payload: dict, *, correlation_id: str, causation_id: str | None) -> EventEnvelope`
  - [ ] Refactor `Platform/types/events.py`
    - Keep existing domain payloads as-is, but **remove signature/ed25519** for v1
    - Add `to_envelope(topic: str, aggregate_id: UUID, *, correlation_id, causation_id) -> EventEnvelope`
    - Provide mapping tables: intent topics (`intent.submitted`, `intent.accepted`, `risk.approved|rejected`, `plan.created|rejected`, `exec.*`)
  - [ ] Update all publishers to emit **topic**-based envelopes (not `event_type`)
- Persistence primitives (single-writer model)
  - [ ] Add TimescaleDB migrations folder `db/migrations/0001_events.sql`
    - Create `events(time timestamptz, event_id text primary key, topic text, correlation_id text, causation_id text, payload jsonb, version int)`
    - Indexes: `(topic, time desc)`, `(correlation_id, time desc)`
    - `SELECT create_hypertable('events','time');`
  - [ ] Add `db/migrations/0002_read_models.sql`
    - Redis-backed read models (doc-only), no SQL; document key schemas
  - [ ] Wire migrations runner (simple): `scripts/migrate.py` using asyncpg to execute in order
  - [ ] Adopt a single-writer persistence policy: only `StateCoordinator` writes to TimescaleDB and Redis; producers publish to NATS only.
- Config & DI cleanup
  - [ ] Expand `Platform/config.py` with v1 envs:
    - `WS_ALLOWED_TOPICS`, `ETH_RPC_URL`, `CHAIN_ID`, `USE_MAINNET_FORK`, `RUST_ENGINE_ENABLED`
  - [ ] Ensure `ServiceConnector.connect_all()` initializes: asyncpg pool, aioredis pool, NATS (JetStream), and exposes handles on `services`
  - [ ] Ensure `dependencies.CoreComponents` creates:
    - `EventStream` (NATS+Redis), `StateCoordinator` (Timescale+Redis), `IntentManager`, `ExecutionPlanner`, `ExecutionOrchestrator`, `RiskEngine`, `VenueManager`
- Strip out-of-scope ML & Ray (feature flags, stubs)
  - [ ] Gate `core/intent/prioritizer.py` & `processor.py` behind `PLATFORM_ENABLE_ML=false` (default off)
  - [ ] Replace calls with no-op heuristic:
    - Priority = `5` bounded by notional; decompose = **identity** list
- Logging & metrics
  - [ ] Configure structlog JSON formatter & request id middleware in `app.py`
  - [ ] Expose `/metrics` (Prometheus) with counters from `monitoring/metrics.py`
- Unify identifiers
  - [ ] Add `Platform/types/ids.py` with `new_correlation_id(intent_id: UUID) -> str` and `parse_correlation_id`
  - [ ] Ensure all events include `correlationId`=`intent-<ULID/UUID>`

## Phase 2 – Core Services

- REST API (align to v1)
  - [ ] Replace `Platform/api/intent.py` with routes:
    - `POST /intents` → returns `{intent_id}`; publish `intent.submitted` then `intent.accepted`
    - `GET /intents/{id}` → resolve from Redis read model
    - `GET /plans/{id}` → resolve from Redis read model
  - [ ] Remove `/submit` and `/status` legacy routes (compat alias optional)
- WebSocket gateway
  - [ ] Add `Platform/api/stream.py`:
    - `GET /stream` WS: accepts `subscribe` message `{topics: string[], correlationId?: string}`
    - Bridges NATS subjects to WS clients using ephemeral consumers; optional resume via last-seen sequence; reserve durables for backend workers
    - Backpressure: bounded queue (size 1024), drop-policy for `market.*`
- EventStream hardening
  - [ ] `streaming/event_stream.py`:
    - Enforce subject registry & wildcard authorization
    - Add `publish_envelope(subject: str, env: EventEnvelope, headers: dict | None)` that sets `Nats-Msg-Id` = `env.eventId` for server dedup
    - Configure stream with `subjects = ["intent.*","plan.*","exec.*","system.*","risk.*"]` and a duplicate window
- Intent Manager (publish-only; StateCoordinator persists)
  - [ ] `core/intent/manager.py`:
    - `submit_intent(intent, metadata)`:
      - Validate via `IntentValidator` (basic, no DB deps)
      - Risk precheck (notional/slippage)
      - Generate `intent_id`, `correlationId`
      - Publish `intent.submitted` envelope to NATS (no direct DB/Redis writes)
      - Invoke RiskEngine; on approval publish `risk.approved`; then publish `intent.accepted`
      - Do not write to TimescaleDB or Redis directly; `StateCoordinator` subscribes and persists/updates read models
    - `get_intent_status(intent_id)` reads from Redis `intent:{id}`
    - `get_intent_history(intent_id)` reads from TimescaleDB by `correlation_id`
    - Background `queue` loop **removed** (planning is event-driven)
- Risk Engine (stateless V1; gates acceptance)
  - [ ] Implement `risk/engine.py::evaluate_risk`:
    - `MAX_NOTIONAL_USD=10000`, `MAX_SLIPPAGE=0.05`
    - Return `{approved: bool, reason?: str}`
  - [ ] Publish `risk.approved|rejected`; only publish `intent.accepted` after approval
- Execution Planner (single-step Uniswap V3; cached pool state)
  - [ ] `core/execution/planner.py`:
    - Subscribe `intent.accepted` (via EventStream)
    - Requires cached pool snapshots (slot0/liquidity/fee) to avoid RPC in hot path
    - Compute min_out = quote_out \* (1 - max_slippage)
    - Use Rust route if `RUST_ENGINE_ENABLED=true` else direct pool stub
    - Emit `plan.created` with `{planId, intentId, steps:[{venue:"uniswap_v3", base, quote, amount_in, min_out}]}` payload
    - No ML cost model; `_simulate_plan` returns static estimates
- Orchestrator & Venue Adapter
  - [ ] Create `core/execution/orchestrator.py`
    - Subscribe `plan.created`
    - Emit `exec.started`; for each step:
      - `tx = await adapter.build_swap_tx(...)`
      - `txh = await adapter.submit_tx(tx)` → emit `exec.step_submitted {txHash}`
      - `rcpt = await adapter.wait_receipt(txh, timeout_s=120)` → emit `exec.step_filled {amountOut, txHash}`
    - On all steps done: `exec.completed {intentId, amountOut, txHash}`
    - On failure: `exec.failed {reason}`
  - [ ] Define adapter contract `core/execution/venue_adapter.py`:
    ```py
    class VenueAdapter(Protocol):
        venue: str
        chain: str
        async def price_quote(self, base: Asset, quote: Asset, amount_in: Decimal) -> Quote: ...
        async def build_swap_tx(self, base: Asset, quote: Asset, amount_in: Decimal, min_out: Decimal, recipient: str) -> BuiltTx: ...
        async def submit_tx(self, tx: BuiltTx) -> str: ...
        async def wait_receipt(self, tx_hash: str, timeout_s: int) -> TxReceipt: ...
    ```
  - [ ] Implement `core/market/uniswap_v3_adapter_runtime.py` (ethers.py)
    - Use `ETH_RPC_URL`, `CHAIN_ID`; read ABI JSONs (local)
    - Implement `price_quote`, `build_swap_tx`, `submit_tx`, `wait_receipt`
    - For V1: support **exactInputSingle** on a known pool; recipient from config
- State Coordinator (single writer: append-only + read models)
  - [ ] `state/coordinator.py::apply_event`
    - Idempotency: Redis `SETNX events:seen:{eventId}`
    - Write to TimescaleDB `events` table
    - Update Redis read models:
      - `intent:{intentId}` state machine (Submitted→Accepted→Planned→Executing→Completed/Failed)
      - `plan:{planId}` with steps & progress
      - `positions:{strategyId}` (optional for v1 – summary only)
  - [ ] Subscribe to `intent.*|risk.*|plan.*|exec.*` and be the only component that persists and updates read models
- Chain watcher (optional assist)
  - [ ] `chain_monitor/watcher.py`:
    - If orchestrator `wait_receipt` already covers confirmations, scope watcher to future V1+; keep disabled behind flag

## Phase 3 – Refinement & Integration

- Idempotency & sequencing
  - [ ] Add `causationId` monotonic guard in `state/coordinator.py` per `correlationId`; include a per-correlation sequence number in envelope headers or payload for strict ordering
  - [ ] Ensure orchestrator retries are **bounded** and publish `exec.failed` when exceeded
- Redis read-model schemas (document + enforce)
  - [ ] Keys:
    - `intent:{id}` `{state, last_event_time, latest_plan_id, summary}`
    - `plan:{id}` `{status, steps, progress}`
    - `positions:{strategyId}` summary PnL (mock)
  - [ ] TTL: none for intents; background compaction later
- NATS subjects & queues
  - [ ] Declare queue groups: `planner.workers`, `orchestrator.workers`
  - [ ] Durable consumers for `intent.*`, `plan.created`, `exec.*`
- Observability
  - [ ] Emit metrics:
    - `intents_submitted`, `intents_completed{status}`, `intent_processing_time`
  - [ ] Structured logs include `{topic, correlationId, eventId}`
- Security & governance (lightweight)
  - [ ] `agent/framework.py` authz **stub**; API uses HMAC auth middleware (optional)
  - [ ] Rate-limit `POST /intents` (e.g., 10/min per API key)
- Configurable mock mode
  - [ ] Add `PLATFORM_MOCK_CHAIN=true` to use `core/market/uniswap_v3.py::MockWeb3Provider` for price_quote and synthetic receipts
  - [ ] Add sample script `scripts/publish_fake_flow.py` to feed UI

## Phase 4 – Finalization

- Testing (unit/integration/E2E)
  - [ ] Unit
    - `types/envelope.py` ULID ordering, parsing
    - `risk/engine.py` limits
    - `state/coordinator.py` idempotency + transitions
    - `execution/planner.py` min_out math and rust fallback
    - `execution/orchestrator.py` happy path (adapter mocked)
    - `streaming/event_stream.py` publish/subscribe roundtrip (NATS test container)
  - [ ] Integration
    - Spin up docker-compose: Postgres+Timescale, Redis, NATS, anvil (or sepolia RPC)
    - Flow: `POST /intents` → `exec.completed` and Redis state reflects success
    - Replay: fetch events by `correlationId` and rebuild read model (offline script)
  - [ ] E2E on fork
    - Use anvil + funded EOA from `.env` to perform 1 WETH↔USDC swap on Uniswap V3
- Performance budgets & hardening
  - [ ] Measure pre-chain latencies (validation+planning) < 50ms median
  - [ ] Tune JetStream `MaxAckPending`, `DeliverPolicy=All`, `AckWait=5s`
  - [ ] Backpressure: orchestrator step channel bounded; drop extraneous `market.*`
- Documentation & ops
  - [ ] `README.md`: architecture, services, how to run with/without chain, API/WS contracts
  - [ ] `docs/adr/001-event-envelope.md`, `002-redis-read-models.md`, `003-orchestrator-retry-policy.md`
  - [ ] Example curl & WS client snippets
- Acceptance criteria
  - [ ] End-to-end flow works on testnet/fork (single chain, single venue)
  - [ ] REST + WS contracts match v1 spec
  - [ ] Services communicate only via NATS topics
  - [ ] Event replay reconstructs Redis read models deterministically
  - [ ] Pre-chain ops < 50ms median; integration tests green
