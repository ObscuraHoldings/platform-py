import asyncio
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

import pytest

from platform_py.types import (
    Asset,
    Chain,
    ExecutionStyle,
    Intent,
    IntentConstraints,
    IntentType,
    AssetSpec,
    WETH_ETHEREUM,
    USDC_ETHEREUM,
)
from platform_py.types.envelope import envelope, EventEnvelope


class FakeEventStream:
    """In-memory EventStream stub for tests.

    - Exact-subject subscription only (no wildcards)
    - publish_envelope delivers to subscribers immediately (same task)
    - Captures published envelopes for assertions
    """

    def __init__(self):
        self.subscribers: Dict[str, List[Callable[[Dict[str, Any]], Any]]] = {}
        self.published: List[EventEnvelope] = []

    async def initialize(self):
        return None

    async def shutdown(self):
        return None

    async def subscribe(self, subject: str, handler: Callable[[Dict[str, Any]], Any], durable_name: Optional[str] = None):
        self.subscribers.setdefault(subject, []).append(handler)

    async def publish_envelope(self, env: EventEnvelope, headers: Optional[Dict[str, str]] = None):
        self.published.append(env)
        # Deliver to exact-subject handlers if any
        for cb in self.subscribers.get(env.topic, []):
            await cb(env.model_dump())


@pytest.fixture
def weth_usdc_assets() -> tuple[Asset, Asset]:
    # Use canonical asset constants with valid checksum addresses
    return WETH_ETHEREUM, USDC_ETHEREUM


@pytest.fixture
def acquire_intent(weth_usdc_assets):
    weth, usdc = weth_usdc_assets
    return Intent(
        strategy_id=uuid4(),
        type=IntentType.ACQUIRE,
        assets=[
            AssetSpec(asset=weth, amount=Decimal("1")),
            AssetSpec(asset=usdc, amount=Decimal("1500")),
        ],
        constraints=IntentConstraints(
            max_slippage=Decimal("0.01"),
            time_window_ms=60_000,
            execution_style=ExecutionStyle.ADAPTIVE,
        ),
    )


@pytest.fixture
def make_envelope():
    def _make(topic: str, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> EventEnvelope:
        return envelope(topic=topic, payload=payload, correlation_id=correlation_id or f"intent:{uuid4()}")

    return _make
