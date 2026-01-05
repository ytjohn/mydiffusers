"""Client configuration for worker endpoints."""

import os
from typing import Literal

# Worker endpoints (can be overridden by environment variables)
DEFAULT_LOCAL_WORKER = os.environ.get("MYDIFFUSER_LOCAL_WORKER", "http://localhost:8001")
DEFAULT_REMOTE_WORKER = os.environ.get("MYDIFFUSER_REMOTE_WORKER", "http://localhost:8002")

# Worker configuration
# Note: Capabilities are queried dynamically from each worker's /capabilities endpoint
# Do not hardcode capabilities here as they depend on worker configuration (VIDEO_ENABLED, etc)
WORKERS = {
    "local": {
        "name": "Local Worker",
        "endpoint": DEFAULT_LOCAL_WORKER,
        "description": "Local GPU (AMD Framework Desktop)",
    },
    "remote": {
        "name": "Remote Worker",
        "endpoint": DEFAULT_REMOTE_WORKER,
        "description": "Remote GPU (Lambda Labs via SSH tunnel)",
    },
}

# Default worker for each job type
DEFAULT_WORKER_FOR_IMAGE = "local"
DEFAULT_WORKER_FOR_VIDEO = "local"
DEFAULT_WORKER_JOB_POLL_INTERVAL = 5  # seconds

WorkerName = Literal["local", "remote"]


def get_worker_endpoint(worker_name: str) -> str:
    """Get worker endpoint URL by name.

    Args:
        worker_name: Worker name (e.g., "local", "remote")

    Returns:
        Worker endpoint URL

    Raises:
        KeyError: If worker not found
    """
    return WORKERS[worker_name]["endpoint"]


def list_workers() -> list[dict]:
    """List all configured workers.

    Returns:
        List of worker config dicts
    """
    return [
        {
            "id": worker_id,
            **config,
        }
        for worker_id, config in WORKERS.items()
    ]
