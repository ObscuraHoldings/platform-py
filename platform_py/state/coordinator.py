
from typing import Dict, Any, Optional

import structlog

from ..types.envelope import EventEnvelope
import asyncpg
import redis.asyncio as redis
import json

logger = structlog.get_logger()


class StateCoordinator:
    """Single-writer state coordinator (append-only + read models).

    For V1 scaffolding, this class provides in-memory stubs and documents the
    responsibilities. Persistence to TimescaleDB and Redis is wired in later phases.
    """

    def __init__(self, db_pool: Optional[asyncpg.Pool] = None, redis_client: Optional[redis.Redis] = None):
        # In-memory seen set for idempotency (placeholder for Redis SETNX)
        self._seen: set[str] = set()
        # In-memory aggregates for quick smoke tests
        self._intents: Dict[str, Dict[str, Any]] = {}
        self._plans: Dict[str, Dict[str, Any]] = {}
        self._seq_by_corr: Dict[str, int] = {}
        self._db_pool = db_pool
        self._redis = redis_client

    async def apply_event(self, env: EventEnvelope) -> None:
        """Apply an EventEnvelope.

        - Idempotency by eventId
        - Append to event store (DB placeholder)
        - Update read models (in-memory placeholder)
        """
        if await self._is_duplicate(env.eventId):
            return

        await self._persist_event(env)

        topic = env.topic
        payload = env.payload
        corr = env.correlationId

        # Sequence: accept provided sequence, else compute monotonic per correlation
        if env.sequence is None:
            seq = self._seq_by_corr.get(corr, 0) + 1
            self._seq_by_corr[corr] = seq
        else:
            seq = env.sequence

        # Minimal state machine for intents (Submitted→Accepted→Planned→Executing→Completed/Failed)
        if topic == "intent.submitted":
            iid = payload.get("id") or payload.get("intentId")
            if iid:
                self._intents[iid] = {"state": "Submitted", "last_event": env.eventId, "sequence": seq}
        elif topic == "intent.accepted":
            iid = payload.get("intentId")
            if iid:
                agg = self._intents.setdefault(iid, {})
                agg.update({"state": "Accepted", "last_event": env.eventId, "sequence": seq})
        elif topic == "plan.created":
            pid = payload.get("planId")
            iid = payload.get("intentId")
            if pid:
                self._plans[pid] = {"status": "Planned", "steps": payload.get("steps", []), "sequence": seq}
            if iid and iid in self._intents:
                self._intents[iid].update({"state": "Planned", "latest_plan_id": pid, "sequence": seq})
        elif topic == "exec.started":
            iid = payload.get("intentId")
            if iid and iid in self._intents:
                self._intents[iid].update({"state": "Executing", "sequence": seq})
        elif topic == "exec.completed":
            iid = payload.get("intentId")
            if iid and iid in self._intents:
                self._intents[iid].update({"state": "Completed", "sequence": seq})
        elif topic == "exec.failed":
            iid = payload.get("intentId")
            if iid and iid in self._intents:
                self._intents[iid].update({"state": "Failed", "sequence": seq})

        logger.debug("Applied event", topic=topic, eventId=env.eventId)

    async def get_intent_state(self, intent_id: str) -> Optional[Dict[str, Any]]:
        return self._intents.get(intent_id)

    async def get_plan_state(self, plan_id: str) -> Optional[Dict[str, Any]]:
        return self._plans.get(plan_id)

    async def _is_duplicate(self, event_id: str) -> bool:
        # Redis-based idempotency if available, else in-memory
        if self._redis:
            key = f"events:seen:{event_id}"
            added = await self._redis.setnx(key, "1")
            if added:
                await self._redis.expire(key, 86400)
            return not added
        if event_id in self._seen:
            return True
        self._seen.add(event_id)
        return False

    async def _persist_event(self, env: EventEnvelope) -> None:
        # Append to TimescaleDB if available
        if self._db_pool:
            query = (
                "INSERT INTO events (event_id, topic, correlation_id, causation_id, version, payload) "
                "VALUES ($1, $2, $3, $4, $5, $6)"
            )
            async with self._db_pool.acquire() as conn:
                await conn.execute(
                    query,
                    env.eventId,
                    env.topic,
                    env.correlationId,
                    env.causationId,
                    env.version,
                    json.dumps(env.payload),
                )
        # Update Redis read models if available
        if self._redis:
            await self._update_redis_models(env)

    async def _update_redis_models(self, env: EventEnvelope) -> None:
        topic = env.topic
        p = env.payload
        now_iso = env.timestamp.isoformat()
        if topic == "intent.submitted":
            iid = p.get("intentId") or p.get("id")
            if iid:
                val = {"state": "Submitted", "last_event": env.eventId, "updated_at": now_iso}
                await self._redis.set(f"intent:{iid}", json.dumps(val))
        elif topic == "intent.accepted":
            iid = p.get("intentId")
            if iid:
                # merge update
                key = f"intent:{iid}"
                cur = await self._get_json(key)
                cur.update({"state": "Accepted", "last_event": env.eventId, "updated_at": now_iso})
                await self._redis.set(key, json.dumps(cur))
        elif topic == "plan.created":
            pid = p.get("planId")
            iid = p.get("intentId")
            if pid:
                await self._redis.set(
                    f"plan:{pid}",
                    json.dumps({
                        "status": "Planned",
                        "steps": p.get("steps", []),
                        "updated_at": now_iso,
                    }),
                )
            if iid:
                key = f"intent:{iid}"
                cur = await self._get_json(key)
                cur.update({"state": "Planned", "latest_plan_id": pid, "updated_at": now_iso})
                await self._redis.set(key, json.dumps(cur))
        elif topic == "exec.started":
            iid = p.get("intentId")
            if iid:
                key = f"intent:{iid}"
                cur = await self._get_json(key)
                cur.update({"state": "Executing", "updated_at": now_iso})
                await self._redis.set(key, json.dumps(cur))
        elif topic == "exec.completed":
            iid = p.get("intentId")
            if iid:
                key = f"intent:{iid}"
                cur = await self._get_json(key)
                cur.update({"state": "Completed", "updated_at": now_iso})
                await self._redis.set(key, json.dumps(cur))
        elif topic == "exec.failed":
            iid = p.get("intentId")
            if iid:
                key = f"intent:{iid}"
                cur = await self._get_json(key)
                cur.update({"state": "Failed", "updated_at": now_iso})
                await self._redis.set(key, json.dumps(cur))

    async def _get_json(self, key: str) -> Dict[str, Any]:
        val = await self._redis.get(key) if self._redis else None
        try:
            return json.loads(val) if val else {}
        except Exception:
            return {}
