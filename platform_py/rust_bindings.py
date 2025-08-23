"""
Thin adapter to the Rust extension `platform_rust` with safe fallbacks.

This module attempts to import the compiled PyO3 extension named
`platform_rust`. If the import succeeds, wrapper functions delegate to the
Rust implementations. If not, the module falls back to the existing Python
mock implementations and logs a clear warning.
"""

import structlog
from typing import Dict, Any, List
from .types.rust_bridge import (
    OptimizeRouteParams,
    OptimizeRouteResult,
    AggregateOrderBookEntry,
    AggregateOrderBooksOutput,
    DecodedTransaction,
)

logger = structlog.get_logger()

# Try to import the compiled Rust extension and initialize its runtime
_platform_rust = None
try:
    import platform_rust as _platform_rust  # type: ignore
    # Initialize the Rust async runtime and tracing once when available
    try:
        if hasattr(_platform_rust, "initialize_rust_runtime"):
            _platform_rust.initialize_rust_runtime()
    except Exception as init_err:
        logger.error("Failed to initialize Rust runtime", error=str(init_err))
    logger.info("Loaded native extension: platform_rust")
except Exception as e:
    logger.warning("platform_rust extension unavailable, using Python fallbacks", error=str(e))
    _platform_rust = None

# Fallback implementations (original mocks)
def _fallback_decode_transaction(tx: Any) -> Dict[str, Any]:
    logger.info("FALLBACK rust_bindings.decode_transaction called", tx_hash=getattr(tx, 'hash', None))
    result = {
        "from": tx.get("from") if isinstance(tx, dict) else None,
        "to": tx.get("to") if isinstance(tx, dict) else None,
        "value": tx.get("value") if isinstance(tx, dict) else None,
        "gas": tx.get("gas") if isinstance(tx, dict) else None,
        "gasPrice": tx.get("gasPrice") if isinstance(tx, dict) else None,
        "nonce": tx.get("nonce") if isinstance(tx, dict) else None,
        "input": (tx.get("input")[:32] + "...") if isinstance(tx, dict) and tx.get("input") else None,
    }
    # Normalize to DecodedTransaction model shape (aliases handle key names)
    try:
        return DecodedTransaction.model_validate(result).model_dump(by_alias=True)
    except Exception:
        return result


def _fallback_optimize_route(params: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("FALLBACK rust_bindings.optimize_route called", params=params)
    parsed = OptimizeRouteParams(**params)
    result = {
        "path": [p for p in (parsed.token_in, parsed.token_out) if p is not None],
        "output_amount": int(parsed.amount_in * 99 // 100),
    }
    return OptimizeRouteResult(**result).model_dump()


def _fallback_simulate_transaction(step: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("FALLBACK rust_bindings.simulate_transaction called", step=step)
    return {"success": True, "gas_used": 150000, "output": "0x..."}


def _fallback_aggregate_order_books(books: List[Any]) -> Any:
    logger.info("FALLBACK rust_bindings.aggregate_order_books called", num_books=len(books))
    # Expect normalized entries: {side: 'bid'|'ask', price: int, size: int}
    bids: List[Any] = []
    asks: List[Any] = []
    for e in books:
        side = e.get("side")
        price = e.get("price")
        size = e.get("size")
        if side == "bid":
            bids.append((price, size))
        elif side == "ask":
            asks.append((price, size))
    return {"bids": bids, "asks": asks}


# Public wrappers that delegate to native extension if present

def decode_transaction(tx: Any) -> Dict[str, Any]:
    """Decode a transaction.

    Preferred input is a hex-encoded RLP transaction string. If a non-string
    object (e.g., web3.py TxData) is provided, fall back to the Python decoder
    which extracts common fields.
    """
    if isinstance(tx, str) and _platform_rust is not None and hasattr(_platform_rust, "decode_transaction"):
        try:
            decoded = _platform_rust.decode_transaction(tx)
            return DecodedTransaction.model_validate(decoded).model_dump(by_alias=True)
        except Exception as e:
            logger.error("Native decode_transaction failed, falling back", error=str(e))
            # fall through to fallback below
    return _fallback_decode_transaction(tx)


def optimize_route(params: Dict[str, Any]) -> Dict[str, Any]:
    parsed = OptimizeRouteParams(**params)
    if _platform_rust is not None and hasattr(_platform_rust, "ExecutionEngine"):
        try:
            # If the native module exposes an ExecutionEngine class, instantiate and call optimize_route
            engine = _platform_rust.ExecutionEngine()
            result = engine.optimize_route(parsed.model_dump())
            return OptimizeRouteResult.model_validate(result).model_dump()
        except Exception as e:
            logger.error("Native optimize_route failed, falling back", error=str(e))
            return _fallback_optimize_route(parsed.model_dump())
    return _fallback_optimize_route(parsed.model_dump())


def simulate_transaction(step: Dict[str, Any]) -> Dict[str, Any]:
    if _platform_rust is not None and hasattr(_platform_rust, "ExecutionEngine"):
        try:
            engine = _platform_rust.ExecutionEngine()
            return engine.simulate_transaction(step)
        except Exception as e:
            logger.error("Native simulate_transaction failed, falling back", error=str(e))
            return _fallback_simulate_transaction(step)
    return _fallback_simulate_transaction(step)


def aggregate_order_books(books: List[Any]) -> Any:
    # Validate/normalize entries
    entries = [AggregateOrderBookEntry.model_validate(b).model_dump() for b in books]
    if _platform_rust is not None and hasattr(_platform_rust, "aggregate_order_books"):
        try:
            result = _platform_rust.aggregate_order_books(entries)
            return AggregateOrderBooksOutput.model_validate(result).model_dump()
        except Exception as e:
            logger.error("Native aggregate_order_books failed, falling back", error=str(e))
            return _fallback_aggregate_order_books(entries)
    return _fallback_aggregate_order_books(entries)
