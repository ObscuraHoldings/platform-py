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
from .risk import RiskEngine
from .core.intent.processor import DistributedIntentPipeline
from .core.execution import VenueManager, ExecutionPlanner
from .core.execution.orchestrator import ExecutionOrchestrator
from .state import StateCoordinator

logger = structlog.get_logger()


class CoreComponents:
    """Container for core platform components."""
    
    def __init__(self):
        self.ml_prioritizer: Optional[MLPrioritizer] = None
        self.intent_manager: Optional[IntentManager] = None
        self.intent_pipeline: Optional[DistributedIntentPipeline] = None
        self.venue_manager: Optional[VenueManager] = None
        self.execution_planner: Optional[ExecutionPlanner] = None
        self.execution_orchestrator: Optional[ExecutionOrchestrator] = None
        self.state_coordinator: Optional[StateCoordinator] = None
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
            risk_engine = RiskEngine()
            self.intent_manager = IntentManager(
                db_pool=services.db_pool,
                event_stream=services.event_stream,
                ml_prioritizer=self.ml_prioritizer,
                risk_engine=risk_engine,
                enable_legacy_queue=config.enable_legacy_intent_queue,
            )
            await self.intent_manager.initialize()
        else:
            raise RuntimeError("Database and EventStream must be initialized before IntentManager")
        
        # Initialize Distributed Intent Pipeline (legacy/optional)
        try:
            self.intent_pipeline = DistributedIntentPipeline(
                num_processors=config.ray.num_cpus or 4
            )
            await self.intent_pipeline.initialize_processors()
        except Exception as e:
            logger.warning("Intent pipeline not initialized (distributed features disabled)", error=str(e))
            self.intent_pipeline = None
        
        # Initialize VenueManager and ExecutionPlanner subscriber
        self.venue_manager = VenueManager()
        self.execution_planner = ExecutionPlanner(self.venue_manager, services.event_stream)
        await self.execution_planner.start()

        # Initialize StateCoordinator and subscribe to core subjects
        self.state_coordinator = StateCoordinator(db_pool=services.db_pool, redis_client=services.redis_client)
        await self._subscribe_state_coordinator(services.event_stream)

        # Initialize Orchestrator subscriber
        self.execution_orchestrator = ExecutionOrchestrator(self.venue_manager, services.event_stream)
        await self.execution_orchestrator.start()

    async def _subscribe_state_coordinator(self, event_stream):
        async def handler(evt: dict):
            try:
                from .types.envelope import EventEnvelope
                env = EventEnvelope(**evt)
            except Exception:
                return
            await self.state_coordinator.apply_event(env)

        for subject in ["intent.*", "risk.*", "plan.*", "exec.*"]:
            await event_stream.subscribe(subject, handler)
        
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
