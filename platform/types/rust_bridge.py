"""
Typed models for Rust bridge IO validation.
"""

from typing import List, Optional, Literal, Tuple
from pydantic import BaseModel, Field, validator


class OptimizeRouteParams(BaseModel):
    token_in: str = Field(..., description="Input token address or symbol")
    token_out: str = Field(..., description="Output token address or symbol")
    amount_in: int = Field(..., ge=0, description="Input amount as integer (raw units)")


class OptimizeRouteResult(BaseModel):
    path: List[str] = Field(..., description="Token path as addresses")
    output_amount: int = Field(..., ge=0, description="Estimated output amount (raw units)")


class AggregateOrderBookEntry(BaseModel):
    side: Literal["bid", "ask"]
    price: int = Field(..., ge=0)
    size: int = Field(..., ge=0)


class AggregateOrderBooksOutput(BaseModel):
    bids: List[Tuple[int, int]]
    asks: List[Tuple[int, int]]


class DecodedTransaction(BaseModel):
    from_: Optional[str] = Field(None, alias="from")
    to: Optional[str] = None
    nonce: Optional[int] = None
    gas: Optional[int] = None
    gas_price: Optional[int] = Field(None, alias="gas_price")
    value: Optional[int] = None
    input: Optional[str] = None
    hash: Optional[str] = None

    @validator("input")
    def ensure_hex_prefix(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith("0x"):
            return f"0x{v}"
        return v

