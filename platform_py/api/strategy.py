"""
API endpoints for strategy management.
"""

import structlog
from uuid import UUID
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

# This is a placeholder for where the strategy manager would live
# In a real system, this would be a more sophisticated component
# that manages the lifecycle of strategy instances.
class StrategyManager:
    def __init__(self):
        self.strategies: Dict[UUID, Any] = {}

    def get_all_strategies(self) -> List[Dict[str, Any]]:
        return [s.health_check() for s in self.strategies.values()]

    def get_strategy(self, strategy_id: UUID) -> Any:
        return self.strategies.get(strategy_id)

# Placeholder instance
strategy_manager = StrategyManager()


router = APIRouter(
    prefix="/strategies",
    tags=["Strategies"],
)

logger = structlog.get_logger()

@router.get("/", response_model=List[Dict[str, Any]])
async def list_strategies():
    """List all running strategies and their health."""
    return await strategy_manager.get_all_strategies()

@router.get("/{strategy_id}/health")
async def get_strategy_health(strategy_id: UUID):
    """Get the health of a specific strategy."""
    strategy = await strategy_manager.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return await strategy.health_check()

@router.post("/{strategy_id}/pause")
async def pause_strategy(strategy_id: UUID):
    """Pause a running strategy."""
    strategy = await strategy_manager.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await strategy.pause()
    return {"status": "paused"}

@router.post("/{strategy_id}/resume")
async def resume_strategy(strategy_id: UUID):
    """Resume a paused strategy."""
    strategy = await strategy_manager.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await strategy.resume()
    return {"status": "resumed"}