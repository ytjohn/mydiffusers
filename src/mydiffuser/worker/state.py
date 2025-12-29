"""Worker state management for job progress tracking.

This module provides non-blocking progress tracking by using a shared
dictionary that generator callbacks can update without holding locks.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

logger = logging.getLogger(__name__)

# Shared progress state - updated by generator callbacks, read by status endpoint
# No lock needed since Python dict operations are atomic for single keys
job_progress: dict[str, "JobProgress"] = {}


@dataclass
class JobProgress:
    """Progress information for a running job."""

    status: Literal["queued", "pending", "running", "complete", "failed"]
    progress: float  # 0.0 to 1.0
    current_step: int
    total_steps: int
    message: str
    run_id: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    seconds_elapsed: float | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "progress": self.progress,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "message": self.message,
            "run_id": self.run_id,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "seconds_elapsed": self.seconds_elapsed,
        }


def init_job(job_id: str, total_steps: int) -> None:
    """Initialize job progress tracking."""
    job_progress[job_id] = JobProgress(
        status="pending",
        progress=0.0,
        current_step=0,
        total_steps=total_steps,
        message="Job queued",
        started_at=datetime.now(UTC),
    )
    logger.info(f"[{job_id}] Job initialized with {total_steps} steps")


def update_step(job_id: str, step: int, message: str | None = None) -> None:
    """Update job progress for a specific step."""
    if job_id not in job_progress:
        logger.warning(f"[{job_id}] Cannot update - job not initialized")
        return

    prog = job_progress[job_id]
    prog.current_step = step
    prog.progress = step / prog.total_steps if prog.total_steps > 0 else 0.0
    prog.status = "running"

    if message:
        prog.message = message
    else:
        prog.message = f"Step {step}/{prog.total_steps}"

    logger.debug(f"[{job_id}] Progress: {prog.progress:.1%} - {prog.message}")


def mark_complete(
    job_id: str, run_id: str, seconds_elapsed: float, message: str = "Complete"
) -> None:
    """Mark job as complete."""
    if job_id not in job_progress:
        logger.warning(f"[{job_id}] Cannot complete - job not initialized")
        return

    prog = job_progress[job_id]
    prog.status = "complete"
    prog.progress = 1.0
    prog.message = message
    prog.run_id = run_id
    prog.completed_at = datetime.now(UTC)
    prog.seconds_elapsed = seconds_elapsed

    logger.info(f"[{job_id}] Job complete in {seconds_elapsed:.2f}s -> {run_id}")


def mark_failed(job_id: str, error: str) -> None:
    """Mark job as failed."""
    if job_id not in job_progress:
        logger.warning(f"[{job_id}] Cannot fail - job not initialized")
        return

    prog = job_progress[job_id]
    prog.status = "failed"
    prog.message = "Failed"
    prog.error = error
    prog.completed_at = datetime.now(UTC)

    if prog.started_at:
        elapsed = (datetime.now(UTC) - prog.started_at).total_seconds()
        prog.seconds_elapsed = elapsed

    logger.error(f"[{job_id}] Job failed: {error}")


def get_progress(job_id: str) -> JobProgress | None:
    """Get current progress for a job. Returns None if job not found."""
    return job_progress.get(job_id)


def cleanup_job(job_id: str) -> None:
    """Remove job from progress tracking (called after client fetches results)."""
    if job_id in job_progress:
        del job_progress[job_id]
        logger.info(f"[{job_id}] Progress tracking cleaned up")
