import pytest
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from pydantic import ValidationError

from platform_py.types import (
    Intent,
    IntentType,
    IntentConstraints,
    ExecutionStyle,
    AssetSpec,
    WETH_ETHEREUM,
)


def make_intent_with_amount(amount: Decimal, expires_at=None) -> Intent:
    return Intent(
        strategy_id=__import__('uuid').uuid4(),
        type=IntentType.ACQUIRE,
        assets=[AssetSpec(asset=WETH_ETHEREUM, amount=amount)],
        constraints=IntentConstraints(
            max_slippage=Decimal("0.01"),
            time_window_ms=60_000,
            execution_style=ExecutionStyle.ADAPTIVE,
        ),
        expires_at=expires_at,
    )


def test_intent_expiration_validation():
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(ValidationError):
        make_intent_with_amount(Decimal("2"), expires_at=past)

    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    intent = make_intent_with_amount(Decimal("2"), expires_at=future)
    assert not intent.is_expired
    assert intent.time_remaining is not None


def test_intent_fill_percentage():
    intent = make_intent_with_amount(Decimal("2"))
    # Initially 0
    assert intent.calculate_fill_percentage() == Decimal("0")

    intent.filled_amount = Decimal("1")
    assert intent.calculate_fill_percentage().quantize(Decimal("0.0001")) == Decimal("0.5000")

    intent.filled_amount = Decimal("5")
    # capped at 1
    assert intent.calculate_fill_percentage() == Decimal("1")
