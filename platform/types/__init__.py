"""
Type definitions for the trading platform.
"""

from .common import (
    Asset, TradingPair, Chain, Venue, AssetAmount, Price,
    WETH_ETHEREUM, USDC_ETHEREUM, WETH_ARBITRUM, USDC_ARBITRUM
)
from .intent import (
    Intent, IntentType, IntentStatus, IntentConstraints, AssetSpec, 
    IntentReceipt, IntentUpdate, MLFeatures, ExecutionStyle,
    create_acquire_intent, create_rebalance_intent
)
# Optional event imports (avoid heavy deps during lightweight contexts like tests)
try:
    from .events import (
        Event, EventPayload, EventMetadata, EventFilter, EventProjection,
        IntentSubmittedPayload, IntentValidatedPayload, IntentStatusChangedPayload,
        StrategyStartedPayload, StrategySignalPayload, PriceUpdatePayload,
        OrderSubmittedPayload, OrderFilledPayload, TransactionConfirmedPayload,
        create_intent_submitted_event, create_intent_status_changed_event, create_strategy_signal_event
    )
    _EVENTS_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency path
    _EVENTS_AVAILABLE = False

__all__ = [
    # Common types
    "Asset", "TradingPair", "Chain", "Venue", "AssetAmount", "Price",
    "WETH_ETHEREUM", "USDC_ETHEREUM", "WETH_ARBITRUM", "USDC_ARBITRUM",
    
    # Intent types
    "Intent", "IntentType", "IntentStatus", "IntentConstraints", "AssetSpec",
    "IntentReceipt", "IntentUpdate", "MLFeatures", "ExecutionStyle",
    "create_acquire_intent", "create_rebalance_intent",
]

# Extend exports only if events are available
if _EVENTS_AVAILABLE:
    __all__.extend([
        "Event", "EventPayload", "EventMetadata", "EventFilter", "EventProjection",
        "IntentSubmittedPayload", "IntentValidatedPayload", "IntentStatusChangedPayload",
        "StrategyStartedPayload", "StrategySignalPayload", "PriceUpdatePayload",
        "OrderSubmittedPayload", "OrderFilledPayload", "TransactionConfirmedPayload",
        "create_intent_submitted_event", "create_intent_status_changed_event", "create_strategy_signal_event",
    ])
