"""
Type definitions for the trading platform.
"""

from .common import (
    Asset, TradingPair, Chain, Venue, AssetAmount, Price, OrderBook,
    WETH_ETHEREUM, USDC_ETHEREUM, WETH_ARBITRUM, USDC_ARBITRUM
)
from .intent import (
    Intent, IntentType, IntentStatus, IntentConstraints, AssetSpec, 
    IntentReceipt, IntentUpdate, MLFeatures, ExecutionStyle,
    create_acquire_intent, create_rebalance_intent
)
from .events import (
    Event, EventPayload, EventMetadata, EventFilter, EventProjection,
    IntentSubmittedPayload, IntentValidatedPayload, IntentStatusChangedPayload,
    StrategyStartedPayload, StrategySignalPayload, PriceUpdatePayload,
    OrderSubmittedPayload, OrderFilledPayload, TransactionConfirmedPayload,
        create_intent_submitted_event, create_intent_status_changed_event, create_strategy_signal_event
    )

from .envelope import EventEnvelope, ulid, envelope

__all__ = [
    # Common types
    "Asset", "TradingPair", "Chain", "Venue", "AssetAmount", "Price", "OrderBook",
    "WETH_ETHEREUM", "USDC_ETHEREUM", "WETH_ARBITRUM", "USDC_ARBITRUM",
    
    # Intent types
    "Intent", "IntentType", "IntentStatus", "IntentConstraints", "AssetSpec",
    "IntentReceipt", "IntentUpdate", "MLFeatures", "ExecutionStyle",
    "create_acquire_intent", "create_rebalance_intent",
]

# Extend exports only if events are available
__all__.extend([
    "Event", "EventPayload", "EventMetadata", "EventFilter", "EventProjection",
    "IntentSubmittedPayload", "IntentValidatedPayload", "IntentStatusChangedPayload",
    "StrategyStartedPayload", "StrategySignalPayload", "PriceUpdatePayload",
    "OrderSubmittedPayload", "OrderFilledPayload", "TransactionConfirmedPayload",
        "create_intent_submitted_event", "create_intent_status_changed_event", "create_strategy_signal_event",
    ])

__all__.extend([
    "EventEnvelope", "ulid", "envelope",
])
