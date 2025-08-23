"""
Base strategy class with ML support and async lifecycle management.
"""

import asyncio
import structlog
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set, Callable
from uuid import UUID, uuid4
from datetime import datetime, timezone
from pathlib import Path

from ..types import Intent, Asset, AssetAmount, EventMetadata, create_strategy_signal_event

logger = structlog.get_logger()


@dataclass
class StrategyManifest:
    """Strategy metadata and resource requirements."""
    
    name: str
    version: str
    description: str
    
    # ML model requirements
    ml_models: List[str] = field(default_factory=list)
    model_cache_dir: Optional[str] = None
    
    # Resource requirements
    gpu_memory_mb: Optional[int] = None
    cpu_cores: Optional[int] = None
    max_memory_mb: Optional[int] = None
    
    # Dependencies
    dependencies: List[str] = field(default_factory=list)
    
    # Strategy configuration
    config_schema: Dict[str, Any] = field(default_factory=dict)
    default_config: Dict[str, Any] = field(default_factory=dict)
    
    # Risk parameters
    max_position_size: Optional[float] = None
    max_daily_loss: Optional[float] = None
    max_drawdown: Optional[float] = None


class MLModelManager:
    """Manages ML models for strategy with GPU resource allocation."""
    
    def __init__(self, manifest: StrategyManifest):
        self.manifest = manifest
        self._models: Dict[str, Any] = {}
        self._gpu_context: Optional[Any] = None
        self._model_cache_dir = Path(manifest.model_cache_dir or "./models")
        self._model_cache_dir.mkdir(exist_ok=True)
    
    async def initialize(self) -> None:
        """Initialize ML models and GPU resources."""
        logger.info("Initializing ML models", model_count=len(self.manifest.ml_models))
        
        # Allocate GPU resources if needed
        if self.manifest.gpu_memory_mb:
            await self._allocate_gpu_resources()
        
        # Load ML models
        for model_path in self.manifest.ml_models:
            await self._load_model(model_path)
        
        logger.info("ML models initialized successfully")
    
    async def shutdown(self) -> None:
        """Clean shutdown with resource cleanup."""
        logger.info("Shutting down ML models")
        
        # Cleanup models
        for model_name in list(self._models.keys()):
            await self._unload_model(model_name)
        
        # Free GPU resources
        if self._gpu_context:
            await self._cleanup_gpu_resources()
        
        logger.info("ML models shut down successfully")
    
    async def _allocate_gpu_resources(self) -> None:
        """Allocate GPU resources for ML models."""
        try:
            # Try importing ONNX Runtime with GPU support
            import onnxruntime as ort
            
            # Check for CUDA provider
            providers = ort.get_available_providers()
            if 'CUDAExecutionProvider' in providers:
                # Configure GPU memory limit
                cuda_options = {
                    'device_id': 0,
                    'arena_extend_strategy': 'kNextPowerOfTwo',
                    'gpu_mem_limit': self.manifest.gpu_memory_mb * 1024 * 1024,
                    'cudnn_conv_algo_search': 'EXHAUSTIVE',
                    'do_copy_in_default_stream': True,
                }
                self._gpu_context = ('CUDAExecutionProvider', cuda_options)
                logger.info("GPU resources allocated", memory_mb=self.manifest.gpu_memory_mb)
            else:
                logger.warning("CUDA not available, falling back to CPU")
                self._gpu_context = 'CPUExecutionProvider'
        
        except ImportError:
            logger.warning("ONNX Runtime not available, ML models disabled")
            self._gpu_context = None
    
    async def _cleanup_gpu_resources(self) -> None:
        """Cleanup GPU resources."""
        if self._gpu_context:
            # GPU resources are automatically freed when models are unloaded
            self._gpu_context = None
            logger.info("GPU resources cleaned up")
    
    async def _load_model(self, model_path: str) -> None:
        """Load an ML model."""
        try:
            import onnxruntime as ort
            
            full_path = self._model_cache_dir / model_path
            if not full_path.exists():
                logger.error("Model file not found", path=str(full_path))
                return
            
            # Create inference session
            providers = [self._gpu_context] if self._gpu_context else ['CPUExecutionProvider']
            session = ort.InferenceSession(str(full_path), providers=providers)
            
            self._models[model_path] = session
            logger.info("Model loaded successfully", path=model_path)
            
        except ImportError:
            logger.warning("ONNX Runtime not available", model=model_path)
        except Exception as e:
            logger.error("Failed to load model", model=model_path, error=str(e))
    
    async def _unload_model(self, model_name: str) -> None:
        """Unload an ML model."""
        if model_name in self._models:
            del self._models[model_name]
            logger.info("Model unloaded", model=model_name)
    
    async def predict(self, model_path: str, features: Dict[str, Any]) -> Dict[str, float]:
        """Run inference on a model."""
        if model_path not in self._models:
            logger.error("Model not loaded", model=model_path)
            return {}
        
        try:
            session = self._models[model_path]
            
            # Prepare input
            input_name = session.get_inputs()[0].name
            input_data = self._prepare_input(features, session)
            
            # Run inference
            start_time = datetime.now()
            result = session.run(None, {input_name: input_data})
            inference_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Process output
            output = self._process_output(result, session)
            
            logger.debug("Model inference completed", 
                        model=model_path, 
                        inference_time_ms=inference_time)
            
            return output
            
        except Exception as e:
            logger.error("Model inference failed", model=model_path, error=str(e))
            return {}
    
    def _prepare_input(self, features: Dict[str, Any], session) -> Any:
        """Prepare input for ML model."""
        import numpy as np
        
        # Simple feature vector preparation
        # In practice, this would be more sophisticated
        feature_values = list(features.values())
        return np.array([feature_values], dtype=np.float32)
    
    def _process_output(self, result: List[Any], session) -> Dict[str, float]:
        """Process ML model output."""
        output = {}
        
        # Map outputs to named results
        output_names = [output.name for output in session.get_outputs()]
        for i, name in enumerate(output_names):
            if i < len(result):
                value = float(result[i][0]) if hasattr(result[i], '__getitem__') else float(result[i])
                output[name] = value
        
        return output
    
    def get_loaded_models(self) -> List[str]:
        """Get list of loaded model paths."""
        return list(self._models.keys())


class StrategyState:
    """Manages strategy state and position tracking."""
    
    def __init__(self):
        self.positions: Dict[Asset, AssetAmount] = {}
        self.pending_intents: Set[UUID] = set()
        self.active_orders: Set[UUID] = set()
        self.performance_metrics: Dict[str, float] = {}
        self.last_update: datetime = datetime.now(timezone.utc)
    
    def update_position(self, asset: Asset, amount: AssetAmount) -> None:
        """Update position for an asset."""
        self.positions[asset] = amount
        self.last_update = datetime.now(timezone.utc)
    
    def get_position(self, asset: Asset) -> Optional[AssetAmount]:
        """Get current position for an asset."""
        return self.positions.get(asset)
    
    def add_pending_intent(self, intent_id: UUID) -> None:
        """Track a pending intent."""
        self.pending_intents.add(intent_id)
    
    def remove_pending_intent(self, intent_id: UUID) -> None:
        """Remove a pending intent."""
        self.pending_intents.discard(intent_id)
    
    def get_total_value(self, price_oracle: Callable[[Asset], float]) -> float:
        """Calculate total portfolio value."""
        total_value = 0.0
        for asset, amount in self.positions.items():
            try:
                price = price_oracle(asset)
                total_value += float(amount.amount) * price
            except Exception as e:
                logger.warning("Failed to get price for asset", asset=asset.symbol, error=str(e))
        
        return total_value


class BaseStrategy(ABC):
    """Abstract base strategy class with async lifecycle and ML support."""
    
    def __init__(self, strategy_id: UUID, manifest: StrategyManifest, config: Dict[str, Any]):
        self.strategy_id = strategy_id
        self.manifest = manifest
        self.config = {**manifest.default_config, **config}
        
        # State management
        self.state = StrategyState()
        self._running = False
        self._paused = False
        
        # ML support
        self.ml_manager = MLModelManager(manifest)
        
        # Event handling
        self._event_handlers: Dict[str, List[Callable]] = {}
        
        # Performance tracking
        self._start_time: Optional[datetime] = None
        self._total_intents_generated = 0
        self._successful_intents = 0
        
        logger.info("Strategy initialized", 
                   strategy_id=str(strategy_id), 
                   name=manifest.name,
                   version=manifest.version)
    
    async def initialize(self) -> None:
        """Initialize strategy resources and ML models."""
        logger.info("Initializing strategy", strategy_id=str(self.strategy_id))
        
        # Initialize ML models
        await self.ml_manager.initialize()
        
        # Call strategy-specific initialization
        await self._on_initialize()
        
        self._running = True
        self._start_time = datetime.now(timezone.utc)
        
        logger.info("Strategy initialized successfully", strategy_id=str(self.strategy_id))
    
    async def shutdown(self) -> None:
        """Clean shutdown of strategy."""
        logger.info("Shutting down strategy", strategy_id=str(self.strategy_id))
        
        self._running = False
        
        # Call strategy-specific cleanup
        await self._on_shutdown()
        
        # Cleanup ML resources
        await self.ml_manager.shutdown()
        
        # Log final performance metrics
        self._log_final_metrics()
        
        logger.info("Strategy shut down successfully", strategy_id=str(self.strategy_id))
    
    async def pause(self) -> None:
        """Pause strategy execution."""
        if self._running:
            self._paused = True
            await self._on_pause()
            logger.info("Strategy paused", strategy_id=str(self.strategy_id))
    
    async def resume(self) -> None:
        """Resume strategy execution."""
        if self._running and self._paused:
            self._paused = False
            await self._on_resume()
            logger.info("Strategy resumed", strategy_id=str(self.strategy_id))
    
    @property
    def is_running(self) -> bool:
        """Check if strategy is running."""
        return self._running and not self._paused
    
    @property
    def uptime(self) -> Optional[float]:
        """Get strategy uptime in seconds."""
        if self._start_time:
            return (datetime.now(timezone.utc) - self._start_time).total_seconds()
        return None
    
    # Abstract methods that strategies must implement
    @abstractmethod
    async def generate_intents(self, market_data: Dict[str, Any]) -> List[Intent]:
        """Generate trading intents based on market data."""
        pass
    
    @abstractmethod
    async def update_ml_models(self, new_data: Dict[str, Any]) -> None:
        """Update ML models with new data (online learning)."""
        pass
    
    @abstractmethod
    async def evaluate_market_conditions(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """Evaluate current market conditions and return confidence scores."""
        pass
    
    # Optional lifecycle hooks
    async def _on_initialize(self) -> None:
        """Strategy-specific initialization logic."""
        pass
    
    async def _on_shutdown(self) -> None:
        """Strategy-specific shutdown logic."""
        pass
    
    async def _on_pause(self) -> None:
        """Strategy-specific pause logic."""
        pass
    
    async def _on_resume(self) -> None:
        """Strategy-specific resume logic."""
        pass
    
    # Event handling
    def add_event_handler(self, event_type: str, handler: Callable) -> None:
        """Add an event handler for a specific event type."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Handle an incoming event."""
        if event_type in self._event_handlers:
            for handler in self._event_handlers[event_type]:
                try:
                    await handler(event_data)
                except Exception as e:
                    logger.error("Event handler failed", 
                               event_type=event_type, 
                               handler=handler.__name__, 
                               error=str(e))
    
    # Intent tracking
    async def track_intent_generated(self, intent: Intent) -> None:
        """Track when an intent is generated."""
        self._total_intents_generated += 1
        self.state.add_pending_intent(intent.id)
        
        logger.info("Intent generated", 
                   strategy_id=str(self.strategy_id),
                   intent_id=str(intent.id),
                   intent_type=intent.type.value)
    
    async def track_intent_completed(self, intent_id: UUID, success: bool) -> None:
        """Track when an intent is completed."""
        self.state.remove_pending_intent(intent_id)
        
        if success:
            self._successful_intents += 1
        
        logger.info("Intent completed", 
                   strategy_id=str(self.strategy_id),
                   intent_id=str(intent_id),
                   success=success)
    
    # Performance metrics
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        success_rate = (self._successful_intents / self._total_intents_generated 
                       if self._total_intents_generated > 0 else 0.0)
        
        return {
            "total_intents_generated": self._total_intents_generated,
            "successful_intents": self._successful_intents,
            "success_rate": success_rate,
            "pending_intents": len(self.state.pending_intents),
            "uptime_seconds": self.uptime,
            "is_running": self.is_running,
            "loaded_models": self.ml_manager.get_loaded_models(),
            **self.state.performance_metrics
        }
    
    def _log_final_metrics(self) -> None:
        """Log final performance metrics on shutdown."""
        metrics = self.get_performance_metrics()
        logger.info("Final strategy metrics", 
                   strategy_id=str(self.strategy_id),
                   **metrics)
    
    # ML convenience methods
    async def predict_with_model(self, model_path: str, features: Dict[str, Any]) -> Dict[str, float]:
        """Run prediction with a specific ML model."""
        return await self.ml_manager.predict(model_path, features)
    
    async def get_ml_confidence(self, features: Dict[str, Any]) -> float:
        """Get ML confidence score for current market conditions."""
        # Default implementation - strategies can override
        predictions = {}
        for model_path in self.manifest.ml_models:
            result = await self.predict_with_model(model_path, features)
            predictions.update(result)
        
        # Simple average confidence
        if predictions:
            confidences = [v for k, v in predictions.items() if 'confidence' in k.lower()]
            return sum(confidences) / len(confidences) if confidences else 0.5
        
        return 0.5  # Neutral confidence
    
    # Utility methods
    def validate_config(self) -> List[str]:
        """Validate strategy configuration."""
        errors = []
        
        # Basic validation against schema
        schema = self.manifest.config_schema
        for key, requirements in schema.items():
            if requirements.get('required', False) and key not in self.config:
                errors.append(f"Required config key missing: {key}")
            
            if key in self.config:
                value = self.config[key]
                value_type = requirements.get('type')
                if value_type and not isinstance(value, value_type):
                    errors.append(f"Config key {key} has wrong type: expected {value_type}, got {type(value)}")
        
        return errors
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform strategy health check."""
        return {
            "strategy_id": str(self.strategy_id),
            "name": self.manifest.name,
            "version": self.manifest.version,
            "is_running": self.is_running,
            "uptime_seconds": self.uptime,
            "ml_models_loaded": len(self.ml_manager.get_loaded_models()),
            "pending_intents": len(self.state.pending_intents),
            "config_valid": len(self.validate_config()) == 0,
            "last_state_update": self.state.last_update.isoformat()
        }