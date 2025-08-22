"""
Event envelope and ULID utilities for topic-based messaging and persistence.

This module defines a minimal, schema-first event envelope used across services.
It coexists with the richer domain Event types; producers should publish envelopes,
and the StateCoordinator is the single writer to persistence and read models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_base32(data: bytes) -> str:
    """Encode bytes to Crockford's Base32 without padding."""
    bits = 0
    value = 0
    out = []
    for b in data:
        value = (value << 8) | b
        bits += 8
        while bits >= 5:
            out.append(_CROCKFORD32[(value >> (bits - 5)) & 0x1F])
            bits -= 5
    if bits:
        out.append(_CROCKFORD32[(value << (5 - bits)) & 0x1F])
    return "".join(out)


def ulid(ts: Optional[datetime] = None) -> str:
    """Generate a lexicographically sortable ULID string.

    ULID = 48-bit timestamp (ms since epoch) + 80 bits of randomness.
    """
    import os

    now = ts or datetime.now(timezone.utc)
    ms = int(now.timestamp() * 1000)
    time_bytes = ms.to_bytes(6, byteorder="big")  # 48 bits
    rand_bytes = os.urandom(10)  # 80 bits
    return _encode_base32(time_bytes + rand_bytes)[:26]


class EventEnvelope(BaseModel):
    """Topic-based event envelope for NATS + persistence.

    - eventId: ULID
    - timestamp: ISO8601 UTC
    - topic: dot-separated subject (e.g., intent.accepted)
    - correlationId: groups related events (e.g., intent:<ULID>)
    - causationId: prior eventId (if any)
    - payload: domain-specific fields
    - version: schema version for payload
    - sequence: optional per-correlation monotonic sequence number
    """

    eventId: str = Field(..., description="ULID event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    topic: str
    correlationId: str
    causationId: Optional[str] = None
    payload: Dict[str, Any]
    version: int = 1
    sequence: Optional[int] = None


def envelope(
    *,
    topic: str,
    payload: Dict[str, Any],
    correlation_id: str,
    causation_id: Optional[str] = None,
    version: int = 1,
    sequence: Optional[int] = None,
) -> EventEnvelope:
    return EventEnvelope(
        eventId=ulid(),
        topic=topic,
        payload=payload,
        correlationId=correlation_id,
        causationId=causation_id,
        version=version,
        sequence=sequence,
    )

