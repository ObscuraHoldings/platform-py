"""
Main entry point for the hybrid trading platform.
"""

import asyncio
import sys
import uvicorn
from platform.app import create_app
from platform.config import config

try:
    import uvloop
    UVLOOP_AVAILABLE = True
except ImportError:
    UVLOOP_AVAILABLE = False


def setup_event_loop_policy():
    """Set up uvloop event loop policy before starting the server."""
    if UVLOOP_AVAILABLE and sys.platform != "win32":
        uvloop.install()
        print("uvloop event loop policy installed for main process")
    else:
        print("Using default asyncio event loop policy")


def main():
    """Main entry point with uvloop optimization."""
    # Set up uvloop before creating the app
    setup_event_loop_policy()
    
    app = create_app()
    
    uvicorn.run(
        app,
        host=config.api_host,
        port=config.api_port,
        log_level="info" if not config.debug else "debug",
        reload=config.debug,
        access_log=config.debug,
        loop="uvloop" if UVLOOP_AVAILABLE and sys.platform != "win32" else "asyncio",
        workers=1,  # Single worker for now, can be scaled later
    )


if __name__ == "__main__":
    main()
