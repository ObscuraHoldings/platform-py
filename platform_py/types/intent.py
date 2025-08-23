"""
Intent type definitions with ML support.

This module provides intent types for trading operations with machine learning integration.
"""

from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any, Union
from uuid import UUID, uuid4
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

from .common import Asset, AssetAmount, TradingPair, Venue


class IntentType(Enum):
    """Types of trading intents."""
    
    ACQUIRE = "acquire"
    DISPOSE = "dispose" 
    REBALANCE = "rebalance"
    HEDGE = "hedge"
    ARBITRAGE = "arbitrage"
    LIQUIDATE = "liquidate"


class ExecutionStyle(Enum):
    """Execution style preferences."""
    
    AGGRESSIVE = "aggressive"  # Fast execution, higher slippage tolerance
    PASSIVE = "passive"       # Patient execution, lower slippage tolerance
    ADAPTIVE = "adaptive"     # ML-driven adaptive execution
    STEALTH = "stealth"       # Hidden execution to minimize market impact


class IntentStatus(Enum):
    """Intent lifecycle status."""
    
    PENDING = "pending"
    VALIDATED = "validated"
    QUEUED = "queued"
    PROCESSING = "processing"
    PARTIALLY_FILLED = "partially_filled"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class IntentConstraints(BaseModel):
    """Constraints and preferences for intent execution."""
    
    # Core constraints
    max_slippage: Decimal = Field(..., ge=0, le=1, description="Maximum slippage tolerance (0-1)")
    time_window_ms: int = Field(..., gt=0, description="Time window for execution in milliseconds")
    execution_style: ExecutionStyle = Field(..., description="Execution style preference")
    
    # Size constraints
    min_fill_size: Optional[Decimal] = Field(None, ge=0, description="Minimum fill size")
    max_fill_size: Optional[Decimal] = Field(None, ge=0, description="Maximum fill size per transaction")
    
    # Gas and cost constraints
    max_gas_price_gwei: Optional[Decimal] = Field(None, ge=0, description="Maximum gas price in Gwei")
    max_total_gas_cost: Optional[AssetAmount] = Field(None, description="Maximum total gas cost")
    
    # Venue constraints
    allowed_venues: Optional[List[Venue]] = Field(None, description="Allowed trading venues")
    excluded_venues: Optional[List[Venue]] = Field(None, description="Excluded trading venues")
    
    # MEV protection
    enable_mev_protection: bool = Field(default=True, description="Enable MEV protection")
    private_mempool: bool = Field(default=False, description="Use private mempool")
    
    # ML-specific constraints
    ml_model_path: Optional[str] = Field(None, description="Path to ML model for execution optimization")
    feature_vector: Optional[List[float]] = Field(None, description="Feature vector for ML model")
    confidence_threshold: Optional[float] = Field(None, ge=0, le=1, description="ML confidence threshold")
    use_ml_optimization: bool = Field(default=True, description="Enable ML-based optimization")
    
    @model_validator(mode='after')
    def validate_fill_sizes(self) -> 'IntentConstraints':
        """Validate max_fill_size is greater than min_fill_size."""
        if self.max_fill_size is not None and self.min_fill_size is not None:
            if self.max_fill_size < self.min_fill_size:
                raise ValueError("max_fill_size must be greater than min_fill_size")
        return self
    
    @model_validator(mode='after')
    def validate_venue_constraints(self):
        """Validate venue constraints don't conflict."""
        allowed = self.allowed_venues or []
        excluded = self.excluded_venues or []
        
        if allowed and excluded:
            overlap = set(allowed) & set(excluded)
            if overlap:
                raise ValueError(f"Venues cannot be both allowed and excluded: {overlap}")
        return self


class AssetSpec(BaseModel):
    """Asset specification for intents."""
    
    asset: Asset = Field(..., description="Asset to trade")
    amount: Optional[Decimal] = Field(None, ge=0, description="Specific amount to trade")
    percentage: Optional[Decimal] = Field(None, ge=0, le=1, description="Percentage of portfolio")
    target_weight: Optional[Decimal] = Field(None, ge=0, le=1, description="Target portfolio weight")
    
    @model_validator(mode='after')
    def validate_amount_spec(self):
        """Ensure exactly one amount specification is provided."""
        amount = self.amount
        percentage = self.percentage
        target_weight = self.target_weight
        
        specified = sum(x is not None for x in [amount, percentage, target_weight])
        if specified != 1:
            raise ValueError("Exactly one of amount, percentage, or target_weight must be specified")
        return self


class MLFeatures(BaseModel):
    """ML features for intent classification and optimization."""
    
    # Market features
    volatility: Optional[float] = Field(None, description="Market volatility")
    volume_ratio: Optional[float] = Field(None, description="Volume ratio vs historical average")
    spread: Optional[float] = Field(None, description="Bid-ask spread")
    market_impact: Optional[float] = Field(None, description="Estimated market impact")
    
    # Time features
    time_of_day: Optional[float] = Field(None, ge=0, le=24, description="Hour of day")
    day_of_week: Optional[int] = Field(None, ge=0, le=6, description="Day of week (0=Monday)")
    is_market_hours: Optional[bool] = Field(None, description="During traditional market hours")
    
    # Portfolio features
    portfolio_concentration: Optional[float] = Field(None, description="Portfolio concentration risk")
    position_size_ratio: Optional[float] = Field(None, description="Position size vs portfolio")
    
    # Network features
    gas_price_percentile: Optional[float] = Field(None, ge=0, le=100, description="Gas price percentile")
    mempool_congestion: Optional[float] = Field(None, description="Mempool congestion level")
    
    # Custom features
    custom_features: Dict[str, float] = Field(default_factory=dict, description="Custom ML features")


class Intent(BaseModel):
    """Trading intent with ML support."""
    
    # Identity
    id: UUID = Field(default_factory=uuid4, description="Unique intent ID")
    strategy_id: UUID = Field(..., description="Strategy that generated this intent")
    parent_intent_id: Optional[UUID] = Field(None, description="Parent intent if this is a sub-intent")
    
    # Timing
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Intent creation timestamp")
    expires_at: Optional[datetime] = Field(None, description="Intent expiration time")
    
    # Core intent data
    type: IntentType = Field(..., description="Intent type")
    assets: List[AssetSpec] = Field(..., min_length=1, description="Assets to trade")
    constraints: IntentConstraints = Field(..., description="Execution constraints")
    
    # Priority and metadata
    priority: int = Field(default=5, ge=1, le=10, description="Intent priority (1=lowest, 10=highest)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    tags: List[str] = Field(default_factory=list, description="Intent tags for categorization")
    
    # Status tracking
    status: IntentStatus = Field(default=IntentStatus.PENDING, description="Current status")
    status_reason: Optional[str] = Field(None, description="Reason for current status")
    
    # ML features
    ml_features: Optional[MLFeatures] = Field(None, description="ML features for optimization")
    ml_score: Optional[float] = Field(None, ge=0, le=1, description="ML-generated intent score")
    ml_predictions: Dict[str, float] = Field(default_factory=dict, description="ML model predictions")
    
    # Execution tracking
    submitted_orders: List[UUID] = Field(default_factory=list, description="Submitted order IDs")
    filled_amount: Optional[Decimal] = Field(default=Decimal('0'), ge=0, description="Amount filled so far")
    average_price: Optional[Decimal] = Field(None, description="Average execution price")
    total_gas_used: Optional[Decimal] = Field(default=Decimal('0'), ge=0, description="Total gas used")
    
    @model_validator(mode='after')
    def validate_expiration(self) -> 'Intent':
        """Validate expiration is in the future."""
        if self.expires_at is not None:
            ts = self.timestamp or datetime.now(timezone.utc)
            if self.expires_at <= ts:
                raise ValueError("Expiration time must be in the future")
        return self
    
    @field_validator('assets')
    def validate_assets_not_empty(cls, v: List[AssetSpec]) -> List[AssetSpec]:
        """Ensure assets list is not empty."""
        if not v:
            raise ValueError("Intent must specify at least one asset")
        return v
    
    @property
    def is_expired(self) -> bool:
        """Check if intent has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at
    
    @property
    def time_remaining(self) -> Optional[timedelta]:
        """Get time remaining until expiration."""
        if self.expires_at is None:
            return None
        remaining = self.expires_at - datetime.now(timezone.utc)
        return remaining if remaining.total_seconds() > 0 else timedelta(0)
    
    @property
    def is_multi_asset(self) -> bool:
        """Check if intent involves multiple assets."""
        return len(self.assets) > 1
    
    @property
    def primary_asset(self) -> Asset:
        """Get the primary asset (first in list)."""
        return self.assets[0].asset
    
    def get_asset_amount(self, asset: Asset) -> Optional[AssetSpec]:
        """Get asset specification for a specific asset."""
        for spec in self.assets:
            if spec.asset == asset:
                return spec
        return None
    
    def update_status(self, new_status: IntentStatus, reason: Optional[str] = None) -> None:
        """Update intent status with reason."""
        self.status = new_status
        self.status_reason = reason
    
    def add_ml_prediction(self, model_name: str, prediction: float) -> None:
        """Add ML model prediction."""
        self.ml_predictions[model_name] = prediction
    
    def calculate_fill_percentage(self) -> Decimal:
        """Calculate percentage of intent filled."""
        if not self.assets or self.filled_amount is None:
            return Decimal('0')
        
        # For single asset intents with specific amounts
        primary_spec = self.assets[0]
        if primary_spec.amount is not None:
            return min(self.filled_amount / primary_spec.amount, Decimal('1'))
        
        # For percentage-based intents, this would need portfolio context
        return Decimal('0')


class IntentReceipt(BaseModel):
    """Receipt returned when submitting an intent."""
    
    intent_id: UUID = Field(..., description="Intent ID")
    received: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Receipt timestamp")
    status: IntentStatus = Field(default=IntentStatus.PENDING, description="Initial status")
    estimated_execution_time: Optional[timedelta] = Field(None, description="Estimated execution time")
    warnings: Optional[List[str]] = Field(None, description="Validation warnings")
    queue_position: Optional[int] = Field(None, description="Position in execution queue")


class IntentUpdate(BaseModel):
    """Intent status update notification."""
    
    intent_id: UUID = Field(..., description="Intent ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Update timestamp")
    old_status: IntentStatus = Field(..., description="Previous status")
    new_status: IntentStatus = Field(..., description="New status")
    reason: Optional[str] = Field(None, description="Reason for status change")
    filled_amount: Optional[Decimal] = Field(None, description="Amount filled")
    execution_details: Dict[str, Any] = Field(default_factory=dict, description="Execution details")


# Intent builder helper functions
def create_acquire_intent(
    strategy_id: UUID,
    asset: Asset,
    amount: Decimal,
    max_slippage: Decimal = Decimal('0.005'),
    time_window_ms: int = 60000,
    execution_style: ExecutionStyle = ExecutionStyle.ADAPTIVE
) -> Intent:
    """Create a simple acquire intent."""
    return Intent(
        strategy_id=strategy_id,
        type=IntentType.ACQUIRE,
        assets=[AssetSpec(asset=asset, amount=amount)],
        constraints=IntentConstraints(
            max_slippage=max_slippage,
            time_window_ms=time_window_ms,
            execution_style=execution_style
        )
    )


def create_rebalance_intent(
    strategy_id: UUID,
    target_weights: Dict[Asset, Decimal],
    max_slippage: Decimal = Decimal('0.01'),
    time_window_ms: int = 300000  # 5 minutes
) -> Intent:
    """Create a portfolio rebalance intent."""
    assets = [
        AssetSpec(asset=asset, target_weight=weight)
        for asset, weight in target_weights.items()
    ]
    
    return Intent(
        strategy_id=strategy_id,
        type=IntentType.REBALANCE,
        assets=assets,
        constraints=IntentConstraints(
            max_slippage=max_slippage,
            time_window_ms=time_window_ms,
            execution_style=ExecutionStyle.ADAPTIVE
        )
    )
