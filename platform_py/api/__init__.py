"""
API endpoints for the trading platform.
"""

from fastapi import APIRouter

from . import intent, strategy, stream

api_router = APIRouter()
api_router.include_router(intent.router)
api_router.include_router(strategy.router)
api_router.include_router(stream.router)
