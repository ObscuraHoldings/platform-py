"""
Async event streaming with NATS JetStream and Redis for filtering and replay.
"""

import asyncio
import json
import structlog 
from typing import Dict, Any, Callable, Optional, List
from uuid import UUID

import nats
from nats.js import JetStreamContext
from nats.errors import TimeoutError as NatsTimeoutError, NoServersError
import redis.asyncio as redis
from dataclasses import dataclass, field

from ..config import config
from ..types import Event

logger = structlog.get_logger()


@dataclass
class StreamConfig:
    """Event stream configuration."""
    stream_name: str = "platform_events"
    subjects: List[str] = field(default_factory=lambda: ["intent.*", "strategy.*", "market.*", "execution.*", "system.*"])
    durable_name: str = "platform_worker"
    retention_policy: str = "workqueue" # Exactly-once semantics
    max_age_seconds: int = 86400  # 24 hours


class EventStream:
    """Manages event streaming with NATS JetStream and provides Redis-based features."""
    
    def __init__(self, nats_config=config.nats, redis_config=config.redis, stream_config=StreamConfig()):
        self.nats_config = nats_config
        self.redis_config = redis_config
        self.stream_config = stream_config
        
        self.nats_client: Optional[nats.NATS] = None
        self.jetstream: Optional[JetStreamContext] = None
        self.redis_client: Optional[redis.Redis] = None
        
        self._subscribers: Dict[str, List[Callable]] = {}
        self._is_initialized = False
        logger.info("EventStream initialized")

    async def initialize(self) -> None:
        """Initialize connections to NATS and Redis, and set up JetStream."""
        if self._is_initialized:
            return
            
        try:
            # Connect to NATS
            self.nats_client = await nats.connect(
                servers=self.nats_config.servers,
                reconnect_time_wait=self.nats_config.reconnect_time_wait,
                max_reconnect_attempts=self.nats_config.max_reconnect_attempts,
                error_cb=self._nats_error_cb,
                reconnected_cb=self._nats_reconnected_cb,
                disconnected_cb=self._nats_disconnected_cb,
                closed_cb=self._nats_closed_cb,
            )
            self.jetstream = self.nats_client.jetstream()
            logger.info("Connected to NATS", servers=self.nats_config.servers)
            
            # Create JetStream stream
            await self._setup_jetstream()
            
            # Connect to Redis
            self.redis_client = redis.from_url(
                self.redis_config.url,
                max_connections=self.redis_config.max_connections
            )
            await self.redis_client.ping()
            logger.info("Connected to Redis", host=self.redis_config.host)
            
            self._is_initialized = True
            logger.info("EventStream initialized successfully")

        except (NatsTimeoutError, NoServersError, redis.exceptions.ConnectionError) as e:
            logger.error("Failed to initialize EventStream", error=str(e), exc_info=True)
            raise

    async def _setup_jetstream(self) -> None:
        """Set up the JetStream stream and consumers."""
        try:
            stream = await self.jetstream.add_stream(
                name=self.stream_config.stream_name,
                subjects=self.stream_config.subjects,
                retention=self.stream_config.retention_policy,
                max_age=self.stream_config.max_age_seconds,
                storage="file",
                replicas=1 # For local dev; increase for production
            )
            logger.info("JetStream stream created or updated", name=stream.config.name)
        except Exception as e:
            logger.warning("Failed to create JetStream stream, may already exist", error=str(e))
            # Check if stream exists
            try:
                await self.jetstream.stream_info(self.stream_config.stream_name)
            except Exception as e_info:
                logger.error("JetStream stream does not exist and could not be created", error=str(e_info))
                raise

    async def shutdown(self) -> None:
        """Gracefully shut down connections."""
        if self.nats_client:
            await self.nats_client.close()
        if self.redis_client:
            await self.redis_client.close()
        self._is_initialized = False
        logger.info("EventStream shut down")

    async def publish(self, subject: str, event: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> None:
        """Publish an event to a subject with exactly-once delivery semantics."""
        if not self.jetstream:
            raise RuntimeError("EventStream not initialized")
        
        dedup_id = event.get('id', str(UUID()))
        message_data = json.dumps(event).encode('utf-8')
        
        try:
            ack = await self.jetstream.publish(
                subject,
                message_data,
                headers=headers,
                msg_id=dedup_id, # For deduplication
                timeout=5.0
            )
            logger.debug("Event published", subject=subject, stream=ack.stream, seq=ack.seq)
            
            # Optionally, buffer in Redis for quick replay
            await self._buffer_in_redis(subject, event)

        except NatsTimeoutError:
            logger.error("Publish timeout", subject=subject)

    async def subscribe(self, subject: str, handler: Callable[[Dict[str, Any]], None], durable_name: Optional[str] = None) -> None:
        """Subscribe to a subject with a handler."""
        if not self.jetstream:
            raise RuntimeError("EventStream not initialized")
            
        if subject not in self._subscribers:
            self._subscribers[subject] = []
        self._subscribers[subject].append(handler)
        
        durable = durable_name or f"{self.stream_config.durable_name}_{subject.replace('.*', '_wildcard')}"
        
        async def message_handler(msg):
            try:
                event_data = json.loads(msg.data.decode())
                logger.debug("Received event", subject=msg.subject)
                
                # Call all registered handlers for this subject
                for cb in self._subscribers.get(subject, []):
                    await cb(event_data)
                
                await msg.ack()
                
            except Exception as e:
                logger.error("Error processing event", subject=msg.subject, error=str(e))
                await msg.nak(delay=5) # Retry after 5 seconds

        await self.jetstream.subscribe(
            subject,
            durable=durable,
            cb=message_handler,
            manual_ack=True,
            ack_wait=30 # 30 seconds to process
        )
        logger.info("Subscribed to subject", subject=subject, durable_name=durable)

    async def _buffer_in_redis(self, subject: str, event: Dict[str, Any]) -> None:
        """Store event in a Redis stream for buffering and quick replay."""
        if not self.redis_client:
            return
        try:
            stream_key = f"events:{subject}"
            pipeline = self.redis_client.pipeline()
            pipeline.xadd(
                stream_key, 
                {b'data': json.dumps(event).encode()},
                maxlen=10000, 
                approximate=True
            )
            pipeline.expire(stream_key, self.stream_config.max_age_seconds)
            await pipeline.execute()
        except Exception as e:
            logger.warning("Failed to buffer event in Redis", error=str(e))

    async def get_stream_state(self, stream_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get the current state of a JetStream stream."""
        if not self.jetstream:
            return None
        try:
            stream_info = await self.jetstream.stream_info(stream_name or self.stream_config.stream_name)
            return stream_info.config.dict()
        except Exception as e:
            logger.error("Failed to get stream state", error=str(e))
            return None

    async def replay_events_from_redis(self, subject: str, from_timestamp_ms: int, to_timestamp_ms: Optional[int] = None) -> List[Dict[str, Any]]:
        """Replay events from Redis buffer."""
        if not self.redis_client:
            raise RuntimeError("Redis client not initialized")
            
        stream_key = f"events:{subject}"
        start = from_timestamp_ms
        end = to_timestamp_ms or "+"
        
        results = await self.redis_client.xrange(stream_key, start, end)
        return [json.loads(item[1][b'data']) for item in results]

    # NATS connection callbacks
    async def _nats_error_cb(self, e):
        logger.error("NATS connection error", error=str(e))

    async def _nats_reconnected_cb(self):
        logger.info("Reconnected to NATS")

    async def _nats_disconnected_cb(self):
        logger.warning("Disconnected from NATS")

    async def _nats_closed_cb(self):
        logger.warning("NATS connection closed")