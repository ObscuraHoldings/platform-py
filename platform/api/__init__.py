"""
API endpoints for the trading platform.
"""

from fastapi import APIRouter

from . import intent, strategy

api_router = APIRouter()
api_router.include_router(intent.router)
api_router.include_router(strategy.router)
