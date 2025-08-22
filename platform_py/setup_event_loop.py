"""Configure the event loop for the application.

This module provides a small helper to opt-in to `uvloop` when
available. It is intentionally minimal and non-fatal: failures to
import or install `uvloop` are logged but do not stop startup.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def setup_event_loop() -> None:
    """Install uvloop's event loop policy if available.

    This is safe to call multiple times; if `uvloop` is not present
    we quietly continue with the default asyncio loop.
    """
    try:
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("uvloop enabled for asyncio event loop")
    except Exception as exc:  # pragma: no cover - environmental
        logger.debug("uvloop unavailable, using default asyncio loop", exc_info=exc)

