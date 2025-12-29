#!/usr/bin/env python3
"""Worker server entrypoint.

Starts a headless FastAPI server that processes inference jobs.
Requires PyTorch and GPU access.

Usage:
    python scripts/run_worker.py [--port PORT] [--host HOST]

Examples:
    # Local worker
    python scripts/run_worker.py --port 8001

    # Remote worker (bind to all interfaces for SSH tunnel)
    python scripts/run_worker.py --host 0.0.0.0 --port 8001
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import uvicorn

from mydiffuser.worker.app import create_worker_app


def main():
    parser = argparse.ArgumentParser(description="Run mydiffuser worker server")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1, use 0.0.0.0 for remote access)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port to listen on (default: 8001)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (development only)",
    )

    args = parser.parse_args()

    print(f"Starting worker server on {args.host}:{args.port}")
    print("This process will load PyTorch models and process inference jobs.")
    print("Press Ctrl+C to stop.")
    print()

    app = create_worker_app()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
