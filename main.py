"""Simple entrypoint to run the FastAPI app using package imports."""

import uvicorn
from platform_py.app import create_app
from platform_py.config import config


def main() -> None:
    app = create_app()
    uvicorn.run(
        app,
        host=config.api_host,
        port=config.api_port,
        log_level="debug" if config.debug else "info",
        reload=config.debug,
        access_log=config.debug,
        workers=1,
    )


if __name__ == "__main__":
    main()
