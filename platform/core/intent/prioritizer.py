"""
ML-based intent prioritization.

This module provides an ML model-based intent prioritizer.
"""

import structlog
from typing import Any, Dict, Optional

from ...types import Intent

logger = structlog.get_logger()


class MLPrioritizer:
    """Prioritizes intents using a trained ML model."""
    
    def __init__(self, model_path: str, gpu_enabled: bool = False):
        self.model_path = model_path
        self.gpu_enabled = gpu_enabled
        self.model = None  # Lazy-loaded model
        logger.info("MLPrioritizer initialized", model_path=model_path, gpu_enabled=gpu_enabled)
    
    async def initialize(self) -> None:
        """Load the ML model."""
        try:
            import onnxruntime as ort
            
            providers = ['CUDAExecutionProvider'] if self.gpu_enabled else ['CPUExecutionProvider']
            self.model = ort.InferenceSession(self.model_path, providers=providers)
            logger.info("ML prioritization model loaded successfully")
            
        except ImportError:
            logger.warning("ONNX Runtime not available, ML prioritizer disabled")
            self.model = None
        except Exception as e:
            logger.error("Failed to load ML prioritization model", error=str(e))
            self.model = None
    
    async def calculate_priority(self, intent: Intent) -> int:
        """Calculate priority for an intent using the ML model."""
        if not self.model or not intent.ml_features:
            return intent.priority # Fallback to default priority
        
        try:
            # Prepare features
            features = self._prepare_features(intent.ml_features.dict())
            
            # Run inference
            input_name = self.model.get_inputs()[0].name
            result = self.model.run(None, {input_name: features})
            
            # Process result
            priority_score = float(result[0][0]) # Assuming model outputs a single score
            priority = int(priority_score * 10) # Scale to 1-10
            
            logger.debug("ML priority calculated", intent_id=str(intent.id), priority=priority)
            return max(1, min(10, priority))

        except Exception as e:
            logger.error("ML priority calculation failed", aintent_id=str(intent.id), error=str(e))
            return intent.priority # Fallback to default

    def _prepare_features(self, features: Dict[str, Any]) -> Any:
        """Prepare features for the ONNX model."""
        import numpy as np
        
        # This should match the model's expected input format
        feature_vector = list(features.values())
        return np.array([feature_vector], dtype=np.float32)
