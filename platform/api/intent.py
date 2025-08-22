"""
API endpoints for intent management.
"""

import structlog
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List

from ..types import Intent, IntentReceipt, IntentUpdate, EventMetadata
from ..dependencies import components

router = APIRouter(
    prefix="/intents",
    tags=["Intents"],
)

logger = structlog.get_logger()


@router.post("/submit", response_model=IntentReceipt)
async def submit_intent(intent: Intent, background_tasks: BackgroundTasks):
    """Submit a new intent for execution."""
    if not components.intent_manager:
        raise HTTPException(status_code=503, detail="IntentManager not available")
    
    # Create event metadata (this would be populated from auth, etc.)
    metadata = EventMetadata(
        source_service="api",
        source_version="0.1.0",
        correlation_id=UUID(),
    )
    
    receipt = await components.intent_manager.submit_intent(intent, metadata)
    
    if receipt.status == IntentStatus.FAILED:
        raise HTTPException(status_code=400, detail=f"Intent submission failed: {receipt.warnings}")
    
    # If the pipeline is available, start processing in the background
    if components.intent_pipeline:
        async def process():
            processed_intents = await components.intent_pipeline.process_intents([intent])
            logger.info("Background intent processing complete", count=len(processed_intents))
        background_tasks.add_task(process)
    
    return receipt


@router.get("/{intent_id}/status", response_model=IntentUpdate)
async def get_intent_status(intent_id: UUID):
    """Get the current status of an intent."""
    if not components.intent_manager:
        raise HTTPException(status_code=503, detail="IntentManager not available")
    
    status = await components.intent_manager.get_intent_status(intent_id)
    if not status:
        raise HTTPException(status_code=404, detail="Intent not found")
        
    return IntentUpdate(intent_id=intent_id, new_status=status['new_status'], old_status=status['new_status']) # old_status is a simplification

@router.get("/{intent_id}/history")
async def get_intent_history(intent_id: UUID):
    """Get the event history for an intent."""
    if not components.intent_manager:
        raise HTTPException(status_code=503, detail="IntentManager not available")
        
    history = await components.intent_manager.get_intent_history(intent_id)
    if not history:
        raise HTTPException(status_code=404, detail="Intent not found")
        
    return [event.dict() for event in history]