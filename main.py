"""Simple entrypoint to run the FastAPI app using package imports."""

import uvicorn
from platform_py.config import config


def main() -> None:
    uvicorn.run(
        "platform_py.app:create_app",
        factory=True,
        host=config.api_host,
        port=config.api_port,
        log_level="debug" if config.debug else "info",
        reload=config.debug,
        access_log=config.debug,
        workers=1,
    )


if __name__ == "__main__":
    main()
