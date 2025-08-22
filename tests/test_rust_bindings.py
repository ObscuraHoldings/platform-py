import os
import sys
import pytest
import importlib.util

# Import rust_bindings from the canonical package
from platform_py.rust_bindings import decode_transaction, optimize_route, aggregate_order_books


class DummyTx(dict):
    # Minimal dummy transaction for fallback decode
    pass


def test_decode_transaction_fallback_with_dict():
    # Provide a dummy dict mimicking a web3 transaction
    tx = {'from': '0xabc', 'to': '0xdef', 'nonce': 1, 'gas': 21000, 'gas_price': 50, 'value': 1000, 'input': 'deadbeef', 'hash': '0x123'}
    result = decode_transaction(tx)
    # Expected keys: 'from', 'to', 'nonce', 'gas', 'gas_price', 'value', 'input', 'hash'
    assert isinstance(result, dict)
    assert 'from' in result


def test_decode_transaction_with_hex_string_fallback():
    # When provided non-string or invalid hex, fallback should process it
    tx = DummyTx({'from': '0xabc', 'to': '0xdef'})
    result = decode_transaction(tx)
    assert isinstance(result, dict)
    # Even if minimal, should include keys from fallback
    assert result.get('from') == '0xabc'


def test_optimize_route_fallback():
    params = {"token_in": "ETH", "token_out": "DAI", "amount_in": 1000}
    result = optimize_route(params)
    # Should return a dict with 'path' and 'output_amount'
    assert isinstance(result, dict)
    assert 'path' in result
    assert 'output_amount' in result


def test_aggregate_order_books_fallback():
    # Provide a list of simple order entries
    books = [
        {"side": "bid", "price": 1000, "size": 10},
        {"side": "ask", "price": 1010, "size": 5}
    ]
    result = aggregate_order_books(books)
    # Expect result to be a dict with keys 'bids' and 'asks'
    assert isinstance(result, dict)
    assert 'bids' in result
    assert 'asks' in result
