"""
Service connections management for external services like database, cache, etc.
"""

import structlog
import asyncpg
import redis.asyncio as redis
import ray
from typing import Optional

from .config import config
from .streaming import EventStream

logger = structlog.get_logger()


class ServiceConnector:
    """Manages connections to external services."""
    
    def __init__(self):
        self.db_pool: Optional[asyncpg.Pool] = None
        self.redis_client: Optional[redis.Redis] = None
        self.event_stream: Optional[EventStream] = None
    
    async def connect_all(self) -> None:
        """Connect to all external services."""
        logger.info("Connecting to external services")
        
        # Connect to Database
        try:
            # Prefer explicit max_size parameter; fall back to max_overflow if only that is set
            max_size = getattr(config.database, "max_size", None) or config.database.max_overflow
            if max_size < config.database.pool_size:
                raise ValueError("database.max_size must be >= database.pool_size")

            self.db_pool = await asyncpg.create_pool(
                dsn=config.database.url,
                min_size=config.database.pool_size,
                max_size=max_size,
            )

            # Simple health check: acquire and release one connection
            async with self.db_pool.acquire() as conn:
                await conn.fetchrow('SELECT 1')

            logger.info("Database connection pool created and verified", pool_size=config.database.pool_size, max_size=max_size)
        except Exception as e:
            logger.error("Failed to connect to database", error=str(e), exc_info=True)
            raise
        
        # Connect to Redis
        try:
            self.redis_client = redis.from_url(
                config.redis.url,
                max_connections=config.redis.max_connections
            )
            await self.redis_client.ping()
            logger.info("Redis connection successful")
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e), exc_info=True)
            raise

        # Connect to NATS and initialize EventStream
        try:
            self.event_stream = EventStream()
            await self.event_stream.initialize()
            logger.info("EventStream initialized")
        except Exception as e:
            logger.error("Failed to initialize EventStream", error=str(e), exc_info=True)
            raise
            
        # Connect to Ray
        try:
            if not ray.is_initialized():
                ray.init(address=config.ray.address or 'auto')
            logger.info("Ray connected", address=config.ray.address or 'auto')
        except Exception as e:
            logger.error("Failed to connect to Ray", error=str(e), exc_info=True)
            raise

    async def disconnect_all(self) -> None:
        """Disconnect from all external services."""
        logger.info("Disconnecting from external services")
        
        if self.db_pool:
            await self.db_pool.close()
            logger.info("Database connection pool closed")
            
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")

        if self.event_stream:
            await self.event_stream.shutdown()
            logger.info("EventStream shut down")
            
        if ray.is_initialized():
            ray.shutdown()
            logger.info("Ray shut down")


# Global service connector instance
services = ServiceConnector()