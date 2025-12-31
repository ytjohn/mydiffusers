"""Client API routes for job submission and status."""

import logging
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile, File
from PIL import Image
import io

from mydiffuser.client import jobs
from mydiffuser.client.config import list_workers, WORKERS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["client"])


@router.get("/workers")
async def get_workers():
    """List available workers and their capabilities."""
    return {"workers": list_workers()}


@router.get("/workers/{worker_name}/capabilities")
async def get_worker_capabilities(worker_name: str):
    """Get capabilities for a specific worker.

    Args:
        worker_name: Worker name (e.g., "local", "remote")

    Returns:
        Worker capabilities including available video models

    Raises:
        HTTPException: If worker doesn't exist or is unreachable
    """
    if worker_name not in WORKERS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown worker: {worker_name}. Available: {list(WORKERS.keys())}",
        )

    worker_config = WORKERS[worker_name]
    endpoint = worker_config["endpoint"]

    # Query worker capabilities
    try:
        from mydiffuser.client.worker_client import WorkerClient

        with WorkerClient(endpoint, timeout=10.0) as client:
            caps = client.capabilities(timeout=5.0)
            return caps
    except Exception as e:
        logger.warning(f"Failed to fetch capabilities from {worker_name}: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Worker {worker_name} is unreachable: {e}",
        )


@router.post("/jobs/image")
async def submit_image_job(
    prompt: Annotated[str, Form()],
    worker: Annotated[str, Form()] = "local",
    height: Annotated[int, Form()] = 480,
    width: Annotated[int, Form()] = 832,
    seed: Annotated[int, Form()] = 42,
    steps: Annotated[int, Form()] = 4,
    guidance: Annotated[float, Form()] = 0.0,
    tags: Annotated[str, Form()] = "[]",
):
    """Submit an image generation job to a worker.

    Args:
        prompt: Text prompt for generation
        worker: Worker name (default: "local")
        height: Image height in pixels (default: 480)
        width: Image width in pixels (default: 832)
        seed: Random seed (default: 42)
        steps: Inference steps (default: 4)
        guidance: Guidance scale (default: 0.0)

    Returns:
        Job submission response with job_id
    """
    # Validate worker exists
    if worker not in WORKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown worker: {worker}. Available: {list(WORKERS.keys())}",
        )

    # Parse tags from JSON string
    import json
    try:
        tags_list = json.loads(tags)
    except json.JSONDecodeError:
        tags_list = []

    try:
        job_id = await jobs.submit_image_job(
            worker_name=worker,
            prompt=prompt,
            height=height,
            width=width,
            seed=seed,
            num_inference_steps=steps,
            guidance_scale=guidance,
            tags=tags_list,
        )

        return {
            "job_id": job_id,
            "status": "submitted",
            "worker": worker,
            "message": "Job submitted successfully. Polling for completion...",
        }

    except Exception as e:
        logger.exception(f"Failed to submit image job: {e}")
        raise HTTPException(status_code=500, detail=f"Job submission failed: {e}")


@router.post("/jobs/video")
async def submit_video_job(
    prompt: Annotated[str, Form()],
    image: Annotated[UploadFile | None, File()] = None,
    worker: Annotated[str, Form()] = "local",
    seed: Annotated[int, Form()] = 42,
    source_run_id: Annotated[str | None, Form()] = None,
    duration_seconds: Annotated[int, Form()] = 3,
    fps: Annotated[int, Form()] = 12,
    steps: Annotated[int, Form()] = 15,
    guidance: Annotated[float, Form()] = 3.0,
    resolution: Annotated[str, Form()] = "480p",
    model_size: Annotated[str | None, Form()] = None,
    tags: Annotated[str, Form()] = "[]",
):
    """Submit a video generation job to a worker.

    Args:
        prompt: Text prompt for generation
        image: Source image file (PNG, JPG, etc.) - optional if source_run_id provided
        worker: Worker name (default: "local")
        seed: Random seed (default: 42)
        source_run_id: Optional source run ID to use existing image
        duration_seconds: Duration in seconds (default: 3)
        fps: Frames per second (default: 12)
        steps: Inference steps (default: 15)
        guidance: Guidance scale (default: 3.0)

    Returns:
        Job submission response with job_id
    """
    # Validate worker exists
    if worker not in WORKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown worker: {worker}. Available: {list(WORKERS.keys())}",
        )

    # Handle source_run_id or image upload
    source_image = None
    if source_run_id and source_run_id.strip():
        # Load image from run ID
        from mydiffuser.utils.paths import run_dir
        run_path = run_dir(source_run_id.strip())
        image_path = run_path / "output.png"
        if not image_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Source run ID not found or no output.png: {source_run_id}",
            )
        try:
            source_image = Image.open(image_path)
            if source_image.mode != "RGB":
                source_image = source_image.convert("RGB")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid source image: {e}")
    elif image:
        # Read and validate uploaded image
        try:
            image_data = await image.read()
            source_image = Image.open(io.BytesIO(image_data))
            if source_image.mode != "RGB":
                source_image = source_image.convert("RGB")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid image: {e}")
    else:
        raise HTTPException(
            status_code=400,
            detail="Either source_run_id or image file must be provided",
        )

    # Parse tags from JSON string
    import json
    try:
        tags_list = json.loads(tags)
    except json.JSONDecodeError:
        tags_list = []

    try:
        job_id = await jobs.submit_video_job(
            worker_name=worker,
            prompt=prompt,
            source_image=source_image,
            seed=seed,
            source_run_id=source_run_id,
            duration_seconds=duration_seconds,
            fps=fps,
            num_inference_steps=steps,
            guidance_scale=guidance,
            resolution=resolution,
            model_size=model_size,
            tags=tags_list,
        )

        return {
            "job_id": job_id,
            "status": "submitted",
            "worker": worker,
            "message": "Job submitted successfully. Polling for completion...",
        }

    except Exception as e:
        logger.exception(f"Failed to submit video job: {e}")
        raise HTTPException(status_code=500, detail=f"Job submission failed: {e}")


@router.get("/jobs")
async def list_jobs_endpoint():
    """List all client-tracked jobs."""
    job_list = jobs.list_jobs()

    return {
        "jobs": [
            {
                "job_id": job.job_id,
                "type": job.type,
                "status": job.status,
                "worker": job.worker_name,
                "prompt": job.prompt[:100],  # Truncate for listing
                "preset": job.preset,
                "progress": job.worker_progress,
                "step": f"{job.worker_step}/{job.worker_total_steps}",
                "worker_run_id": job.worker_run_id,
                "local_run_id": job.local_run_id,
                "created_at": job.created_at.isoformat(),
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "error": job.error,
            }
            for job in job_list
        ]
    }


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get detailed status for a specific job.

    Args:
        job_id: Job ID to query

    Returns:
        Detailed job status
    """
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job.job_id,
        "type": job.type,
        "status": job.status,
        "worker": {
            "name": job.worker_name,
            "endpoint": job.worker_endpoint,
        },
        "request": {
            "prompt": job.prompt,
            "preset": job.preset,
            "seed": job.seed,
        },
        "progress": {
            "progress": job.worker_progress,
            "step": job.worker_step,
            "total_steps": job.worker_total_steps,
            "message": job.worker_message,
        },
        "results": {
            "worker_run_id": job.worker_run_id,
            "local_run_id": job.local_run_id,
        },
        "timing": {
            "created_at": job.created_at.isoformat(),
            "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "fetched_at": job.fetched_at.isoformat() if job.fetched_at else None,
        },
        "error": job.error,
    }
