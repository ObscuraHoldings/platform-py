"""
Uniswap V3 venue adapter.
"""

from typing import List, Dict, Any, Optional
from decimal import Decimal

from ...types import Asset, TradingPair, Price, OrderBook, Chain, Venue
from .adapter import VenueAdapter

# Mock for a web3 provider that returns somewhat realistic data
class MockWeb3Provider:
    """
    A mock provider that returns semi-realistic data for a WETH/USDC pool
    without making actual web3 calls.
    """
    # Corresponds to a WETH price of ~$3000 with 6 decimals for USDC and 18 for WETH
    # sqrt(3000 * 10**6 / 10**18) * 2**96 ≈ 4295128739 (already scaled by 2**96)
    SQRT_PRICE_X96 = 4295128739

    async def get_pool_data(self, pool_address: str) -> Dict[str, Any]:
        # In a real implementation, this would fetch data from the blockchain
        return {
            "sqrtPriceX96": self.SQRT_PRICE_X96,
            "liquidity": 1000 * 10**18, # 1000 WETH liquidity
            "tick": 200000 # Example tick
        }

class UniswapV3Adapter(VenueAdapter):
    """Uniswap V3 adapter for multiple chains."""
    
    def __init__(self):
        self.web3_providers = {chain.value: MockWeb3Provider() for chain in self.get_supported_chains()}
    
    async def get_name(self) -> str:
        return "Uniswap V3"

    def get_supported_chains(self) -> List[Chain]:
        return [Chain.ETHEREUM, Chain.ARBITRUM, Chain.BASE]

    async def get_trading_pairs(self, chain_id: int) -> List[TradingPair]:
        # In a real implementation, this would be fetched from the Uniswap subgraph or a database
        return [
            TradingPair(
                base=Asset(symbol="WETH", address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", decimals=18, chain_id=chain_id), 
                quote=Asset(symbol="USDC", address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", decimals=6, chain_id=chain_id),
                venue=Venue.UNISWAP_V3,
                pool_address="0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640" # WETH/USDC 0.05% pool
            )
        ]

    async def get_price(self, pair: TradingPair) -> Price:
        provider = self.web3_providers.get(pair.base.chain_id)
        if not provider or not pair.pool_address:
            raise ValueError(f"Unsupported chain ({pair.base.chain_id}) or missing pool address for {pair.symbol}")

        pool_data = await provider.get_pool_data(pair.pool_address)
        
        # Formula for Uniswap V3 price from sqrtPriceX96
        # price = (sqrtPriceX96 / 2**96)**2 * (10**base_decimals / 10**quote_decimals)
        sqrt_price = Decimal(str(pool_data['sqrtPriceX96']))
        q96 = Decimal(2) ** 96
        price_ratio = (sqrt_price / q96) ** 2
        
        # Adjust for decimals to get human-readable price (use Decimal to avoid float artifacts)
        decimal_adj = (Decimal(10) ** (pair.base.decimals - pair.quote.decimals))
        price_val = price_ratio * decimal_adj
        
        return Price(pair=pair, price=price_val, source=await self.get_name())

    async def get_order_book(self, pair: TradingPair, depth: int = 20) -> OrderBook:
        # Uniswap V3 doesn't have a traditional order book, but one can be constructed from the liquidity distribution
        # This is a simplified placeholder
        price = await self.get_price(pair)
        one = Decimal("1")
        tick = Decimal("0.0001")
        # Build levels around mid
        bids_list = [(price.price * (one - tick * Decimal(i)), Decimal("1")) for i in range(1, depth + 1)]
        asks_list = [(price.price * (one + tick * Decimal(i)), Decimal("1")) for i in range(1, depth + 1)]

        # Enforce best_ask > best_bid strictly (avoid Decimal rounding edge cases)
        best_bid_price = max(p for p, _ in bids_list)
        best_ask_price = min(p for p, _ in asks_list)
        if best_ask_price <= best_bid_price:
            # Nudge the lowest ask one extra tick above best bid
            asks_list[0] = (best_bid_price * (one + tick), asks_list[0][1])
            # Resort asks to keep ascending order
            asks_list.sort(key=lambda x: x[0])

        return OrderBook(
            pair=pair,
            bids=bids_list,
            asks=asks_list,
        )

    async def submit_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        # This would involve creating and sending a transaction
        return {"order_id": "0x123...", "status": "submitted"}

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        # This would involve checking the status of a transaction
        return {"order_id": order_id, "status": "filled"}
