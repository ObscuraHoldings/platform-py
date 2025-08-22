"""
Execution Orchestrator: subscribes to plan.created, drives execution via venue adapters,
and publishes execution lifecycle events (exec.*).
"""

import asyncio
import structlog
from typing import Any, Dict, Optional

from ...streaming import EventStream
from ...types.envelope import envelope
from ...types.common import Venue
from .venue_manager import VenueManager

logger = structlog.get_logger()


class ExecutionOrchestrator:
    def __init__(self, venue_manager: VenueManager, event_stream: EventStream):
        self.venue_manager = venue_manager
        self.event_stream = event_stream

    async def start(self) -> None:
        await self.venue_manager.initialize()

        async def on_plan_created(evt: Dict[str, Any]):
            payload = evt.get("payload", {})
            plan_id = payload.get("planId")
            intent_id = payload.get("intentId")
            steps = payload.get("steps", [])
            corr = evt.get("correlationId", f"intent:{intent_id}")
            cause = evt.get("eventId")
            if not intent_id or not plan_id:
                return

            started = envelope(
                topic="exec.started",
                payload={"intentId": intent_id, "planId": plan_id},
                correlation_id=corr,
                causation_id=cause,
            )
            await self.event_stream.publish_envelope(started)

            last_txh: Optional[str] = None
            amount_out: Optional[str] = None
            try:
                for step in steps:
                    venue_name = step.get("venue")
                    adapter = await self._get_adapter(venue_name)
                    # Build a simple order representation
                    order = {
                        "base": step.get("base"),
                        "quote": step.get("quote"),
                        "amount_in": step.get("amount_in"),
                        "min_out": step.get("min_out"),
                    }
                    # Submit order (mock returns order_id)
                    sub_res = await adapter.submit_order(order)
                    txh = sub_res.get("order_id")
                    last_txh = txh
                    step_sub = envelope(
                        topic="exec.step_submitted",
                        payload={"intentId": intent_id, "planId": plan_id, "txHash": txh},
                        correlation_id=corr,
                        causation_id=started.eventId,
                    )
                    await self.event_stream.publish_envelope(step_sub)

                    # Wait for filled (poll mock)
                    await asyncio.sleep(0.05)
                    status = await adapter.get_order_status(txh)
                    amount_out = status.get("amount_out") or step.get("min_out")
                    step_fill = envelope(
                        topic="exec.step_filled",
                        payload={
                            "intentId": intent_id,
                            "planId": plan_id,
                            "txHash": txh,
                            "amountOut": amount_out,
                        },
                        correlation_id=corr,
                        causation_id=step_sub.eventId,
                    )
                    await self.event_stream.publish_envelope(step_fill)

                completed = envelope(
                    topic="exec.completed",
                    payload={"intentId": intent_id, "planId": plan_id, "txHash": last_txh, "amountOut": amount_out},
                    correlation_id=corr,
                    causation_id=cause,
                )
                await self.event_stream.publish_envelope(completed)
            except Exception as e:
                logger.error("Orchestration failed", error=str(e), planId=plan_id, intentId=intent_id)
                failed = envelope(
                    topic="exec.failed",
                    payload={"intentId": intent_id, "planId": plan_id, "reason": str(e)},
                    correlation_id=corr,
                    causation_id=cause,
                )
                await self.event_stream.publish_envelope(failed)

        await self.event_stream.subscribe("plan.created", on_plan_created)
        logger.info("ExecutionOrchestrator subscribed to plan.created")

    async def _get_adapter(self, venue_name: str):
        # Map string to Venue enum
        try:
            venue = Venue(venue_name)
        except Exception:
            raise ValueError(f"Unsupported venue: {venue_name}")
        adapter = self.venue_manager.adapters.get(venue)
        if not adapter:
            raise ValueError(f"No adapter registered for venue {venue.value}")
        return adapter

