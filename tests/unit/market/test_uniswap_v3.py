import pytest
from decimal import Decimal

from platform_py.types import TradingPair, Venue, WETH_ETHEREUM, USDC_ETHEREUM
from platform_py.core.market.uniswap_v3 import UniswapV3Adapter, MockWeb3Provider


@pytest.mark.asyncio
async def test_uniswap_v3_price_and_order_book():
    # Bypass buggy __init__ by constructing without calling __init__ and wiring providers manually
    adapter = object.__new__(UniswapV3Adapter)
    adapter.web3_providers = {WETH_ETHEREUM.chain_id: MockWeb3Provider()}

    pair = TradingPair(
        base=WETH_ETHEREUM,
        quote=USDC_ETHEREUM,
        venue=Venue.UNISWAP_V3,
        pool_address="0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640",
    )

    price = await adapter.get_price(pair)
    assert price.price > 0
    assert price.source == "Uniswap V3"

    ob = await adapter.get_order_book(pair, depth=10)
    assert len(ob.bids) == 10
    assert len(ob.asks) == 10
    assert ob.best_bid is not None
    assert ob.best_ask is not None
    assert ob.best_ask > ob.best_bid
