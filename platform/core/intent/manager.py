"""
Async intent management with event sourcing, validation, and ML-based prioritization.
"""

import asyncio
import structlog
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

import asyncpg

from ...types import (
    Intent, IntentStatus, IntentReceipt, IntentUpdate,
    Event, EventMetadata,
    create_intent_submitted_event, create_intent_status_changed_event
)
from ...streaming import EventStream
from .validator import IntentValidator
from .processor import DistributedIntentPipeline

logger = structlog.get_logger()


class IntentManager:
    """Manages intent lifecycle with event sourcing and distributed processing."""
    
    def __init__(self, 
                 db_pool: asyncpg.Pool, 
                 event_stream: EventStream,
                 ml_prioritizer: Optional[MLPrioritizer] = None):
        
        self.db_pool = db_pool
        self.event_stream = event_stream
        self.validator = IntentValidator(db_pool)
        self.ml_prioritizer = ml_prioritizer
        self.pipeline = DistributedIntentPipeline()
        
        self._intent_queue = asyncio.PriorityQueue()
        self._processing_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info("IntentManager initialized", ml_prioritizer_enabled=bool(ml_prioritizer))
    
    async def initialize(self) -> None:
        """Initialize IntentManager and start processing loop."""
        self._running = True
        await self.pipeline.initialize_processors()
        self._processing_task = asyncio.create_task(self._process_intent_queue())
        logger.info("IntentManager processing started")
    
    async def shutdown(self) -> None:
        """Shut down IntentManager gracefully."""
        self._running = False
        if self._processing_task:
            try:
                self._processing_task.cancel()
                await self._processing_task
            except asyncio.CancelledError:
                pass
        await self.pipeline.shutdown()
        logger.info("IntentManager shut down")
    
    async def submit_intent(self, intent: Intent, metadata: EventMetadata) -> IntentReceipt:
        """Submit new intent for validation, prioritization, and execution."""
        logger.info("Submitting new intent", intent_id=str(intent.id))
        
        try:
            # 1. Validate intent
            validation_errors, validation_warnings = await self.validator.validate(intent)
            if validation_errors:
                logger.warning("Intent validation failed", intent_id=str(intent.id), errors=validation_errors)
                intent.update_status(IntentStatus.FAILED, f"Validation failed: {validation_errors}")
                # Optionally, store and publish failed validation event
                return IntentReceipt(
                    intent_id=intent.id,
                    status=IntentStatus.FAILED,
                    warnings=validation_errors
                )
            
            intent.update_status(IntentStatus.VALIDATED)
            
            # 2. Prioritize intent
            if self.ml_prioritizer:
                ml_priority = await self.ml_prioritizer.calculate_priority(intent)
                intent.priority = max(intent.priority, ml_priority)
                logger.info("Intent prioritized with ML", intent_id=str(intent.id), priority=intent.priority)
            
            # 3. Store submission event
            event = create_intent_submitted_event(intent, metadata)
            await self._store_event(event)
            
            # 4. Publish submission event
            await self.event_stream.publish(
                subject=f"intent.submitted.{intent.type.value}",
                event=event.dict()
            )
            
            # 5. Add to processing queue
            await self._intent_queue.put((-intent.priority, intent)) # Use negative for min-heap as priority queue
            
            logger.info("Intent submitted successfully", intent_id=str(intent.id), priority=intent.priority)
            
            return IntentReceipt(
                intent_id=intent.id,
                status=IntentStatus.QUEUED,
                warnings=validation_warnings,
                queue_position=self._intent_queue.qsize()
            )
        
        except Exception as e:
            logger.error("Failed to submit intent", intent_id=str(intent.id), error=str(e), exc_info=True)
            return IntentReceipt(
                intent_id=intent.id,
                status=IntentStatus.FAILED,
                warnings=[f"Internal server error: {str(e)}"]
            )
    
    async def _process_intent_queue(self) -> None:
        """Continuously process intents from the queue."""
        while self._running:
            try:
                priority, intent = await self._intent_queue.get()
                
                logger.info("Processing intent from queue", intent_id=str(intent.id))
                
                # Get current aggregate version before processing
                current_version = await self._get_aggregate_version(intent.id)
                
                # Update status to processing
                intent.update_status(IntentStatus.PROCESSING)
                
                # Create and store status change event
                metadata = EventMetadata(source_service="IntentManager", source_version="1.0.0") # Placeholder
                status_event = create_intent_status_changed_event(
                    intent_id=intent.id, 
                    old_status=IntentStatus.QUEUED, 
                    new_status=IntentStatus.PROCESSING, 
                    metadata=metadata,
                    aggregate_version=current_version + 1
                )
                await self._store_event(status_event)
                
                # Publish status change event
                await self.event_stream.publish(f"intent.status.{intent.id}", status_event.dict())
                
                # Hand off to distributed execution pipeline
                sub_intents = await self.pipeline.process_intents([intent])
                
                logger.info("Intent processed by pipeline", 
                            intent_id=str(intent.id), 
                            sub_intent_count=len(sub_intents))
                
                # TODO: Further process sub_intents (e.g., send to execution planner)
                for sub_intent in sub_intents:
                    logger.debug("Sub-intent created", 
                                 parent_id=str(sub_intent.parent_intent_id), 
                                 sub_id=str(sub_intent.id))

                self._intent_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error processing intent queue", error=str(e), exc_info=True)
                await asyncio.sleep(1) # Avoid tight loop on repeated errors
    
    async def _store_event(self, event: Event) -> None:
        """Store event in TimescaleDB event store."""
        query = """
            INSERT INTO events (
                id, event_type, event_version, aggregate_id, aggregate_type, 
                aggregate_version, business_timestamp, system_timestamp, 
                payload, metadata, signature, signer_public_key, hash
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                query,
                event.id,
                event.event_type,
                event.event_version,
                event.aggregate_id,
                event.aggregate_type,
                event.aggregate_version,
                event.business_timestamp,
                event.system_timestamp,
                event.payload.json(),
                event.metadata.json(),
                event.signature,
                event.signer_public_key,
                event.hash
            )
        logger.debug("Event stored in database", event_id=str(event.id), event_type=event.event_type)
    
    async def _get_aggregate_version(self, aggregate_id: UUID) -> int:
        """Get the latest version of an aggregate."""
        query = "SELECT MAX(aggregate_version) FROM events WHERE aggregate_id = $1"
        async with self.db_pool.acquire() as conn:
            version = await conn.fetchval(query, aggregate_id)
            return version or 0
    
    async def get_intent_status(self, intent_id: UUID) -> Optional[Dict[str, Any]]:
        """Get current status of an intent."""
        # In a full CQRS system, this would query a read model.
        # For now, we query the event stream for the latest status.
        query = """
            SELECT new_status, reason, filled_amount, business_timestamp
            FROM events e
            JOIN jsonb_to_record(e.payload) as p(new_status text, reason text, filled_amount text)
            ON true
            WHERE e.aggregate_id = $1
            AND e.event_type = 'intent.status_changed'
            ORDER BY e.business_timestamp DESC
            LIMIT 1;
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, intent_id)
            if row:
                return dict(row)
        return None
    
    async def get_intent_history(self, intent_id: UUID) -> List[Event]:
        """Get the full event history for an intent."""
        query = """
            SELECT * FROM events 
            WHERE aggregate_id = $1 
            ORDER BY aggregate_version ASC
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, intent_id)
            
            events = []
            for row in rows:
                # This is a simplified reconstruction. A real implementation would need to
                # deserialize the payload based on the event_type.
                payload_dict = json.loads(row['payload'])
                metadata_dict = json.loads(row['metadata'])
                
                # A more robust solution would use a factory or a mapping from
                # event_type to payload class.
                # For now, we make a broad assumption, which is not ideal.
                from ...types.events import EventPayload  # Avoid circular import
                class GenericPayload(EventPayload):
                    def get_event_type(self) -> str: return row['event_type']
                
                event = Event(
                    id=row['id'],
                    event_type=row['event_type'],
                    event_version=row['event_version'],
                    aggregate_id=row['aggregate_id'],
                    aggregate_type=row['aggregate_type'],
                    aggregate_version=row['aggregate_version'],
                    business_timestamp=row['business_timestamp'],
                    system_timestamp=row['system_timestamp'],
                    payload=GenericPayload(**payload_dict),
                    metadata=EventMetadata(**metadata_dict),
                    signature=row['signature'],
                    signer_public_key=row['signer_public_key'],
                    hash=row['hash']
                )
                events.append(event)
            return events

    def get_queue_size(self) -> int:
        """Get current size of the intent queue."""
        return self._intent_queue.qsize()