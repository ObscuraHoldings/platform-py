"""
Venue adapter interface and multi-chain support.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from ...types import Asset, TradingPair, Price, OrderBook

class VenueAdapter(ABC):
    """Abstract base class for all venue adapters."""
    
    @abstractmethod
    async def get_name(self) -> str:
        """Get the name of the venue."""
        pass

    @abstractmethod
    async def get_supported_chains(self) -> List[int]:
        """Get a list of supported chain IDs."""
        pass

    @abstractmethod
    async def get_trading_pairs(self, chain_id: int) -> List[TradingPair]:
        """Get a list of available trading pairs on a specific chain."""
        pass

    @abstractmethod
    async def get_price(self, pair: TradingPair) -> Price:
        """Get the current price for a trading pair."""
        pass

    @abstractmethod
    async def get_order_book(self, pair: TradingPair, depth: int = 20) -> OrderBook:
        """Get the order book for a trading pair."""
        pass

    @abstractmethod
    async def submit_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Submit an order to the venue."""
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Get the status of an order."""
        pass
