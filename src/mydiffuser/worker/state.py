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

    status: Literal["queued", "pending", "running", "complete", "failed", "cancelled"]
    progress: float  # 0.0 to 1.0
    current_step: int
    total_steps: int
    message: str
    run_id: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    seconds_elapsed: float | None = None
    cancelled: bool = False  # Flag for cancellation request

    # Timing information for ETA calculation
    last_step_time: datetime | None = None  # When the last step completed
    seconds_per_iteration: float | None = None  # Average time per iteration
    eta_seconds: float | None = None  # Estimated time remaining

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
            "seconds_per_iteration": self.seconds_per_iteration,
            "eta_seconds": self.eta_seconds,
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
    """Update job progress for a specific step.

    Automatically calculates iteration time and ETA based on timing.
    """
    if job_id not in job_progress:
        logger.warning(f"[{job_id}] Cannot update - job not initialized")
        return

    prog = job_progress[job_id]
    now = datetime.now(UTC)

    # Calculate iteration timing
    if prog.last_step_time and step > 0:
        # Time since last step
        step_duration = (now - prog.last_step_time).total_seconds()

        # Update rolling average (weighted toward recent iterations)
        if prog.seconds_per_iteration is None:
            prog.seconds_per_iteration = step_duration
        else:
            # Exponential moving average (weight=0.3 for new value)
            prog.seconds_per_iteration = (
                0.7 * prog.seconds_per_iteration + 0.3 * step_duration
            )

        # Calculate ETA (remaining steps * avg time per step)
        remaining_steps = prog.total_steps - step
        prog.eta_seconds = remaining_steps * prog.seconds_per_iteration

    prog.last_step_time = now
    prog.current_step = step
    prog.progress = step / prog.total_steps if prog.total_steps > 0 else 0.0
    prog.status = "running"

    if message:
        prog.message = message
    else:
        # Include ETA in message if available
        if prog.eta_seconds:
            eta_mins = prog.eta_seconds / 60
            if eta_mins >= 1:
                prog.message = f"Step {step}/{prog.total_steps} (ETA: {eta_mins:.1f}m)"
            else:
                prog.message = f"Step {step}/{prog.total_steps} (ETA: {prog.eta_seconds:.0f}s)"
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


def request_cancellation(job_id: str) -> bool:
    """Request cancellation of a running job.

    Returns True if cancellation was requested, False if job not found or already complete.
    The actual cancellation happens between diffusion steps when the callback checks this flag.
    """
    if job_id not in job_progress:
        logger.warning(f"[{job_id}] Cannot cancel - job not found")
        return False

    prog = job_progress[job_id]

    # Can't cancel if already finished
    if prog.status in ("complete", "failed", "cancelled"):
        logger.warning(f"[{job_id}] Cannot cancel - job already {prog.status}")
        return False

    prog.cancelled = True
    logger.info(f"[{job_id}] Cancellation requested")
    return True


def is_cancelled(job_id: str) -> bool:
    """Check if a job has been cancelled.

    This is called by the progress callback to determine if generation should stop.
    """
    if job_id not in job_progress:
        return False
    return job_progress[job_id].cancelled


def mark_cancelled(job_id: str) -> None:
    """Mark job as cancelled after generation has stopped."""
    if job_id not in job_progress:
        logger.warning(f"[{job_id}] Cannot mark cancelled - job not initialized")
        return

    prog = job_progress[job_id]
    prog.status = "cancelled"
    prog.message = "Cancelled by user"
    prog.completed_at = datetime.now(UTC)

    if prog.started_at:
        elapsed = (datetime.now(UTC) - prog.started_at).total_seconds()
        prog.seconds_elapsed = elapsed

    logger.info(f"[{job_id}] Job cancelled at step {prog.current_step}/{prog.total_steps}")


def cleanup_job(job_id: str) -> None:
    """Remove job from progress tracking (called after client fetches results)."""
    if job_id in job_progress:
        del job_progress[job_id]
        logger.info(f"[{job_id}] Progress tracking cleaned up")
