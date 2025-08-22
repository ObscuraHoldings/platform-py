"""
Dependency injection and management for core platform components.

This module centralizes the instantiation of core components to avoid circular dependencies
and provide a single source of truth for shared services.
"""

import structlog
from typing import Optional

from .config import config
from .services import services
from .core.intent import IntentManager, MLPrioritizer
from .core.intent.processor import DistributedIntentPipeline

logger = structlog.get_logger()


class CoreComponents:
    """Container for core platform components."""
    
    def __init__(self):
        self.ml_prioritizer: Optional[MLPrioritizer] = None
        self.intent_manager: Optional[IntentManager] = None
        self.intent_pipeline: Optional[DistributedIntentPipeline] = None
        self._is_initialized = False
    
    async def initialize(self) -> None:
        """Initialize and wire up all core components."""
        if self._is_initialized:
            return
            
        logger.info("Initializing core components")
        
        # Initialize ML Prioritizer
        if config.ml.enable_onnx_optimization:
            self.ml_prioritizer = MLPrioritizer(
                model_path=config.ml.model_cache_dir + "/intent_prioritizer.onnx",
                gpu_enabled=config.ray.num_gpus > 0
            )
            await self.ml_prioritizer.initialize()
        
        # Initialize Intent Manager
        if services.db_pool and services.event_stream:
            self.intent_manager = IntentManager(
                db_pool=services.db_pool,
                event_stream=services.event_stream,
                ml_prioritizer=self.ml_prioritizer
            )
            await self.intent_manager.initialize()
        else:
            raise RuntimeError("Database and EventStream must be initialized before IntentManager")
        
        # Initialize Distributed Intent Pipeline
        self.intent_pipeline = DistributedIntentPipeline(
            num_processors=config.ray.num_cpus or 4
        )
        await self.intent_pipeline.initialize_processors()
        
        self._is_initialized = True
        logger.info("Core components initialized successfully")
    
    async def shutdown(self) -> None:
        """Shut down all core components."""
        logger.info("Shutting down core components")
        if self.intent_manager:
            await self.intent_manager.shutdown()
        if self.intent_pipeline:
            await self.intent_pipeline.shutdown()
        self._is_initialized = False
        logger.info("Core components shut down")


# Global components container
components = CoreComponents()