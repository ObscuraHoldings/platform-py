
from decimal import Decimal
from typing import Dict, Any

from ..types import Intent


class RiskDecision(Dict[str, Any]):
    @property
    def approved(self) -> bool:
        return bool(self.get("approved", False))


class RiskEngine:
    """Stateless V1 risk checks: notional and slippage gates."""

    MAX_NOTIONAL_USD = Decimal("10000")
    MAX_SLIPPAGE = Decimal("0.05")  # 5%

    async def evaluate_risk(self, intent: Intent) -> RiskDecision:
        # Slippage gate
        if intent.constraints.max_slippage > self.MAX_SLIPPAGE:
            return RiskDecision(approved=False, reason="SLIPPAGE_LIMIT")

        # Notional gate (best-effort: use first asset amount if present)
        amount = None
        if intent.assets and intent.assets[0].amount is not None:
            amount = intent.assets[0].amount
        # If no explicit amount, approve (no portfolio/price context in V1)
        if amount is not None and amount > self.MAX_NOTIONAL_USD:
            return RiskDecision(approved=False, reason="NOTIONAL_LIMIT")

        return RiskDecision(approved=True)
