"""
FastAPI application factory for the trading platform.
"""

import asyncio
import structlog
from structlog.contextvars import merge_contextvars, bind_contextvars, clear_contextvars
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .setup_event_loop import setup_event_loop
from .config import config


# Set up structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        merge_contextvars,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan management."""
    # Setup event loop optimization
    setup_event_loop()
    
    logger.info("Starting platform services", environment=config.environment)
    
    # Pre-warm Rust extension and runtime (if available)
    try:
        from . import rust_bindings as _rb  # noqa: F401
        logger.info("Rust extension loaded", available=bool(getattr(_rb, "_platform_rust", None)))
    except Exception as e:
        logger.warning("Rust extension import failed; using fallbacks", error=str(e))
    
    # Initialize service connections
    from .services import services
    await services.connect_all()

    # Initialize core components
    from .dependencies import components
    await components.initialize()
    
    logger.info("Platform services started successfully")
    
    yield
    
    # Cleanup on shutdown
    logger.info("Shutting down platform services")
    
    from .dependencies import components
    await components.shutdown()
    
    from .services import services
    await services.disconnect_all()
    
    logger.info("Platform services shut down successfully")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    
    app = FastAPI(
        title="Hybrid Trading Platform",
        description="Python-Rust hybrid strategy execution platform",
        version="0.1.0",
        debug=config.debug,
        lifespan=lifespan
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if config.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID/Correlation ID middleware for observability
    from starlette.middleware.base import BaseHTTPMiddleware
    import uuid

    async def request_id_dispatch(request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        # Bind request_id into structlog contextvars for this request
        bind_contextvars(request_id=req_id)
        try:
            response = await call_next(request)
        finally:
            # Clear context to avoid leaking between requests
            clear_contextvars()
        response.headers["X-Request-ID"] = req_id
        return response

    app.add_middleware(BaseHTTPMiddleware, dispatch=request_id_dispatch)
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "environment": config.environment,
            "version": "0.1.0"
        }
    
    # Add API routers
    from .api import api_router
    app.include_router(api_router, prefix="/api/v1")
    
    logger.info("FastAPI application created", debug=config.debug)
    
    return app
