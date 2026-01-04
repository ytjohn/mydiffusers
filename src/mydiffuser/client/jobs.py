"""Client-side job tracking and management."""

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from PIL import Image

from mydiffuser.client import database
from mydiffuser.client.config import (
    DEFAULT_WORKER_JOB_POLL_INTERVAL,
    get_worker_endpoint,
    list_workers,
)
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
    request_parameters: dict | None = None  # Request parameters

    # Timing
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    fetched_at: datetime | None = None


# Helper functions for database conversion
def _job_to_dict(job: ClientJob) -> dict:
    """Convert ClientJob to dict for database storage."""
    return asdict(job)


def _dict_to_job(data: dict) -> ClientJob:
    """Convert database dict to ClientJob dataclass."""
    # Filter out database-only fields that aren't in ClientJob
    job_fields = {
        "job_id",
        "type",
        "worker_name",
        "worker_endpoint",
        "status",
        "prompt",
        "preset",
        "seed",
        "worker_run_id",
        "worker_progress",
        "worker_step",
        "worker_total_steps",
        "worker_message",
        "local_run_id",
        "error",
        "created_at",
        "submitted_at",
        "completed_at",
        "fetched_at",
    }

    filtered_data = {k: v for k, v in data.items() if k in job_fields}

    # Convert ISO strings back to datetime objects
    for field_name in ["created_at", "submitted_at", "completed_at", "fetched_at"]:
        if filtered_data.get(field_name):
            filtered_data[field_name] = datetime.fromisoformat(
                filtered_data[field_name]
            )

    return ClientJob(**filtered_data)


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

    # Persist to database
    database.create_client_job(_job_to_dict(job))
    logger.info(f"Created client job {job_id} -> {worker_name} ({worker_endpoint})")
    return job


def get_job(job_id: str) -> ClientJob | None:
    """Get job by ID.

    Args:
        job_id: Job ID

    Returns:
        ClientJob if found, None otherwise
    """
    job_data = database.get_client_job(job_id)
    return _dict_to_job(job_data) if job_data else None


def list_jobs() -> list[ClientJob]:
    """List all tracked jobs.

    Returns:
        List of ClientJob instances, newest first
    """
    job_data_list = database.list_client_jobs()
    return [_dict_to_job(job_data) for job_data in job_data_list]


def update_job_status(job_id: str, status_data: dict) -> None:
    """Update job status from worker response.

    Args:
        job_id: Job ID
        status_data: Status dict from worker
    """
    job = get_job(job_id)
    if job is None:
        logger.warning(f"Attempted to update unknown job {job_id}")
        return

    # Prepare updates dict
    updates = {
        "status": status_data.get("status", "running"),
        "worker_progress": status_data.get("progress", 0.0),
        "worker_step": status_data.get("current_step", 0),
        "worker_total_steps": status_data.get("total_steps", 0),
        "worker_message": status_data.get("message"),
        "worker_run_id": status_data.get("run_id"),
        "error": status_data.get("error"),
    }

    # Set completed_at timestamp if status changed to complete/failed
    if updates["status"] == "complete" and job.completed_at is None:
        updates["completed_at"] = datetime.now(UTC)
    elif updates["status"] == "failed":
        updates["completed_at"] = datetime.now(UTC)

    # Persist to database
    database.update_client_job_status(job_id, updates)


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

                # Refresh job from database to get updated status
                job = get_job(job_id)
                if job is None:
                    logger.error(f"Job {job_id} disappeared from database")
                    return None

                if job.status == "complete":
                    break

                if job.status == "failed":
                    logger.error(f"Job {job_id} failed on worker")
                    return None

            except Exception as e:
                logger.exception(f"Error polling job {job_id}: {e}")
                database.update_client_job_status(
                    job_id, {"status": "failed", "error": str(e)}
                )
                return None

            # Wait before next poll
            await asyncio.sleep(DEFAULT_WORKER_JOB_POLL_INTERVAL)

        # Fetch results
        try:
            if job.worker_run_id is None:
                raise RuntimeError("Job complete but no worker_run_id")

            # Extract to client run directory
            local_dir = run_dir(job.worker_run_id)
            client.fetch_results(job_id, local_dir)

            # Update job with fetch completion
            database.update_client_job_status(
                job_id,
                {"local_run_id": job.worker_run_id, "fetched_at": datetime.now(UTC)},
            )

            # Index run in SQLite database
            from mydiffuser.utils.paths import read_json

            meta_file = local_dir / "meta.json"
            if meta_file.exists():
                try:
                    meta = read_json(meta_file)

                    # Add performance tracking
                    try:
                        from mydiffuser.database import performance_tracker

                        # Extract parameters and actual performance data
                        params = meta.get("params", {})
                        parameters = {
                            "width": params.get("width") or meta.get("width"),
                            "height": params.get("height") or meta.get("height"),
                            "num_inference_steps": params.get("num_inference_steps")
                            or meta.get("num_inference_steps"),
                            "guidance_scale": params.get("guidance_scale")
                            or meta.get("guidance_scale"),
                            "seed": params.get("seed") or meta.get("seed"),
                            "device": meta.get("device"),
                            "dtype": meta.get("dtype"),
                            "preset": params.get("preset") or meta.get("preset"),
                        }

                        # Determine model from meta data
                        model_id = "Tongyi-MAI/Z-Image-Turbo"  # Default based on your actual usage
                        if job.type == "video":
                            model_id = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"

                        # Calculate estimates for this actual run
                        from mydiffuser.client.estimate import job_estimator

                        try:
                            vram_estimates = job_estimator.estimate_job(
                                job.type, model_id, parameters, job.worker_name
                            )
                            vram_predicted = vram_estimates.vram_total_needed
                            time_predicted = vram_estimates.time_estimate_seconds
                        except Exception as e:
                            logger.warning(f"Estimation failed for job {job_id}: {e}")
                            vram_predicted = 19.3 if job.type == "image" else 11.7
                            time_predicted = 300

                        # Record actual performance data
                        # Extract actual VRAM from metadata if available, otherwise use estimates
                        actual_vram_total = meta.get("vram_used", vram_predicted)

                        performance_tracker.record_job_performance(
                            job_id=job_id,
                            worker_id=job.worker_name,
                            model_id=model_id,
                            model_type=job.type,
                            parameters=parameters,
                            vram_estimates={"total": vram_predicted},
                            vram_actual={
                                "total": actual_vram_total,
                                "model": actual_vram_total,  # Use allocated as model VRAM
                            },
                            model_was_loaded=False,
                            time_estimates={"predicted": time_predicted},
                            time_actual=meta.get("seconds_elapsed")
                            or meta.get("seconds", 0),
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record performance data: {e}")
                        # Set defaults if estimation failed
                        vram_predicted = 19.3 if job.type == "image" else 11.7
                        time_predicted = 300

                    # Add predictions to meta for database indexing
                    meta['vram_predicted_total'] = vram_predicted
                    meta['time_predicted_seconds'] = time_predicted

                    database.index_run(job.worker_run_id, meta)

                    # Trigger background training if enough new data available
                    try:
                        from mydiffuser.client.performance_estimator import (
                            performance_estimator,
                        )
                        from mydiffuser.config import GPU_ARCH

                        model_id = meta.get("params", {}).get("model_id")
                        gen_type = meta.get("type")
                        if model_id and gen_type and GPU_ARCH:
                            performance_estimator.check_and_train_if_needed(
                                model_id, GPU_ARCH, gen_type
                            )
                    except Exception as e:
                        logger.debug(f"Background training check failed: {e}")

                except Exception as e:
                    logger.warning(f"Failed to index run {job.worker_run_id}: {e}")
            return run_dir(job.worker_run_id)

        except Exception as e:
            logger.exception(f"Error handling completed job {job_id}: {e}")
            database.update_client_job_status(
                job_id, {"status": "failed", "error": str(e)}
            )
            return None


async def submit_image_job(
    worker_name: str,
    prompt: str,
    height: int,
    width: int,
    seed: int,
    num_inference_steps: int,
    guidance_scale: float,
    tags: list[str] | None = None,
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

    if tags is None:
        tags = []

    try:
        with WorkerClient(endpoint, timeout=10.0) as client:
            job_id = client.submit_image_job(
                prompt=prompt,
                height=height,
                width=width,
                seed=seed,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                tags=tags,
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
    resolution: str = "480p",
    model_size: str | None = None,
    tags: list[str] | None = None,
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
        resolution: Output resolution (480p or 720p)
        model_size: Model size (5B or 14B), None for worker default
        tags: Optional list of tags

    Returns:
        Job ID (UUID)

    Raises:
        Exception: If submission fails (worker offline or error)
    """
    endpoint = get_worker_endpoint(worker_name)

    logger.info(f"Submitting video job to {worker_name}: '{prompt[:50]}...'")

    if tags is None:
        tags = []

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
                resolution=resolution,
                model_size=model_size,
                tags=tags,
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


async def sync_jobs_from_workers() -> dict[str, int]:
    """Sync in-flight jobs from all workers on startup.

    Queries each worker for active jobs and adds them to client tracking if missing.
    This recovers jobs that were running when the client was restarted.

    Also attempts to fetch results for completed jobs that were never fetched.

    Returns:
        Dict mapping worker name to number of jobs recovered/retried
    """
    logger.info("Syncing jobs from workers...")
    recovered = {}

    # First, try to fetch any completed jobs that were never fetched
    unfetched_jobs = database.list_client_jobs(limit=100)
    unfetched = [
        j
        for j in unfetched_jobs
        if j["status"] == "complete" and j["fetched_at"] is None
    ]

    if unfetched:
        logger.info(
            f"Found {len(unfetched)} completed jobs that were never fetched, attempting recovery..."
        )
        for job_data in unfetched:
            job_id = job_data["job_id"]
            logger.info(f"Attempting to fetch results for job {job_id}")
            asyncio.create_task(poll_and_fetch_job(job_id))

    # Continue with normal worker sync for in-progress jobs

    for worker in list_workers():
        worker_name = worker["id"]
        endpoint = worker["endpoint"]

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{endpoint}/jobs")
                response.raise_for_status()
                data = response.json()

            worker_jobs = data.get("jobs", [])
            count = 0

            for job_data in worker_jobs:
                job_id = job_data.get("job_id")
                if not job_id:
                    continue

                # Skip if we already have this job
                if get_job(job_id) is not None:
                    logger.debug(f"Job {job_id} already tracked, updating status")
                    update_job_status(job_id, job_data)
                    continue

                # Skip completed/failed jobs (they're done, no need to track)
                status = job_data.get("status")
                if status in ("complete", "failed", "cancelled"):
                    continue

                # Recover the job
                logger.info(
                    f"Recovering job {job_id} from worker {worker_name} (status: {status})"
                )

                # Create ClientJob from worker data
                # Note: We don't have full request info, but we can track the job
                job = ClientJob(
                    job_id=job_id,
                    type="image",  # Default, we don't know the actual type
                    worker_name=worker_name,
                    worker_endpoint=endpoint,
                    status=status,
                    prompt="(Recovered from worker - in progress)",
                    worker_progress=job_data.get("progress", 0.0),
                    worker_step=job_data.get("current_step", 0),
                    worker_total_steps=job_data.get("total_steps", 0),
                    worker_message=job_data.get("message"),
                    worker_run_id=job_data.get("run_id"),
                    submitted_at=datetime.now(UTC),
                )

                # Persist to database
                database.create_client_job(_job_to_dict(job))

                # Start polling for this recovered job
                asyncio.create_task(poll_and_fetch_job(job_id))
                count += 1

            recovered[worker_name] = count
            logger.info(f"Recovered {count} jobs from worker {worker_name}")

        except Exception as e:
            logger.warning(f"Failed to sync jobs from worker {worker_name}: {e}")
            recovered[worker_name] = 0

    total = sum(recovered.values())
    logger.info(f"Job sync complete: recovered {total} total jobs across all workers")
    return recovered
