#!/usr/bin/env python3
"""Run the MyDiffuser client UI server.

This is a lightweight UI server that does NOT require PyTorch/GPU.
It can run on any machine and submits jobs to remote workers.

Usage:
    python scripts/run_client.py [--host HOST] [--port PORT]

Examples:
    # Run on localhost:8000 (default)
    python scripts/run_client.py

    # Run on all interfaces (accessible from network)
    python scripts/run_client.py --host 0.0.0.0

    # Custom port
    python scripts/run_client.py --port 8080
"""

import argparse
import logging
import os
import sys

# CRITICAL: Skip GPU detection in client to prevent hangs on broken GPU drivers
# This must be set BEFORE importing mydiffuser modules
os.environ["MYDIFFUSER_SKIP_GPU_DETECT"] = "1"

# Configure logging before any imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def get_uvicorn_log_config():
    """Get uvicorn logging config with timestamps."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s:%(name)s:%(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "access": {
                "format": "%(asctime)s %(levelname)s:%(name)s:%(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO"},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run MyDiffuser client UI server (no GPU required)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("MyDiffuser Client UI Server")
    logger.info("=" * 60)
    logger.info("Starting client server on %s:%d", args.host, args.port)
    logger.info("This is a lightweight client (no GPU/PyTorch required).")
    logger.info("Submits jobs to remote workers for inference.")
    logger.info("Press Ctrl+C to stop.")
    logger.info("")

    try:
        import uvicorn
        from mydiffuser.client.app import create_app

        app = create_app()

        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level="info",
            log_config=get_uvicorn_log_config(),
        )
    except KeyboardInterrupt:
        logger.info("\nShutdown requested, stopping client server...")
    except Exception as e:
        logger.exception("Client server crashed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
