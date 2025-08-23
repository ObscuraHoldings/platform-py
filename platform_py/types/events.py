"""
Event type definitions for time-series storage and event sourcing.

This module provides event types for TimescaleDB with bi-temporal tracking and audit trails.
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional, List, Union, Type, TypeVar
from uuid import UUID, uuid4
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field, field_validator, ConfigDict
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

from .common import Asset, AssetAmount, TradingPair
from .intent import Intent, IntentStatus


EventPayloadType = TypeVar('EventPayloadType', bound='EventPayload')


class EventPayload(BaseModel, ABC):
    """Base class for all event payloads."""
    
    # Allow arbitrary types without deprecated Config class
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    @abstractmethod
    def get_event_type(self) -> str:
        """Get the event type string."""
        pass


class EventMetadata(BaseModel):
    """Metadata for events."""
    
    source_service: str = Field(..., description="Service that generated the event")
    source_version: str = Field(..., description="Version of the source service")
    correlation_id: Optional[UUID] = Field(None, description="Correlation ID for request tracing")
    causation_id: Optional[UUID] = Field(None, description="ID of the event that caused this event")
    user_id: Optional[UUID] = Field(None, description="User ID if applicable")
    session_id: Optional[UUID] = Field(None, description="Session ID if applicable")
    environment: str = Field(default="development", description="Environment (dev/staging/prod)")
    additional_data: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class Event(BaseModel):
    """Base event class for event sourcing with bi-temporal tracking."""
    
    # Event identity
    id: UUID = Field(default_factory=uuid4, description="Unique event ID")
    event_type: str = Field(..., description="Event type identifier")
    event_version: int = Field(default=1, description="Event schema version")
    
    # Aggregate information
    aggregate_id: UUID = Field(..., description="ID of the aggregate this event belongs to")
    aggregate_type: str = Field(..., description="Type of the aggregate")
    aggregate_version: int = Field(..., ge=1, description="Version of the aggregate after this event")
    
    # Bi-temporal tracking
    business_timestamp: datetime = Field(..., description="When the business event occurred")
    system_timestamp: datetime = Field(default_factory=datetime.utcnow, description="When event was recorded")
    
    # Event data
    payload: EventPayload = Field(..., description="Event payload data")
    metadata: EventMetadata = Field(..., description="Event metadata")
    
    # Audit and security
    signature: Optional[bytes] = Field(None, description="Digital signature for audit trail")
    signer_public_key: Optional[bytes] = Field(None, description="Public key of the signer")
    hash: Optional[str] = Field(None, description="Event content hash")
    
    @field_validator('business_timestamp')
    def validate_business_timestamp(cls, v: datetime) -> datetime:
        """Validate business timestamp is not in the future."""
        if v > datetime.utcnow():
            raise ValueError("Business timestamp cannot be in the future")
        return v
    
    def get_signing_message(self) -> bytes:
        """Get the message to sign for audit trail."""
        # Create a deterministic representation for signing
        signing_data = {
            "id": str(self.id),
            "event_type": self.event_type,
            "aggregate_id": str(self.aggregate_id),
            "aggregate_version": self.aggregate_version,
            "business_timestamp": self.business_timestamp.isoformat(),
            "payload": self.payload.model_dump()
        }
        return json.dumps(signing_data, sort_keys=True).encode('utf-8')
    
    def sign(self, private_key: ed25519.Ed25519PrivateKey) -> None:
        """Sign the event for audit trail."""
        message = self.get_signing_message()
        self.signature = private_key.sign(message)
        self.signer_public_key = private_key.public_key().public_bytes_raw()
        
        # Calculate content hash
        hasher = hashes.Hash(hashes.SHA256())
        hasher.update(message)
        self.hash = hasher.finalize().hex()
    
    def verify_signature(self) -> bool:
        """Verify the event signature."""
        if not self.signature or not self.signer_public_key:
            return False
        
        try:
            public_key = ed25519.Ed25519PublicKey.from_public_bytes_raw(self.signer_public_key)
            message = self.get_signing_message()
            public_key.verify(self.signature, message)
            return True
        except (InvalidSignature, ValueError):
            return False
    
    @property
    def age(self) -> float:
        """Get event age in seconds."""
        return (datetime.utcnow() - self.system_timestamp).total_seconds()
    
    @property
    def business_age(self) -> float:
        """Get business event age in seconds."""
        return (datetime.utcnow() - self.business_timestamp).total_seconds()


# Intent Events
class IntentSubmittedPayload(EventPayload):
    """Payload for intent submission events."""
    
    intent_id: UUID = Field(..., description="Intent ID")
    strategy_id: UUID = Field(..., description="Strategy ID")
    intent_type: str = Field(..., description="Intent type")
    intent_data: Dict[str, Any] = Field(..., description="Complete intent data")
    
    def get_event_type(self) -> str:
        return "intent.submitted"


class IntentValidatedPayload(EventPayload):
    """Payload for intent validation events."""
    
    intent_id: UUID = Field(..., description="Intent ID")
    validation_result: bool = Field(..., description="Validation result")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    ml_score: Optional[float] = Field(None, description="ML validation score")
    
    def get_event_type(self) -> str:
        return "intent.validated"


class IntentStatusChangedPayload(EventPayload):
    """Payload for intent status change events."""
    
    intent_id: UUID = Field(..., description="Intent ID")
    old_status: str = Field(..., description="Previous status")
    new_status: str = Field(..., description="New status")
    reason: Optional[str] = Field(None, description="Reason for status change")
    filled_amount: Optional[str] = Field(None, description="Amount filled (as string for precision)")
    
    def get_event_type(self) -> str:
        return "intent.status_changed"


class IntentExpiredPayload(EventPayload):
    """Payload for intent expiration events."""
    
    intent_id: UUID = Field(..., description="Intent ID")
    expired_at: datetime = Field(..., description="Expiration timestamp")
    partial_fill: bool = Field(..., description="Whether intent was partially filled")
    filled_amount: Optional[str] = Field(None, description="Amount filled before expiration")
    
    def get_event_type(self) -> str:
        return "intent.expired"


# Strategy Events
class StrategyStartedPayload(EventPayload):
    """Payload for strategy startup events."""
    
    strategy_id: UUID = Field(..., description="Strategy ID")
    strategy_name: str = Field(..., description="Strategy name")
    strategy_version: str = Field(..., description="Strategy version")
    configuration: Dict[str, Any] = Field(..., description="Strategy configuration")
    ml_models: List[str] = Field(default_factory=list, description="ML models used")
    
    def get_event_type(self) -> str:
        return "strategy.started"


class StrategyStoppedPayload(EventPayload):
    """Payload for strategy shutdown events."""
    
    strategy_id: UUID = Field(..., description="Strategy ID")
    reason: str = Field(..., description="Reason for shutdown")
    final_state: Dict[str, Any] = Field(..., description="Final strategy state")
    
    def get_event_type(self) -> str:
        return "strategy.stopped"


class StrategySignalPayload(EventPayload):
    """Payload for strategy signal events."""
    
    strategy_id: UUID = Field(..., description="Strategy ID")
    signal_type: str = Field(..., description="Signal type")
    signal_strength: float = Field(..., ge=0, le=1, description="Signal strength")
    assets: List[Dict[str, Any]] = Field(..., description="Assets involved")
    confidence: Optional[float] = Field(None, description="ML confidence")
    features: Dict[str, float] = Field(default_factory=dict, description="ML features")
    
    def get_event_type(self) -> str:
        return "strategy.signal"


# Market Data Events
class PriceUpdatePayload(EventPayload):
    """Payload for price update events."""
    
    pair: Dict[str, Any] = Field(..., description="Trading pair data")
    price: str = Field(..., description="Price (as string for precision)")
    volume_24h: Optional[str] = Field(None, description="24h volume")
    source: str = Field(..., description="Price source")
    confidence: Optional[float] = Field(None, description="Price confidence")
    
    def get_event_type(self) -> str:
        return "market.price_update"


class LiquidityUpdatePayload(EventPayload):
    """Payload for liquidity update events."""
    
    pair: Dict[str, Any] = Field(..., description="Trading pair data")
    venue: str = Field(..., description="Trading venue")
    total_liquidity: str = Field(..., description="Total liquidity")
    depth_data: Dict[str, Any] = Field(..., description="Order book depth")
    
    def get_event_type(self) -> str:
        return "market.liquidity_update"


# Execution Events
class OrderSubmittedPayload(EventPayload):
    """Payload for order submission events."""
    
    order_id: UUID = Field(..., description="Order ID")
    intent_id: UUID = Field(..., description="Related intent ID")
    venue: str = Field(..., description="Trading venue")
    order_type: str = Field(..., description="Order type")
    amount: str = Field(..., description="Order amount")
    price: Optional[str] = Field(None, description="Order price")
    
    def get_event_type(self) -> str:
        return "execution.order_submitted"


class OrderFilledPayload(EventPayload):
    """Payload for order fill events."""
    
    order_id: UUID = Field(..., description="Order ID")
    intent_id: UUID = Field(..., description="Related intent ID")
    fill_amount: str = Field(..., description="Fill amount")
    fill_price: str = Field(..., description="Fill price")
    gas_used: Optional[int] = Field(None, description="Gas used")
    transaction_hash: Optional[str] = Field(None, description="Transaction hash")
    
    def get_event_type(self) -> str:
        return "execution.order_filled"


class TransactionConfirmedPayload(EventPayload):
    """Payload for transaction confirmation events."""
    
    transaction_hash: str = Field(..., description="Transaction hash")
    block_number: int = Field(..., description="Block number")
    gas_used: int = Field(..., description="Gas used")
    gas_price: str = Field(..., description="Gas price")
    status: str = Field(..., description="Transaction status")
    
    def get_event_type(self) -> str:
        return "execution.transaction_confirmed"


# ML Events
class ModelTrainingStartedPayload(EventPayload):
    """Payload for ML model training events."""
    
    model_id: UUID = Field(..., description="Model ID")
    model_type: str = Field(..., description="Model type")
    training_data_size: int = Field(..., description="Training data size")
    hyperparameters: Dict[str, Any] = Field(..., description="Model hyperparameters")
    
    def get_event_type(self) -> str:
        return "ml.training_started"


class ModelTrainingCompletedPayload(EventPayload):
    """Payload for ML model training completion events."""
    
    model_id: UUID = Field(..., description="Model ID")
    model_path: str = Field(..., description="Trained model path")
    metrics: Dict[str, float] = Field(..., description="Training metrics")
    training_duration_seconds: float = Field(..., description="Training duration")
    
    def get_event_type(self) -> str:
        return "ml.training_completed"


class ModelInferencePayload(EventPayload):
    """Payload for ML model inference events."""
    
    model_id: UUID = Field(..., description="Model ID")
    input_features: Dict[str, float] = Field(..., description="Input features")
    prediction: Dict[str, float] = Field(..., description="Model prediction")
    confidence: float = Field(..., description="Prediction confidence")
    inference_time_ms: float = Field(..., description="Inference time in milliseconds")
    
    def get_event_type(self) -> str:
        return "ml.inference"


# System Events
class SystemStartedPayload(EventPayload):
    """Payload for system startup events."""
    
    service_name: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    environment: str = Field(..., description="Environment")
    configuration: Dict[str, Any] = Field(..., description="System configuration")
    
    def get_event_type(self) -> str:
        return "system.started"


class SystemErrorPayload(EventPayload):
    """Payload for system error events."""
    
    error_type: str = Field(..., description="Error type")
    error_message: str = Field(..., description="Error message")
    stack_trace: Optional[str] = Field(None, description="Stack trace")
    context: Dict[str, Any] = Field(default_factory=dict, description="Error context")
    
    def get_event_type(self) -> str:
        return "system.error"


# Event factory functions
def create_intent_submitted_event(
    intent: Intent,
    metadata: EventMetadata,
    business_timestamp: Optional[datetime] = None
) -> Event:
    """Create an intent submitted event."""
    payload = IntentSubmittedPayload(
        intent_id=intent.id,
        strategy_id=intent.strategy_id,
        intent_type=intent.type.value,
        intent_data=intent.model_dump()
    )
    
    return Event(
        event_type=payload.get_event_type(),
        aggregate_id=intent.id,
        aggregate_type="intent",
        aggregate_version=1,
        business_timestamp=business_timestamp or datetime.utcnow(),
        payload=payload,
        metadata=metadata
    )


def create_intent_status_changed_event(
    intent_id: UUID,
    old_status: IntentStatus,
    new_status: IntentStatus,
    metadata: EventMetadata,
    reason: Optional[str] = None,
    filled_amount: Optional[str] = None,
    aggregate_version: int = 1
) -> Event:
    """Create an intent status changed event."""
    payload = IntentStatusChangedPayload(
        intent_id=intent_id,
        old_status=old_status.value,
        new_status=new_status.value,
        reason=reason,
        filled_amount=filled_amount
    )
    
    return Event(
        event_type=payload.get_event_type(),
        aggregate_id=intent_id,
        aggregate_type="intent",
        aggregate_version=aggregate_version,
        business_timestamp=datetime.utcnow(),
        payload=payload,
        metadata=metadata
    )


def create_strategy_signal_event(
    strategy_id: UUID,
    signal_type: str,
    signal_strength: float,
    assets: List[Asset],
    metadata: EventMetadata,
    confidence: Optional[float] = None,
    features: Optional[Dict[str, float]] = None
) -> Event:
    """Create a strategy signal event."""
    payload = StrategySignalPayload(
        strategy_id=strategy_id,
        signal_type=signal_type,
        signal_strength=signal_strength,
        assets=[asset.model_dump() for asset in assets],
        confidence=confidence,
        features=features or {}
    )
    
    return Event(
        event_type=payload.get_event_type(),
        aggregate_id=strategy_id,
        aggregate_type="strategy",
        aggregate_version=1,
        business_timestamp=datetime.utcnow(),
        payload=payload,
        metadata=metadata
    )


# Event store interface
class EventFilter(BaseModel):
    """Filter for querying events."""
    
    aggregate_id: Optional[UUID] = None
    aggregate_type: Optional[str] = None
    event_type: Optional[str] = None
    from_timestamp: Optional[datetime] = None
    to_timestamp: Optional[datetime] = None
    from_version: Optional[int] = None
    to_version: Optional[int] = None
    metadata_filter: Dict[str, Any] = Field(default_factory=dict)


class EventProjection(BaseModel):
    """Base class for event projections."""
    
    id: UUID = Field(..., description="Projection ID")
    last_processed_event: Optional[UUID] = Field(None, description="Last processed event ID")
    last_processed_timestamp: Optional[datetime] = Field(None, description="Last processed timestamp")
    version: int = Field(default=1, description="Projection version")
    
    model_config = ConfigDict(arbitrary_types_allowed=True)