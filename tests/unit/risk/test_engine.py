import pytest
from decimal import Decimal

from platform_py.risk.engine import RiskEngine
from platform_py.types import Intent, IntentType, IntentConstraints, AssetSpec, ExecutionStyle, WETH_ETHEREUM


def make_intent(max_slippage: Decimal, amount: Decimal | None):
    spec_base = AssetSpec(asset=WETH_ETHEREUM, amount=amount)
    intent = Intent(
        strategy_id=__import__('uuid').uuid4(),
        type=IntentType.ACQUIRE,
        assets=[spec_base],
        constraints=IntentConstraints(
            max_slippage=max_slippage,
            time_window_ms=60_000,
            execution_style=ExecutionStyle.ADAPTIVE,
        ),
    )
    return intent


@pytest.mark.asyncio
async def test_risk_engine_slippage_gate_rejects_over_limit():
    engine = RiskEngine()
    intent = make_intent(max_slippage=RiskEngine.MAX_SLIPPAGE + Decimal("0.01"), amount=Decimal("100"))
    decision = await engine.evaluate_risk(intent)
    assert not decision.approved
    assert decision["reason"] == "SLIPPAGE_LIMIT"


@pytest.mark.asyncio
async def test_risk_engine_notional_gate_rejects_over_limit():
    engine = RiskEngine()
    intent = make_intent(max_slippage=Decimal("0.01"), amount=RiskEngine.MAX_NOTIONAL_USD + Decimal("0.01"))
    decision = await engine.evaluate_risk(intent)
    assert not decision.approved
    assert decision["reason"] == "NOTIONAL_LIMIT"


@pytest.mark.asyncio
async def test_risk_engine_approves_at_limits():
    engine = RiskEngine()
    intent = make_intent(max_slippage=RiskEngine.MAX_SLIPPAGE, amount=RiskEngine.MAX_NOTIONAL_USD)
    decision = await engine.evaluate_risk(intent)
    assert decision.approved
