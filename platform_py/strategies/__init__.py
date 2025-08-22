"""
Strategy framework for the trading platform.
"""

from .base import BaseStrategy, StrategyManifest, StrategyState, MLModelManager

__all__ = [
    "BaseStrategy",
    "StrategyManifest",
    "StrategyState",
    "MLModelManager"
]