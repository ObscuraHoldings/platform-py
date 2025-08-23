"""
Common type definitions for the trading platform.

This module provides base types with validation for multi-chain trading operations.
"""

from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID, uuid4
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from eth_utils import is_checksum_address, to_checksum_address


class Chain(Enum):
    """Supported blockchain networks."""
    
    ETHEREUM = 1
    ARBITRUM = 42161
    BASE = 8453
    POLYGON = 137
    OPTIMISM = 10
    SEPOLIA = 11155111  # Testnet
    
    @property
    def name_str(self) -> str:
        """Get human-readable chain name."""
        return self.name.lower()
    
    @property
    def is_testnet(self) -> bool:
        """Check if chain is a testnet."""
        return self in [Chain.SEPOLIA]


class Venue(Enum):
    """Supported trading venues."""
    
    UNISWAP_V3 = "uniswap_v3"
    UNISWAP_V2 = "uniswap_v2"
    CURVE = "curve"
    BALANCER = "balancer"
    SUSHISWAP = "sushiswap"
    PANCAKESWAP = "pancakeswap"
    
    @property
    def supports_concentrated_liquidity(self) -> bool:
        """Check if venue supports concentrated liquidity."""
        return self in [Venue.UNISWAP_V3, Venue.BALANCER]


class Asset(BaseModel):
    """Asset definition with multi-chain support."""
    
    symbol: str = Field(..., min_length=1, max_length=10, description="Asset symbol")
    address: str = Field(..., pattern=r'^0x[a-fA-F0-9]{40}$', description="Contract address")
    decimals: int = Field(..., ge=0, le=77, description="Token decimals")
    chain_id: int = Field(..., gt=0, description="Blockchain network ID")
    name: Optional[str] = Field(None, max_length=100, description="Asset name")
    coingecko_id: Optional[str] = Field(None, description="CoinGecko API ID")
    
    @field_validator('address')
    def validate_checksum_address(cls, v: str) -> str:
        """Validate and convert to checksum address."""
        if not is_checksum_address(v):
            try:
                return to_checksum_address(v)
            except ValueError:
                raise ValueError(f"Invalid Ethereum address: {v}")
        return v
    
    @field_validator('chain_id')
    def validate_supported_chain(cls, v: int) -> int:
        """Validate chain ID is supported."""
        supported_chains = [chain.value for chain in Chain]
        if v not in supported_chains:
            raise ValueError(f"Unsupported chain ID: {v}. Supported: {supported_chains}")
        return v
    
    @property
    def chain(self) -> Chain:
        """Get Chain enum from chain_id."""
        return Chain(self.chain_id)
    
    @property
    def unique_id(self) -> str:
        """Get unique identifier across chains."""
        return f"{self.chain_id}:{self.address}"
    
    def __hash__(self) -> int:
        """Make Asset hashable for use in sets/dicts."""
        return hash(self.unique_id)
    
    def __eq__(self, other) -> bool:
        """Asset equality based on unique_id."""
        if not isinstance(other, Asset):
            return False
        return self.unique_id == other.unique_id
    
    model_config = ConfigDict(frozen=True)  # Make immutable


class TradingPair(BaseModel):
    """Trading pair definition."""
    
    base: Asset = Field(..., description="Base asset")
    quote: Asset = Field(..., description="Quote asset") 
    venue: Venue = Field(..., description="Trading venue")
    pool_address: Optional[str] = Field(None, pattern=r'^0x[a-fA-F0-9]{40}$', description="Pool contract address")
    fee_tier: Optional[int] = Field(None, ge=0, description="Fee tier in basis points")
    
    @model_validator(mode='after')
    def validate_same_chain(self):
        """Ensure both assets are on the same chain."""
        base = self.base
        quote = self.quote
        if base and quote and base.chain_id != quote.chain_id:
            raise ValueError(
                f"Base and quote assets must be on the same chain. Base: {base.chain_id}, Quote: {quote.chain_id}"
            )
        return self
    
    @field_validator('pool_address')
    def validate_pool_address(cls, v: Optional[str]) -> Optional[str]:
        """Validate pool address if provided."""
        if v is not None and not is_checksum_address(v):
            try:
                return to_checksum_address(v)
            except ValueError:
                raise ValueError(f"Invalid pool address: {v}")
        return v
    
    @property
    def symbol(self) -> str:
        """Get trading pair symbol."""
        return f"{self.base.symbol}/{self.quote.symbol}"
    
    @property
    def chain_id(self) -> int:
        """Get chain ID for the trading pair."""
        return self.base.chain_id
    
    @property
    def chain(self) -> Chain:
        """Get Chain enum for the trading pair."""
        return self.base.chain
    
    def __hash__(self) -> int:
        """Make TradingPair hashable."""
        return hash((self.base.unique_id, self.quote.unique_id, self.venue.value))
    
    def __eq__(self, other) -> bool:
        """TradingPair equality."""
        if not isinstance(other, TradingPair):
            return False
        return (self.base == other.base and 
                self.quote == other.quote and 
                self.venue == other.venue)
    
    model_config = ConfigDict(frozen=True)


class AssetAmount(BaseModel):
    """Asset amount with precise decimal handling."""
    
    asset: Asset = Field(..., description="Asset reference")
    amount: Decimal = Field(..., ge=0, description="Amount in asset units")
    
    @model_validator(mode='after')
    def validate_amount_precision(self) -> 'AssetAmount':
        """Validate amount precision matches asset decimals."""
        asset = self.asset
        v = self.amount
        if asset is not None and v is not None:
            # Check that amount doesn't have more decimal places than asset supports
            decimal_places = abs(v.as_tuple().exponent)
            if decimal_places > asset.decimals:
                raise ValueError(
                    f"Amount precision ({decimal_places}) exceeds asset decimals ({asset.decimals})"
                )
        return self
    
    @property
    def raw_amount(self) -> int:
        """Get raw amount as integer (wei-like units)."""
        return int(self.amount * (10 ** self.asset.decimals))
    
    @classmethod
    def from_raw(cls, asset: Asset, raw_amount: int) -> 'AssetAmount':
        """Create AssetAmount from raw integer amount."""
        amount = Decimal(raw_amount) / (10 ** asset.decimals)
        return cls(asset=asset, amount=amount)
    
    def __add__(self, other: 'AssetAmount') -> 'AssetAmount':
        """Add two asset amounts."""
        if self.asset != other.asset:
            raise ValueError("Cannot add amounts of different assets")
        return AssetAmount(asset=self.asset, amount=self.amount + other.amount)
    
    def __sub__(self, other: 'AssetAmount') -> 'AssetAmount':
        """Subtract two asset amounts."""
        if self.asset != other.asset:
            raise ValueError("Cannot subtract amounts of different assets")
        result_amount = self.amount - other.amount
        if result_amount < 0:
            raise ValueError("Result would be negative")
        return AssetAmount(asset=self.asset, amount=result_amount)
    
    def __mul__(self, scalar: Decimal) -> 'AssetAmount':
        """Multiply asset amount by scalar."""
        return AssetAmount(asset=self.asset, amount=self.amount * scalar)
    
    def __truediv__(self, scalar: Decimal) -> 'AssetAmount':
        """Divide asset amount by scalar."""
        if scalar == 0:
            raise ValueError("Cannot divide by zero")
        return AssetAmount(asset=self.asset, amount=self.amount / scalar)
    
    def __str__(self) -> str:
        """String representation."""
        return f"{self.amount} {self.asset.symbol}"


class Price(BaseModel):
    """Price representation for trading pairs."""
    
    pair: TradingPair = Field(..., description="Trading pair")
    price: Decimal = Field(..., gt=0, description="Price (quote per base)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Price timestamp")
    source: str = Field(..., description="Price source")
    
    @property
    def inverse_price(self) -> Decimal:
        """Get inverse price (base per quote)."""
        return Decimal('1') / self.price
    
    def convert_amount(self, amount: AssetAmount) -> AssetAmount:
        """Convert amount from base to quote or vice versa."""
        if amount.asset == self.pair.base:
            # Convert base to quote
            quote_amount = amount.amount * self.price
            return AssetAmount(asset=self.pair.quote, amount=quote_amount)
        elif amount.asset == self.pair.quote:
            # Convert quote to base  
            base_amount = amount.amount / self.price
            return AssetAmount(asset=self.pair.base, amount=base_amount)
        else:
            raise ValueError(f"Amount asset {amount.asset.symbol} not in pair {self.pair.symbol}")


class OrderBook(BaseModel):
    """Represents the order book for a trading pair."""
    
    pair: TradingPair = Field(..., description="Trading pair")
    bids: List[Tuple[Decimal, Decimal]] = Field(..., description="List of (price, quantity) for bids")
    asks: List[Tuple[Decimal, Decimal]] = Field(..., description="List of (price, quantity) for asks")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Order book timestamp")
    
    @property
    def best_bid(self) -> Optional[Decimal]:
        """Get best bid price."""
        return max(bid[0] for bid in self.bids) if self.bids else None
    
    @property
    def best_ask(self) -> Optional[Decimal]:
        """Get best ask price."""
        return min(ask[0] for ask in self.asks) if self.asks else None
    
    @property
    def spread(self) -> Optional[Decimal]:
        """Get bid-ask spread."""
        best_bid = self.best_bid
        best_ask = self.best_ask
        if best_bid and best_ask:
            return best_ask - best_bid
        return None
    
    @property
    def mid_price(self) -> Optional[Decimal]:
        """Get mid price."""
        best_bid = self.best_bid
        best_ask = self.best_ask
        if best_bid and best_ask:
            return (best_bid + best_ask) / Decimal('2')
        return None
    
    def get_depth(self, side: str, price_levels: int = 10) -> List[Tuple[Decimal, Decimal]]:
        """Get order book depth for specified side."""
        if side.lower() == 'bid':
            return sorted(self.bids, key=lambda x: x[0], reverse=True)[:price_levels]
        elif side.lower() == 'ask':
            return sorted(self.asks, key=lambda x: x[0])[:price_levels]
        else:
            raise ValueError("Side must be 'bid' or 'ask'")
    
    def get_liquidity_at_price(self, price: Decimal, side: str) -> Decimal:
        """Get available liquidity at a specific price level."""
        levels = self.bids if side.lower() == 'bid' else self.asks
        for level_price, quantity in levels:
            if level_price == price:
                return quantity
        return Decimal('0')


# Common asset definitions for major chains
WETH_ETHEREUM = Asset(
    symbol="WETH",
    address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    decimals=18,
    chain_id=Chain.ETHEREUM.value,
    name="Wrapped Ether"
)

USDC_ETHEREUM = Asset(
    symbol="USDC",
    address="0xA0b86a33E6417c8e83Af79F67068b60f7A0B4dd5",
    decimals=6,
    chain_id=Chain.ETHEREUM.value,
    name="USD Coin"
)

WETH_ARBITRUM = Asset(
    symbol="WETH",
    address="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    decimals=18,
    chain_id=Chain.ARBITRUM.value,
    name="Wrapped Ether"
)

USDC_ARBITRUM = Asset(
    symbol="USDC",
    address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    decimals=6,
    chain_id=Chain.ARBITRUM.value,
    name="USD Coin"
)


class BaseEntity(BaseModel):
    """Base entity with common fields."""
    
    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    
    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()


class TimestampedEntity(BaseModel):
    """Entity with timestamp tracking."""
    
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp")
    block_number: Optional[int] = Field(None, ge=0, description="Blockchain block number")
    transaction_hash: Optional[str] = Field(None, pattern=r'^0x[a-fA-F0-9]{64}$', description="Transaction hash")
    
    @field_validator('transaction_hash', mode='before')
    def validate_tx_hash(cls, v: Optional[str]) -> Optional[str]:
        """Validate transaction hash format."""
        if v is not None and not v.startswith('0x'):
            return f"0x{v}"
        return v


class ValidationMixin:
    """Mixin for additional validation utilities."""
    
    @classmethod
    def validate_percentage(cls, v: Decimal, field_name: str = "percentage") -> Decimal:
        """Validate percentage is between 0 and 100."""
        if not (Decimal('0') <= v <= Decimal('100')):
            raise ValueError(f"{field_name} must be between 0 and 100, got {v}")
        return v
    
    @classmethod
    def validate_positive_decimal(cls, v: Decimal, field_name: str = "value") -> Decimal:
        """Validate decimal is positive."""
        if v <= 0:
            raise ValueError(f"{field_name} must be positive, got {v}")
        return v


# Asset registry for common tokens
ASSET_REGISTRY: Dict[str, Asset] = {
    "WETH_ETHEREUM": WETH_ETHEREUM,
    "USDC_ETHEREUM": USDC_ETHEREUM,
    "WETH_ARBITRUM": WETH_ARBITRUM,
    "USDC_ARBITRUM": USDC_ARBITRUM,
}


def get_asset_by_key(key: str) -> Optional[Asset]:
    """Get asset from registry by key."""
    return ASSET_REGISTRY.get(key)


def get_asset_by_address(address: str, chain_id: int) -> Optional[Asset]:
    """Get asset from registry by address and chain."""
    for asset in ASSET_REGISTRY.values():
        if asset.address.lower() == address.lower() and asset.chain_id == chain_id:
            return asset
    return None


def create_trading_pair(base_key: str, quote_key: str, venue: Venue) -> Optional[TradingPair]:
    """Create a trading pair from asset registry keys."""
    base = get_asset_by_key(base_key)
    quote = get_asset_by_key(quote_key)
    
    if base and quote:
        return TradingPair(base=base, quote=quote, venue=venue)
    return None
