"""Client-side job tracking and management."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from PIL import Image

from mydiffuser.client.config import get_worker_endpoint, DEFAULT_WORKER_JOB_POLL_INTERVAL
from mydiffuser.client.worker_client import WorkerClient
from mydiffuser.utils.paths import run_dir

logger = logging.getLogger(__name__)

JobType = Literal["image", "video"]
JobStatus = Literal["pending", "submitted", "running", "complete", "failed"]


@dataclass
class ClientJob:
    """Client-side job tracking information."""

    job_id: str  # UUID from worker
    type: JobType  # "image" or "video"
    worker_name: str  # Which worker this was submitted to
    worker_endpoint: str  # Worker URL
    status: JobStatus = "pending"  # Current status
    prompt: str = ""  # User prompt
    preset: str = "draft"  # Quality preset
    seed: int = 42  # Random seed

    # Worker-side info (populated when complete)
    worker_run_id: str | None = None  # Run ID on worker
    worker_progress: float = 0.0  # 0.0 to 1.0
    worker_step: int = 0  # Current step
    worker_total_steps: int = 0  # Total steps
    worker_message: str | None = None  # Status message

    # Client-side info
    local_run_id: str | None = None  # Run ID after fetching to local
    error: str | None = None  # Error message if failed

    # Timing
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    fetched_at: datetime | None = None


# In-memory job storage (TODO: persist to SQLite)
_jobs: dict[str, ClientJob] = {}


def create_job(
    job_id: str,
    job_type: JobType,
    worker_name: str,
    prompt: str,
    preset: str = "draft",
    seed: int = 42,
) -> ClientJob:
    """Create and track a new job.

    Args:
        job_id: Worker job ID (UUID)
        job_type: "image" or "video"
        worker_name: Worker identifier
        prompt: Generation prompt
        preset: Quality preset
        seed: Random seed

    Returns:
        Created ClientJob instance
    """
    worker_endpoint = get_worker_endpoint(worker_name)

    job = ClientJob(
        job_id=job_id,
        type=job_type,
        worker_name=worker_name,
        worker_endpoint=worker_endpoint,
        status="submitted",
        prompt=prompt,
        preset=preset,
        seed=seed,
        submitted_at=datetime.now(UTC),
    )

    _jobs[job_id] = job
    logger.info(f"Created client job {job_id} -> {worker_name} ({worker_endpoint})")
    return job


def get_job(job_id: str) -> ClientJob | None:
    """Get job by ID.

    Args:
        job_id: Job ID

    Returns:
        ClientJob if found, None otherwise
    """
    return _jobs.get(job_id)


def list_jobs() -> list[ClientJob]:
    """List all tracked jobs.

    Returns:
        List of ClientJob instances, newest first
    """
    return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)


def update_job_status(job_id: str, status_data: dict) -> None:
    """Update job status from worker response.

    Args:
        job_id: Job ID
        status_data: Status dict from worker
    """
    job = _jobs.get(job_id)
    if job is None:
        logger.warning(f"Attempted to update unknown job {job_id}")
        return

    # Update from worker status
    job.status = status_data.get("status", "running")
    job.worker_progress = status_data.get("progress", 0.0)
    job.worker_step = status_data.get("current_step", 0)
    job.worker_total_steps = status_data.get("total_steps", 0)
    job.worker_message = status_data.get("message")
    job.worker_run_id = status_data.get("run_id")
    job.error = status_data.get("error")

    if job.status == "complete" and job.completed_at is None:
        job.completed_at = datetime.now(UTC)
    elif job.status == "failed":
        job.completed_at = datetime.now(UTC)


async def poll_and_fetch_job(job_id: str) -> Path | None:
    """Poll worker for job completion and fetch results.

    This is a long-running async function that polls the worker
    until the job completes, then fetches the results.

    Args:
        job_id: Job ID to poll

    Returns:
        Path to local run directory if successful, None if failed
    """
    job = get_job(job_id)
    if job is None:
        logger.error(f"Cannot poll unknown job {job_id}")
        return None

    logger.info(f"Starting to poll job {job_id} on {job.worker_name}")

    with WorkerClient(job.worker_endpoint) as client:
        # Poll until complete
        while True:
            try:
                status_data = client.get_status(job_id)
                update_job_status(job_id, status_data)

                if job.status == "complete":
                    logger.info(f"Job {job_id} complete, fetching results...")
                    break
                elif job.status == "failed":
                    logger.error(f"Job {job_id} failed: {job.error}")
                    return None

                # Wait before next poll
                await asyncio.sleep(DEFAULT_WORKER_JOB_POLL_INTERVAL)

            except Exception as e:
                logger.exception(f"Error polling job {job_id}: {e}")
                job.status = "failed"
                job.error = str(e)
                return None

        # Fetch results
        try:
            if job.worker_run_id is None:
                raise RuntimeError("Job complete but no worker_run_id")

            # Extract to client run directory
            local_dir = run_dir(job.worker_run_id)
            client.fetch_results(job_id, local_dir)

            job.local_run_id = job.worker_run_id
            job.fetched_at = datetime.now(UTC)

            logger.info(f"Job {job_id} results fetched to {local_dir}")
            return local_dir

        except Exception as e:
            logger.exception(f"Error fetching results for job {job_id}: {e}")
            job.status = "failed"
            job.error = f"Fetch failed: {e}"
            return None


async def submit_image_job(
    worker_name: str,
    prompt: str,
    height: int,
    width: int,
    seed: int,
    num_inference_steps: int,
    guidance_scale: float,
) -> str:
    """Submit an image generation job to a worker.

    Args:
        worker_name: Worker to submit to
        prompt: Text prompt
        height: Image height in pixels
        width: Image width in pixels
        seed: Random seed
        num_inference_steps: Inference steps
        guidance_scale: Guidance scale

    Returns:
        Job ID (UUID)

    Raises:
        Exception: If submission fails (worker offline or error)
    """
    endpoint = get_worker_endpoint(worker_name)

    logger.info(f"Submitting image job to {worker_name}: '{prompt[:50]}...'")

    try:
        with WorkerClient(endpoint, timeout=10.0) as client:
            job_id = client.submit_image_job(
                prompt=prompt,
                height=height,
                width=width,
                seed=seed,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
            )

        # Track locally (preset removed, just for tracking purposes we'll use "custom")
        create_job(
            job_id=job_id,
            job_type="image",
            worker_name=worker_name,
            prompt=prompt,
            preset="custom",
            seed=seed,
        )

        # Start background polling task
        asyncio.create_task(poll_and_fetch_job(job_id))

        return job_id

    except Exception as e:
        # Log error with context about which worker failed
        error_msg = f"Worker '{worker_name}' ({endpoint}) unreachable or failed: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


async def submit_video_job(
    worker_name: str,
    prompt: str,
    source_image: Image.Image,
    seed: int,
    source_run_id: str | None,
    duration_seconds: int,
    fps: int,
    num_inference_steps: int,
    guidance_scale: float,
) -> str:
    """Submit a video generation job to a worker.

    Args:
        worker_name: Worker to submit to
        prompt: Text prompt
        source_image: Source image for I2V
        seed: Random seed
        source_run_id: Optional source run ID
        duration_seconds: Duration in seconds
        fps: Frames per second
        num_inference_steps: Inference steps
        guidance_scale: Guidance scale

    Returns:
        Job ID (UUID)

    Raises:
        Exception: If submission fails (worker offline or error)
    """
    endpoint = get_worker_endpoint(worker_name)

    logger.info(f"Submitting video job to {worker_name}: '{prompt[:50]}...'")

    try:
        with WorkerClient(endpoint, timeout=10.0) as client:
            job_id = client.submit_video_job(
                prompt=prompt,
                source_image=source_image,
                seed=seed,
                source_run_id=source_run_id,
                duration_seconds=duration_seconds,
                fps=fps,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
            )

        # Track locally (preset removed, just for tracking purposes we'll use "custom")
        create_job(
            job_id=job_id,
            job_type="video",
            worker_name=worker_name,
            prompt=prompt,
            preset="custom",
            seed=seed,
        )

        # Start background polling task
        asyncio.create_task(poll_and_fetch_job(job_id))

        return job_id

    except Exception as e:
        # Log error with context about which worker failed
        error_msg = f"Worker '{worker_name}' ({endpoint}) unreachable or failed: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e
