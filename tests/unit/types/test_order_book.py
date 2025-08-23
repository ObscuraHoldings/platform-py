from decimal import Decimal

from platform_py.types import TradingPair, Venue, OrderBook, WETH_ETHEREUM, USDC_ETHEREUM


def test_order_book_helpers():
    pair = TradingPair(base=WETH_ETHEREUM, quote=USDC_ETHEREUM, venue=Venue.UNISWAP_V3)
    ob = OrderBook(
        pair=pair,
        bids=[(Decimal("1000"), Decimal("1")), (Decimal("1001"), Decimal("2"))],
        asks=[(Decimal("1002"), Decimal("3")), (Decimal("1003"), Decimal("4"))],
    )

    assert ob.best_bid == Decimal("1001")
    assert ob.best_ask == Decimal("1002")
    assert ob.spread == Decimal("1")
    assert ob.mid_price == Decimal("1001.5")

    # Depth sorting and truncation
    bid_depth = ob.get_depth("bid", price_levels=1)
    ask_depth = ob.get_depth("ask", price_levels=1)
    assert bid_depth == [(Decimal("1001"), Decimal("2"))]
    assert ask_depth == [(Decimal("1002"), Decimal("3"))]
