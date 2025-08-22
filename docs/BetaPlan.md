# **Strategy Execution Platform: Zero to V1 Implementation Guide**

**Version:** 1.0  
**Status:** FINAL  
**Purpose:** Actionable development plan from zero to working V1 prototype

---

## **Table of Contents**

### **Part I: V1 Prototype Scope & Architecture**

- **1. Executive Summary**
  - 1.1. What We're Building
  - 1.2. Core Principles
  - 1.3. Success Criteria
- **2. V1 Scope Definition**
  - 2.1. In Scope
  - 2.2. Out of Scope
  - 2.3. Technology Stack
- **3. Architecture Overview**
  - 3.1. Component Map
  - 3.2. Data Flow
  - 3.3. Performance Budgets

### **Part II: Core Components Specification**

- **4. Backend Services**
  - 4.1. Intent Manager
  - 4.2. Execution Planner
  - 4.3. Execution Orchestrator
  - 4.4. Venue Adapter Contract
  - 4.5. Risk Engine
  - 4.6. State Coordinator
  - 4.7. Event Stream
  - 4.8. Rust Router Module
- **5. Data Models & Contracts**
  - 5.1. Identifiers
  - 5.2. Event Envelope
  - 5.3. Domain Models
  - 5.4. State Machines
- **6. API & Messaging**
  - 6.1. REST API
  - 6.2. WebSocket Contract
  - 6.3. NATS Subjects
- **7. Persistence Layer**
  - 7.1. TimescaleDB Schema
  - 7.2. Redis Read Models

### **Part III: Frontend & Integration**

- **8. Frontend Specification**
  - 8.1. Pages & Navigation
  - 8.2. State Management
  - 8.3. Real-Time Event Handling
  - 8.4. TypeScript Types
- **9. Testing Strategy**
  - 9.1. Unit Tests
  - 9.2. Integration Tests
  - 9.3. E2E Tests

### **Part IV: Implementation Plan**

- **10. Development Milestones**
  - 10.1. Milestone A: Core Plumbing (Day 1)
  - 10.2. Milestone B: Planning Service (Days 2-3)
  - 10.3. Milestone C: Orchestration (Days 4-5)
  - 10.4. Milestone D: Live Chain (Days 6-7)
  - 10.5. Milestone E: Frontend (Days 8-10)
- **11. Quick Start Guide**
  - 11.1. Happy Path Pseudocode
  - 11.2. Design Tradeoffs
  - 11.3. Future Enhancements

---

## **Part I: V1 Prototype Scope & Architecture**

### **1. Executive Summary**

#### **1.1. What We're Building**

A minimal viable trading execution platform that demonstrates the complete intent-to-execution lifecycle on a single blockchain with one DEX. This prototype proves the core architecture while keeping complexity manageable.

#### **1.2. Core Principles**

- **Vertical Slice**: Complete end-to-end functionality over breadth
- **Event-Driven**: Full auditability and replay capability from day one
- **Performance-Aware**: Sub-50ms latency for pre-chain operations
- **Schema-First**: JSON with Pydantic validation, reusable in TypeScript

#### **1.3. Success Criteria**

✓ End-to-end intent execution on testnet/fork  
✓ Real-time UI showing complete lifecycle  
✓ Stateless services communicating via NATS  
✓ Full event replay capability

### **2. V1 Scope Definition**

#### **2.1. In Scope**

- **Single Chain**: Ethereum (testnet or mainnet fork)
- **Single Venue**: Uniswap V3 swaps only
- **Intent Types**: ACQUIRE or DISPOSE only
- **Risk Checks**: Notional limits and slippage gates
- **Execution**: Single-step swap plans
- **UI**: Dashboard with intent list, submission form, and detail view

#### **2.2. Out of Scope**

- ❌ Multi-chain operations
- ❌ Cross-chain bridging
- ❌ CEX integration
- ❌ Perpetuals/derivatives
- ❌ Safe wallet integration (use local EOA)
- ❌ ML prioritization
- ❌ Complex routing algorithms

#### **2.3. Technology Stack**

- **Backend**: Python 3.13+, FastAPI, Pydantic
- **Performance Core**: Rust with PyO3 bindings
- **Messaging**: NATS with JetStream
- **Persistence**: TimescaleDB (events), Redis (read models)
- **Frontend**: Next.js 14, TypeScript, WebSockets
- **Blockchain**: ethers.py for Ethereum interaction

### **3. Architecture Overview**

#### **3.1. Component Map**

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Frontend UI   │────▶│   REST API   │────▶│  Intent Manager │
│   (Next.js)     │     │  (FastAPI)   │     │                 │
└────────┬────────┘     └──────────────┘     └────────┬────────┘
         │                                             │
         │ WebSocket                          ┌────────▼────────┐
         │                                    │   Risk Engine   │
         │                                    └────────┬────────┘
         │                                             │
         │                                    ┌────────▼────────┐
         │                               ┌───▶│ Execution       │
         │                               │    │ Planner         │
         │                               │    └────────┬────────┘
         │                               │             │
┌────────▼────────┐     ┌───────────┐   │    ┌────────▼────────┐
│  Event Stream   │────▶│   NATS    │───┤    │ Execution       │
│  (WebSocket)    │     │           │   │    │ Orchestrator    │
└─────────────────┘     └───────────┘   │    └────────┬────────┘
                                         │             │
                        ┌───────────┐    │    ┌────────▼────────┐
                        │   State   │────┘    │ Venue Adapter   │
                        │Coordinator│         │ (Uniswap V3)    │
                        └─────┬─────┘         └─────────────────┘
                              │
                    ┌─────────┴──────────┐
                    │                    │
            ┌───────▼──────┐   ┌────────▼────────┐
            │ TimescaleDB  │   │     Redis       │
            │  (Events)    │   │ (Read Models)   │
            └──────────────┘   └─────────────────┘
```

#### **3.2. Data Flow**

1. **Intent Submission** → REST API → Intent Manager → publish `intent.submitted`
2. **Risk Check** → Risk Engine → publish `risk.approved` or `risk.rejected`
3. **Acceptance** → Intent Manager publishes `intent.accepted` only after `risk.approved`
4. **Planning** → Execution Planner (subscribes `intent.accepted`) → Rust Router → publish `plan.created`
5. **Execution** → Orchestrator → Venue Adapter → Chain → Receipts → publish `exec.*`
6. **State Updates** → State Coordinator (single writer) → TimescaleDB + Redis
7. **UI Updates** → NATS → WebSocket (ephemeral consumers) → Frontend

#### **3.3. Performance Budgets**

| Operation            | Target Latency |
| -------------------- | -------------- |
| Intent Validation    | < 10ms         |
| Planning             | < 25ms         |
| Pre-chain Operations | < 50ms         |
| Event → UI           | < 50ms median  |

---

## **Part II: Core Components Specification**

### **4. Backend Services**

#### **4.1. Intent Manager**

**Responsibilities (publish-only; StateCoordinator persists):**

- Validates and enqueues intents
- Assigns correlation identifiers (ULID)
- Publishes `intent.submitted`
- Invokes RiskEngine; on approval publishes `risk.approved` then `intent.accepted`
- Does not write to TimescaleDB/Redis directly

**Interface:**

```python
class IntentManager:
    async def submit_intent(self, intent: Intent) -> str:
        intent_id = generate_ulid()
        validate_schema(intent)
        publish("intent.submitted", {**intent.dict(), "id": intent_id})
        decision = await risk.evaluate(intent)
        if decision.approved:
            publish("risk.approved", {"intentId": intent_id})
            publish("intent.accepted", {"intentId": intent_id})
        else:
            publish("risk.rejected", {"intentId": intent_id, "reason": decision.reason})
        return intent_id
```

#### **4.2. Execution Planner**

**Responsibilities:**

- Consumes `intent.accepted` events
- Queries Rust router for optimal path
- Generates single-step ExecutionPlan
- Emits `plan.created` or `plan.rejected`

**Interface:**

```python
class ExecutionPlanner:
    async def on_intent_accepted(self, event: Event):
        quote = await rust.best_route_univ3(
            pools,
            event.payload.amount_in,
            event.payload.token_in,
            event.payload.token_out
        )
        min_out = calculate_min_out(quote, event.payload.constraints.max_slippage)
        plan = build_execution_plan(event.payload, quote, min_out)
        publish("plan.created", plan.dict())
```

#### **4.3. Execution Orchestrator**

**Responsibilities:**

- Drives plan execution step-by-step
- Calls VenueAdapter for transactions
- Handles retries within constraints
- Emits execution lifecycle events

**Event Sequence:**

1. `exec.started`
2. `exec.step_submitted`
3. `exec.step_filled`
4. `exec.completed` or `exec.failed`

#### **4.4. Venue Adapter Contract**

```python
class VenueAdapter(Protocol):
    venue: str  # "uniswap_v3"
    chain: str  # "ethereum"

    async def price_quote(
        self, base: Asset, quote: Asset, amount_in: Decimal
    ) -> Quote

    async def build_swap_tx(
        self, base: Asset, quote: Asset,
        amount_in: Decimal, min_out: Decimal, recipient: str
    ) -> BuiltTx

    async def submit_tx(self, tx: BuiltTx) -> TxHash

    async def wait_receipt(
        self, tx_hash: str, timeout_s: int
    ) -> TxReceipt
```

#### **4.5. Risk Engine**

**V1 Implementation (Stateless):**

```python
class RiskEngine:
    MAX_NOTIONAL = Decimal("10000")  # $10k
    MAX_SLIPPAGE = Decimal("0.05")   # 5%

    async def check(self, intent: Intent) -> RiskDecision:
        if intent.notional_value > MAX_NOTIONAL:
            return RiskDecision(approved=False, reason="NOTIONAL_LIMIT")
        if intent.constraints.max_slippage > MAX_SLIPPAGE:
            return RiskDecision(approved=False, reason="SLIPPAGE_LIMIT")
        return RiskDecision(approved=True)
```

#### **4.6. State Coordinator**

**Responsibilities (single writer):**

- Subscribes to all domain events (`intent.*`, `risk.*`, `plan.*`, `exec.*`)
- Persists to TimescaleDB (append-only)
- Updates Redis read models
- Ensures idempotency via event_id and per-correlation sequencing

**Write Path:**

```python
async def on_event(self, event: Event):
    # 1. Check idempotency
    if await seen_event(event.event_id):
        return

    # 2. Persist to TimescaleDB
    await timescale.insert_event(event)

    # 3. Update Redis aggregate
    aggregate = await redis.get(f"intent:{event.correlation_id}")
    new_aggregate = apply_event(aggregate, event)
    await redis.set(f"intent:{event.correlation_id}", new_aggregate)
```

#### **4.7. Event Stream**

**NATS Configuration:**

- Subjects use dot notation: `intent.submitted`, `exec.completed`
- Queue groups for workers: `planner.workers`, `orchestrator.workers`
- JetStream for durability on critical events

#### **4.8. Rust Router Module**

**PyO3 Interface:**

```rust
#[pyfunction]
fn best_route_univ3(
    pools: Vec<PoolSnapshot>,
    amount_in: u128,
    token_in: Address,
    token_out: Address
) -> PyResult<RouteQuote> {
    // For V1: Simple direct pool lookup
    // Future: Dijkstra's algorithm for multi-hop
    let quote = find_best_direct_route(&pools, amount_in, token_in, token_out);
    Ok(RouteQuote {
        venue: "uniswap_v3",
        path: vec![token_in, token_out],
        amount_out: quote.output,
        gas_estimate: 150_000,
    })
}
```

### **5. Data Models & Contracts**

#### **5.1. Identifiers**

- **Format**: ULID (Universally Unique Lexicographically Sortable Identifier)
- **Pattern**: `01J5S3Y4PEJHBJ5A7FYHBXQRFG`
- **Usage**: `intent_id`, `plan_id`, `event_id`

#### **5.2. Event Envelope**

```json
{
  "eventId": "01J5S3Y4PEJHBJ5A7FYHBXQRFG",
  "timestamp": "2025-08-21T19:26:00.000Z",
  "topic": "intent.accepted",
  "correlationId": "intent-01J5S3Y4PEJHBJ5A7FYHBXQRFG",
  "causationId": "intent-01J5S3Y4PEJHBJ5A7FYHBXQRFG",
  "payload": { "...domain specific..." },
  "version": 1
}
```

#### **5.3. Domain Models**

**Intent:**

```python
class Intent(BaseModel):
    strategy_id: str
    intent_type: Literal["acquire", "dispose"]
    assets: List[Asset]
    amount: Decimal
    constraints: IntentConstraints
    success_criteria: List[SuccessCriterion]
```

**ExecutionPlan:**

```python
class ExecutionPlan(BaseModel):
    id: str
    intent_id: str
    steps: List[ExecutionStep]
    estimated_cost: Decimal
    estimated_duration_ms: int
    risk_score: float
```

#### **5.4. State Machines**

**Intent Lifecycle:**

```
Submitted → Accepted → Planned → Executing → Completed
                ↓          ↓         ↓           ↓
           RiskRejected  PlanRejected  Failed  Expired
```

**Idempotency Rules:**

- Duplicate `event_id`: Discard
- Same `causation_id`: Ensure monotonic sequence

### **6. API & Messaging**

#### **6.1. REST API**

**Endpoints:**

```
POST /intents          → Submit intent, returns intent_id
GET  /intents/{id}     → Get intent state from Redis
GET  /plans/{id}       → Get plan details
WS   /stream           → WebSocket subscription
```

**Request Example:**

```json
POST /intents
{
  "strategy_id": "demo",
  "intent_type": "acquire",
  "assets": [
    {"symbol": "WETH", "chain": "ethereum", "address": "0x...", "decimals": 18},
    {"symbol": "USDC", "chain": "ethereum", "address": "0x...", "decimals": 6}
  ],
  "amount": "1.0",
  "constraints": {
    "max_slippage": "0.01",
    "time_window": 300,
    "execution_style": "aggressive"
  }
}
```

#### **6.2. WebSocket Contract**

**Subscribe (ephemeral consumers; resume via last-seen sequence optional):**

```json
{
  "action": "subscribe",
  "topics": ["intent.*", "exec.*"],
  "correlationId": "intent-01J5S3Y4PEJHBJ5A7FYHBXQRFG"
}
```

#### **6.3. NATS Subjects**

| Subject               | Description           |
| --------------------- | --------------------- |
| `intent.submitted`    | Intent received       |
| `intent.accepted`     | Intent validated      |
| `risk.approved`       | Risk check passed     |
| `risk.rejected`       | Risk check failed     |
| `risk.approved`       | Risk check passed     |
| `plan.created`        | Execution plan ready  |
| `exec.started`        | Execution beginning   |
| `exec.step_submitted` | Transaction sent      |
| `exec.step_filled`    | Transaction confirmed |
| `exec.completed`      | Intent fulfilled      |

### **7. Persistence Layer**

#### **7.1. TimescaleDB Schema**

```sql
CREATE TABLE events (
    time TIMESTAMPTZ NOT NULL,
    event_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    causation_id TEXT NOT NULL,
    payload JSONB NOT NULL
);

SELECT create_hypertable('events', 'time');

CREATE INDEX ON events (topic, time DESC);
CREATE INDEX ON events (correlation_id, time DESC);
```

#### **7.2. Redis Read Models**

```
intent:{intentId} → {
    "state": "executing",
    "last_event_time": "2025-08-21T19:26:00Z",
    "summary": {...},
    "latest_plan_id": "plan-01J..."
}

plan:{planId} → {
    "status": "in_progress",
    "steps": [...],
    "progress": {...}
}

positions:{strategyId} → {
    "pnl": "120.50",
    "positions": [...]
}
```

---

## **Part III: Frontend & Integration**

### **8. Frontend Specification**

#### **8.1. Pages & Navigation**

1. **Dashboard** (`/`)
   - List of recent intents with status badges
   - Quick stats: Total executed, Success rate, Active intents
2. **Submit Intent** (`/submit`)
   - Token pair selector
   - Amount input with USD conversion
   - Slippage and time window controls
3. **Intent Detail** (`/intent/{id}`)
   - Real-time event timeline
   - Plan visualization
   - Execution progress with live updates

#### **8.2. State Management**

**Zustand Store:**

```typescript
interface PlatformStore {
  intentsById: Record<string, IntentView>;
  liveEvents: CircularBuffer<PlatformEvent>;
  connectionStatus: "connecting" | "connected" | "disconnected";

  actions: {
    submitIntent: (form: IntentForm) => Promise<string>;
    subscribeToIntent: (intentId: string) => void;
    applyEvent: (event: PlatformEvent) => void;
  };
}
```

#### **8.3. Real-Time Event Handling**

```typescript
// WebSocket connection
const ws = new WebSocket("/stream");

// Subscribe on intent submission
ws.send(
  JSON.stringify({
    action: "subscribe",
    topics: ["intent.*", "exec.*"],
    correlationId: intentId,
  })
);

// Update UI on events
ws.onmessage = (msg) => {
  const event = JSON.parse(msg.data) as PlatformEvent;
  store.applyEvent(event);
  updateTimeline(event);
};
```

#### **8.4. TypeScript Types**

```typescript
type PlatformEvent =
  | { topic: "intent.accepted"; payload: { intentId: string } }
  | { topic: "plan.created"; payload: { planId: string; steps: Step[] } }
  | {
      topic: "exec.completed";
      payload: { intentId: string; amountOut: string; txHash: string };
    }
  | { topic: "exec.failed"; payload: { reason: string } };
```

### **9. Testing Strategy**

#### **9.1. Unit Tests**

- Intent validation with valid/invalid schemas
- Risk engine limit checks
- Min_out calculation from slippage
- Event reduction to aggregates

#### **9.2. Integration Tests**

- Full event flow with stubbed adapter
- Service restart and replay from TimescaleDB
- Redis aggregate consistency checks

#### **9.3. E2E Tests**

- Playwright test: Submit intent → Wait for completion
- WebSocket event timeline verification
- Page refresh preserves state

---

## **Part IV: Implementation Plan**

### **10. Development Milestones**

#### **10.1. Milestone A: Core Plumbing (Day 1)**

- [ ] Define ULID generation and event envelope
- [ ] Implement `POST /intents` endpoint
- [ ] Publish `intent.accepted` to NATS
- [ ] Stub Risk Engine (auto-approve)

#### **10.2. Milestone B: Planning Service (Days 2-3)**

- [ ] Implement Execution Planner
- [ ] Create mock Rust router returning static quotes
- [ ] Generate ExecutionPlan with single swap step
- [ ] Emit `plan.created` event

#### **10.3. Milestone C: Orchestration (Days 4-5)**

- [ ] Implement Execution Orchestrator
- [ ] Create UniswapV3Adapter with ethers.py
- [ ] Return synthetic receipts (no chain calls)
- [ ] Complete event sequence

#### **10.4. Milestone D: Live Chain (Days 6-7)**

- [ ] Connect to testnet/fork RPC
- [ ] Implement real transaction submission
- [ ] Wait for actual receipts
- [ ] Local EOA signer configuration

#### **10.5. Milestone E: Frontend (Days 8-10)**

- [ ] WebSocket gateway service
- [ ] Dashboard with intent list
- [ ] Submit form with validation
- [ ] Real-time detail view with timeline

### **11. Quick Start Guide**

#### **11.1. Happy Path Pseudocode**

```python
# 1. Submit Intent
intent = Intent(**request_body)
intent_id = ulid()
publish("intent.submitted", {...})
validate(intent)
publish("intent.accepted", {...})

# 2. Risk Check
on("intent.accepted", lambda e:
    ok = risk_check(e.payload.intent, limits)
    publish("risk.approved" if ok else "risk.rejected", {...})
)

# 3. Planning
on("risk.approved", lambda e:
    quote = rust.best_route_univ3(pools, amount_in, token_in, token_out)
    plan = build_plan(e.payload.intent, quote)
    publish("plan.created", {...plan...})
)

# 4. Execution
on("plan.created", async lambda e:
    step = e.payload.steps[0]
    tx = await adapter.build_swap_tx(...step...)
    txh = await adapter.submit_tx(tx)
    publish("exec.step_submitted", {"txHash": txh})
    rcpt = await adapter.wait_receipt(txh, timeout_s=120)
    publish("exec.step_filled", {"amountOut": rcpt.amount_out})
    publish("exec.completed", {"intentId": e.payload.intent_id})
)
```

#### **11.2. Design Tradeoffs**

| Decision      | Choice             | Rationale                                  |
| ------------- | ------------------ | ------------------------------------------ |
| Event Store   | TimescaleDB        | Time-series optimized, simple hypertable   |
| Messaging     | NATS               | Lightweight, fits request/response pattern |
| Schema        | JSON + Pydantic    | Fast iteration, TypeScript reuse           |
| Wallet        | Local EOA          | Avoid Safe complexity in V1                |
| Rust Boundary | Route pricing only | Keep simple, expand based on profiling     |

#### **11.3. Future Enhancements**

**After V1:**

- Multi-venue routing with solver competition
- Cross-chain settlement and bridging
- ML-guided intent prioritization
- Safe wallet integration
- Circuit breakers with volatility feeds

---

## **Acceptance Criteria Checklist**

- [ ] End-to-end flow works on testnet/fork
- [ ] UI shows real-time lifecycle events
- [ ] Page refresh reconstructs state from Redis
- [ ] Services communicate only via NATS
- [ ] Event replay rebuilds correct aggregates
- [ ] All operations under performance budget
- [ ] Integration tests pass
- [ ] Documentation complete
