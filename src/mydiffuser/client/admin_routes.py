"""Admin API routes for database maintenance and system management."""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException

from mydiffuser.client import database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Track background backfill task
_backfill_task: asyncio.Task | None = None
_backfill_stats: dict | None = None


@router.post("/backfill")
async def trigger_backfill(
    force_refresh: Annotated[bool, Form()] = False,
):
    """Trigger database backfill from meta.json files in background.

    Reads all meta.json files from outputs/run/* directories and populates
    missing columns in the runs table (params, device, dtype, etc.).

    Args:
        force_refresh: If True, update ALL runs even if they already have params

    Returns:
        Acknowledgment that backfill started. Use /api/admin/backfill/status to check progress.
    """
    global _backfill_task, _backfill_stats

    # Check if backfill is already running
    if _backfill_task and not _backfill_task.done():
        raise HTTPException(
            status_code=409,
            detail="Backfill already in progress. Please wait for it to complete."
        )

    logger.info(f"Starting backfill in background (force_refresh={force_refresh})...")

    # Reset stats
    _backfill_stats = None

    # Run backfill in executor to avoid blocking (don't await it!)
    async def run_backfill():
        global _backfill_stats
        loop = asyncio.get_event_loop()
        _backfill_stats = await loop.run_in_executor(
            None, database.backfill_runs, force_refresh, None
        )
        logger.info(f"Backfill complete: {_backfill_stats}")

    _backfill_task = asyncio.create_task(run_backfill())

    return {
        "status": "started",
        "message": "Backfill started in background. Use /api/admin/backfill/status to check progress."
    }


@router.get("/backfill/status")
async def get_backfill_status():
    """Get status of last backfill operation.

    Returns:
        Status dict with: running (bool), stats (dict if complete)
    """
    global _backfill_task, _backfill_stats

    if _backfill_task is None:
        return {
            "running": False,
            "stats": None,
            "message": "No backfill has been run yet"
        }

    if not _backfill_task.done():
        return {
            "running": True,
            "stats": None,
            "message": "Backfill in progress..."
        }

    return {
        "running": False,
        "stats": _backfill_stats,
        "message": "Backfill complete"
    }
