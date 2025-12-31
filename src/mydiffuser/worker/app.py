"""Worker FastAPI application for headless inference processing."""

import asyncio
import io
import logging
import shutil
import tarfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from PIL import Image

from mydiffuser import __version__
from mydiffuser.config import (
    DEVICE,
    PLATFORM,
    PROJECT_ROOT,
    VIDEO_ENABLED,
    VIDEO_MODELS,
    VIDEO_MODEL_SIZE,
    configure_torch_backends,
    get_available_video_models,
)
from mydiffuser.models.requests import GenerateImageRequest, GenerateVideoRequest
from mydiffuser.utils.paths import worker_run_dir
from mydiffuser.worker import jobs, state
from mydiffuser.worker.queue import job_queue

logger = logging.getLogger(__name__)

# Lock to serialize GPU inference (only one job at a time)
infer_lock = asyncio.Lock()


def create_worker_app() -> FastAPI:
    """Create and configure the worker FastAPI application."""
    app = FastAPI(
        title="mydiffuser-worker",
        description="Headless inference worker for GPU processing",
        version=__version__,
    )

    @app.on_event("startup")
    async def startup():
        """Initialize worker (models load lazily on first request)."""
        logging.basicConfig(level=logging.INFO)
        logger.info("Worker starting up...")

        # Configure torch backends
        configure_torch_backends()

        # Start job queue processor
        job_queue.start_processor()

        logger.info("Worker startup complete")
        logger.info("Models will load lazily on first request (memory efficient)")
        logger.info("Job queue processor started (FIFO, one job at a time)")

    @app.on_event("shutdown")
    async def shutdown():
        """Cleanup on shutdown."""
        logger.info("Worker shutting down...")

        # Unload any loaded models
        from mydiffuser.inference.state import _unload_all_models
        _unload_all_models()

        logger.info("Worker shutdown complete")

    @app.get("/health")
    async def health():
        """Worker health check and capabilities."""
        import torch

        health_info = {
            "status": "healthy",
            "gpu_available": torch.cuda.is_available(),
            "capabilities": [],
            "queued_jobs": job_queue.get_queue_size(),
            "running_job": job_queue.get_current_job_id(),
            "device": DEVICE,
        }

        # GPU memory info
        if torch.cuda.is_available():
            try:
                mem_info = torch.cuda.mem_get_info()
                health_info["gpu_memory_free_gb"] = round(mem_info[0] / (1024**3), 1)
                health_info["gpu_memory_total_gb"] = round(mem_info[1] / (1024**3), 1)
                health_info["gpu_memory_used_gb"] = round(
                    (mem_info[1] - mem_info[0]) / (1024**3), 1
                )
                health_info["gpu_name"] = torch.cuda.get_device_name(0)
            except Exception as e:
                health_info["gpu_error"] = str(e)

        # Capabilities (all types supported via lazy loading)
        health_info["capabilities"].append("image")
        if VIDEO_ENABLED:
            health_info["capabilities"].append("video")
            # Include available video models
            health_info["video_models"] = get_available_video_models()

        # Platform info
        health_info["platform"] = PLATFORM

        # Report currently loaded model (if any)
        from mydiffuser.inference.state import get_active_model
        active = get_active_model()
        if active:
            health_info["active_model"] = active

        return health_info

    @app.get("/capabilities")
    async def capabilities():
        """Get worker capabilities (models, platform, features).

        This is a lightweight endpoint specifically for capability discovery.
        Clients should call this when selecting a worker to determine:
        - Available video models (5B, 14B)
        - Platform (rocm, cuda, cpu)
        - Supported job types
        """
        caps = {
            "platform": PLATFORM,
            "job_types": ["image"],
        }

        if VIDEO_ENABLED:
            caps["job_types"].append("video")
            caps["video_models"] = get_available_video_models()

        return caps

    @app.get("/gpu/test")
    async def gpu_test():
        """Run a GPU compute test to verify functionality.

        Performs matrix multiplication to validate:
        - GPU is accessible
        - CUDA/ROCm drivers work
        - Compute performance is reasonable

        Useful for validating remote worker deployments.
        """
        import time
        import torch

        if not torch.cuda.is_available():
            return {"ok": False, "error": "No GPU available"}

        try:
            device_name = torch.cuda.get_device_name(0)

            # Small warmup
            warmup = torch.randn(256, 256, device="cuda", dtype=torch.float16)
            _ = warmup @ warmup
            torch.cuda.synchronize()
            del warmup

            # Timed test: 4096x4096 matmul, 10 iterations
            size = 4096
            iterations = 10

            x = torch.randn(size, size, device="cuda", dtype=torch.float16)
            y = torch.randn(size, size, device="cuda", dtype=torch.float16)
            torch.cuda.synchronize()

            t0 = time.perf_counter()
            for _ in range(iterations):
                z = x @ y
            torch.cuda.synchronize()
            elapsed = time.perf_counter() - t0

            # Get a sample value for verification
            sample_value = float(z[0, 0].item())

            # Calculate TFLOPS (2 * N^3 ops per matmul)
            flops_per_matmul = 2 * (size**3)
            total_flops = flops_per_matmul * iterations
            tflops = (total_flops / elapsed) / 1e12

            # Cleanup
            del x, y, z
            torch.cuda.empty_cache()

            return {
                "ok": True,
                "device": device_name,
                "test": {
                    "size": size,
                    "iterations": iterations,
                    "elapsed_sec": round(elapsed, 3),
                    "tflops": round(tflops, 2),
                    "sample_value": round(sample_value, 4),
                },
            }

        except Exception as e:
            logger.exception("GPU test failed")
            return {
                "ok": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    @app.post("/jobs")
    async def submit_job(
        type: str = Form(...),
        request_json: str = Form(...),
        image: UploadFile | None = File(None),
    ):
        """Submit a new job (image or video).

        For image jobs:
            - type: "image"
            - request_json: JSON string of GenerateImageRequest

        For video jobs:
            - type: "video"
            - request_json: JSON string of GenerateVideoRequest
            - image: Uploaded source image file
        """
        import json

        job_id = str(uuid.uuid4())
        logger.info(f"[{job_id}] New {type} job submitted")

        # Parse request
        try:
            request_data = json.loads(request_json)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

        # Add job to queue instead of spawning immediately
        if type == "image":
            request = GenerateImageRequest(**request_data)

            # Create executor function for this job
            async def executor():
                await _run_image_job(job_id, request)

            await job_queue.submit(job_id, "image", executor)

        elif type == "video":
            if image is None:
                raise HTTPException(status_code=400, detail="Video jobs require source image")

            request = GenerateVideoRequest(**request_data)

            # Validate model_size if specified
            if request.model_size:
                available_models = get_available_video_models()
                if request.model_size not in available_models:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Model {request.model_size} not available on this worker. "
                        f"Available models: {', '.join(available_models)}",
                    )

            # Read uploaded image
            image_data = await image.read()
            source_image = Image.open(io.BytesIO(image_data))
            if source_image.mode != "RGB":
                source_image = source_image.convert("RGB")

            # Create executor function for this job
            async def executor():
                await _run_video_job(job_id, request, source_image)

            await job_queue.submit(job_id, "video", executor)

        else:
            raise HTTPException(status_code=400, detail=f"Unknown job type: {type}")

        queue_position = job_queue.get_queue_size()
        return {
            "job_id": job_id,
            "status": "queued",
            "queue_position": queue_position,
        }

    async def _run_image_job(job_id: str, request: GenerateImageRequest):
        """Run image generation job in background."""
        async with infer_lock:
            try:
                # Lazy load image generator (will swap models if needed)
                from mydiffuser.inference.state import ensure_image_generator
                gen = ensure_image_generator()

                await asyncio.get_event_loop().run_in_executor(
                    None, jobs.execute_image_job, job_id, request, gen
                )
            except Exception as e:
                logger.exception(f"[{job_id}] Job execution failed")
                state.mark_failed(job_id, str(e))

    async def _run_video_job(
        job_id: str, request: GenerateVideoRequest, source_image: Image.Image
    ):
        """Run video generation job in background."""
        async with infer_lock:
            try:
                # Determine which model to use
                model_size = request.model_size or VIDEO_MODEL_SIZE
                model_id = VIDEO_MODELS.get(model_size, VIDEO_MODELS["5B"])

                logger.info(f"[{job_id}] Using video model: {model_size} ({model_id})")

                # Lazy load video generator (will swap models if needed)
                from mydiffuser.inference.state import ensure_video_generator
                gen = ensure_video_generator(model_id=model_id)

                await asyncio.get_event_loop().run_in_executor(
                    None,
                    jobs.execute_video_job,
                    job_id,
                    request,
                    source_image,
                    gen,
                )
            except Exception as e:
                logger.exception(f"[{job_id}] Job execution failed")
                state.mark_failed(job_id, str(e))

    @app.get("/jobs/{job_id}/status")
    async def get_job_status(job_id: str):
        """Get job status and progress (non-blocking)."""
        progress = state.get_progress(job_id)
        if progress is None:
            raise HTTPException(status_code=404, detail="Job not found")

        return progress.to_dict()

    @app.get("/jobs/{job_id}/files")
    async def get_job_files(job_id: str):
        """Download job results as tar.gz archive."""
        progress = state.get_progress(job_id)
        if progress is None:
            raise HTTPException(status_code=404, detail="Job not found")

        if progress.status != "complete":
            raise HTTPException(
                status_code=400,
                detail=f"Job not complete (status: {progress.status})",
            )

        if progress.run_id is None:
            raise HTTPException(status_code=500, detail="Job complete but no run_id")

        # Get run directory (from worker temp storage)
        rd = worker_run_dir(progress.run_id)
        if not rd.exists():
            raise HTTPException(status_code=404, detail="Run directory not found")

        # Create tar.gz in memory
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
            for file_path in rd.iterdir():
                if file_path.is_file():
                    tar.add(file_path, arcname=file_path.name)

        tar_buffer.seek(0)

        # Return as streaming response
        return StreamingResponse(
            iter([tar_buffer.getvalue()]),
            media_type="application/gzip",
            headers={
                "Content-Disposition": f"attachment; filename={progress.run_id}.tar.gz"
            },
        )

    @app.delete("/jobs/{job_id}")
    async def delete_job(job_id: str):
        """Delete job results and cleanup progress tracking."""
        progress = state.get_progress(job_id)
        if progress is None:
            raise HTTPException(status_code=404, detail="Job not found")

        # Delete run directory if exists (from worker temp storage)
        if progress.run_id:
            rd = worker_run_dir(progress.run_id)
            if rd.exists():
                shutil.rmtree(rd)
                logger.info(f"[{job_id}] Deleted run directory: {progress.run_id}")

        # Cleanup progress tracking
        state.cleanup_job(job_id)

        return {"status": "deleted", "job_id": job_id}

    return app
