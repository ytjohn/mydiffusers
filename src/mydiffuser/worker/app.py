"""Worker FastAPI application for headless inference processing."""

import asyncio
import io
import logging
import shutil
import tarfile
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image

from mydiffuser import __version__
from mydiffuser.config import (
    DEVICE,
    PLATFORM,
    VIDEO_ENABLED,
    VIDEO_MODEL_SIZE,
    VIDEO_MODELS,
    configure_torch_backends,
    get_available_video_models,
)
from mydiffuser.models.requests import GenerateImageRequest, GenerateVideoRequest
from mydiffuser.utils.paths import worker_run_dir
from mydiffuser.utils.vram_predictor import vram_predictor
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
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
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

        from mydiffuser.config import GPU_ARCH, GPU_NAME

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
                health_info["gpu_name"] = GPU_NAME  # Use config.py detection
                health_info["gpu_arch"] = GPU_ARCH  # Add architecture (e.g., gfx1151)
            except Exception as e:
                health_info["gpu_error"] = str(e)

        # Capabilities (all types supported via lazy loading)
        health_info["capabilities"].append("image")
        if VIDEO_ENABLED:
            health_info["capabilities"].append("video")
        # Include available video models
        health_info["video_models"] = get_available_video_models()
        health_info["capabilities"].append("assist")  # Prompt assistant

        # Add VRAM prediction info
        try:
            vram_summary = vram_predictor.get_system_summary()
            health_info["vram_prediction"] = {
                "estimated_free_gb": round(
                    vram_summary["current_status"]["free_gb"], 1
                ),
                "estimated_total_gb": round(
                    vram_summary["current_status"]["total_gb"], 1
                ),
                "model_sizes": vram_summary["model_sizes"],
            }
        except Exception as e:
            logger.warning(f"VRAM summary failed: {e}")
            health_info["vram_prediction"] = {"error": str(e)}

        # Platform info
        health_info["platform"] = PLATFORM

        # Report currently loaded model (if any)
        from mydiffuser.inference.state import get_active_model

        active = get_active_model()
        if active:
            health_info["active_model"] = active

        # Report model loading status
        from mydiffuser.inference import state as inference_state

        health_info["models_loaded"] = {
            "image": inference_state.image_generator is not None
            and inference_state.image_generator.is_loaded
            if inference_state.image_generator
            else False,
            "video": inference_state.video_generator is not None
            and inference_state.video_generator.is_loaded
            if inference_state.video_generator
            else False,
            "assistant": inference_state.prompt_assistant is not None
            if inference_state.prompt_assistant
            else False,
        }

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

    @app.post("/unload/{model_type}")
    async def unload_model_endpoint(model_type: str):
        """Unload a specific model to free GPU memory.

        Args:
            model_type: Type of model to unload ("image", "video", or "assistant")

        Returns:
            Status dict with memory info
        """
        # Check if there's a running job
        if job_queue.get_current_job_id():
            raise HTTPException(
                status_code=409, detail="Cannot unload model while a job is running"
            )

        # Validate model type
        if model_type not in ["image", "video", "assistant"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid model_type: {model_type}. Must be 'image', 'video', or 'assistant'",
            )

        try:
            from mydiffuser.inference.state import unload_model

            result = unload_model(model_type)
            return result
        except Exception as e:
            logger.error(f"Failed to unload {model_type} model: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.post("/assist/analyze")
    async def analyze_image_for_prompt_improvement(
        image: UploadFile = File(...),
        current_prompt: str = Form(...),
        user_message: str | None = Form(None),
        max_new_tokens: int = Form(512),
    ):
        """Analyze an image and provide prompt improvement suggestions.

        Args:
            image: Uploaded image file to analyze
            current_prompt: The prompt that generated this image
            user_message: Optional user feedback/issue description
            max_new_tokens: Maximum tokens to generate (default 512)

        Returns:
            Dict with analysis, suggestions, and raw_response
        """

        async with infer_lock:
            try:
                # Load the image
                image_data = await image.read()
                img = Image.open(io.BytesIO(image_data))
                if img.mode != "RGB":
                    img = img.convert("RGB")

                # Lazy load assistant (will swap models if needed)
                from mydiffuser.inference.state import ensure_prompt_assistant

                assistant = ensure_prompt_assistant()

                # Run analysis in executor to avoid blocking
                def analyze():
                    return assistant.analyze_image(
                        image=img,
                        current_prompt=current_prompt,
                        issue=user_message,
                        max_new_tokens=max_new_tokens,
                    )

                result = await asyncio.get_event_loop().run_in_executor(None, analyze)

                # Return the analysis
                return {
                    "analysis": result["analysis"],
                    "suggestions": result["suggestions"],
                    "raw_response": result["raw_response"],
                }

            except Exception as e:
                logger.exception(f"Assist analysis failed: {e}")
                raise HTTPException(status_code=500, detail=f"Analysis failed: {e}") from e

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
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

        # VRAM compatibility check
        try:
            if type == "image":
                from mydiffuser.utils.presets import apply_preset

                request_obj = GenerateImageRequest(**request_data)
                params = apply_preset(request_obj)

                compatibility = vram_predictor.check_compatibility(
                    "image",
                    width=params["width"],
                    height=params["height"],
                    num_inference_steps=params["num_inference_steps"],
                )

            elif type == "video":
                request_obj = GenerateVideoRequest(**request_data)
                params = request_data  # Use raw params for video

                # Calculate frames
                fps = params.get("fps", 12)
                duration = params.get("duration_seconds", 3)
                num_frames = fps * duration

                model_size = params.get("model_size", "5B")
                width = 1280 if "720p" in str(params.get("resolution", "480p")) else 832
                height = 704 if "720p" in str(params.get("resolution", "480p")) else 480

                compatibility = vram_predictor.check_compatibility(
                    "video",
                    model_name="wan-2.1-5b" if model_size == "5B" else "wan-2.1-14b",
                    width=width,
                    height=height,
                    num_frames=num_frames,
                    num_inference_steps=params.get("num_inference_steps", 15),
                )
            else:
                compatibility = {"compatible": True, "recommendations": []}

        except Exception as e:
            logger.warning(f"VRAM check failed: {e}")
            compatibility = {"compatible": True, "recommendations": []}

        if not compatibility["compatible"]:
            logger.warning(
                f"[{job_id}] Job rejected due to insufficient VRAM: {compatibility}"
            )
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Insufficient VRAM",
                    "needed_gb": round(compatibility["needed_gb"], 1),
                    "available_gb": round(compatibility["free_gb"], 1),
                    "recommendations": compatibility["recommendations"],
                },
            )

        # Add job to queue instead of spawning immediately
        if type == "image":
            request = GenerateImageRequest(**request_data)

            # Create executor function for this job
            async def executor():
                await _run_image_job(job_id, request)

            await job_queue.submit(job_id, "image", executor)

        elif type == "video":
            if image is None:
                raise HTTPException(
                    status_code=400, detail="Video jobs require source image"
                )

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
            except InterruptedError:
                # Job was cancelled, already marked as cancelled in callback
                logger.info(f"[{job_id}] Image job cancelled by user")
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
            except InterruptedError:
                # Job was cancelled, already marked as cancelled in callback
                logger.info(f"[{job_id}] Video job cancelled by user")
            except Exception as e:
                logger.exception(f"[{job_id}] Job execution failed")
                state.mark_failed(job_id, str(e))

    @app.get("/jobs")
    async def list_jobs():
        """List recent jobs on this worker (last 10, including completed).

        Returns active jobs plus recently completed ones for client sync.
        Useful for client synchronization after restart.
        """
        all_jobs = []
        for job_id, progress in state.job_progress.items():
            job_data = progress.to_dict()
            job_data["job_id"] = job_id
            all_jobs.append(job_data)

        # Sort by most recent first (using completed_at or started_at)
        all_jobs.sort(
            key=lambda j: (j.get("completed_at") or j.get("started_at") or ""),
            reverse=True,
        )

        # Return last 10 jobs
        recent_jobs = all_jobs[:10]

        return {"jobs": recent_jobs, "count": len(recent_jobs), "total": len(all_jobs)}

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

    @app.post("/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        """Request cancellation of a running job.

        The job will be cancelled between diffusion steps (not immediately).
        Returns 200 if cancellation was requested, 404 if job not found,
        400 if job is already complete/failed/cancelled.
        """
        progress = state.get_progress(job_id)
        if progress is None:
            raise HTTPException(status_code=404, detail="Job not found")

        # Request cancellation
        success = state.request_cancellation(job_id)

        if not success:
            raise HTTPException(
                status_code=400, detail=f"Cannot cancel job in state: {progress.status}"
            )

        return {
            "status": "cancellation_requested",
            "job_id": job_id,
            "message": "Job will be cancelled between diffusion steps",
        }

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

    @app.post("/shutdown")
    async def shutdown_worker():
        """Gracefully shutdown the worker by cancelling jobs and unloading models.

        This endpoint is called by restart-worker.sh to ensure clean GPU cleanup
        before the process is terminated. Prevents GPU from entering D-state.

        Steps:
        1. Cancel any currently running job
        2. Unload all models to free GPU memory
        3. Return success
        4. Exit the process after a brief delay

        Returns:
            Dict with status and cleanup details
        """
        import os
        import signal

        logger.info("Shutdown requested via API")
        result = {
            "status": "ok",
            "message": "Worker shutting down gracefully",
            "cancelled_job": None,
            "models_unloaded": False,
        }

        # Cancel any running job
        current_job_id = job_queue.get_current_job_id()
        if current_job_id:
            logger.info(f"Cancelling running job: {current_job_id}")
            success = state.request_cancellation(current_job_id)
            if success:
                result["cancelled_job"] = current_job_id
                # Give the job a moment to register cancellation
                await asyncio.sleep(0.5)
            else:
                logger.warning(f"Failed to cancel job {current_job_id}")
        else:
            logger.info("No running job to cancel")

        # Unload all models to free GPU memory
        try:
            logger.info("Unloading all models...")
            from mydiffuser.inference.state import unload_all_models

            unload_result = unload_all_models()
            result["models_unloaded"] = True
            result["gpu_memory"] = unload_result.get("gpu_memory", {})
            logger.info("All models unloaded successfully")

            # Additional GPU synchronization after model unload
            # Especially important after cancelled jobs
            import torch
            if torch.cuda.is_available():
                logger.info("Synchronizing GPU after model unload...")
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                logger.info("GPU synchronized")

        except Exception as e:
            logger.error(f"Failed to unload models: {e}")
            result["models_unloaded"] = False
            result["unload_error"] = str(e)

        # Schedule process exit after returning response
        async def delayed_exit():
            await asyncio.sleep(0.5)  # Brief delay to ensure response is sent
            # Additional delay to let ROCm driver complete cleanup
            logger.info("Waiting for ROCm driver cleanup...")
            await asyncio.sleep(2.0)
            logger.info("Exiting worker process (graceful shutdown)")
            os.kill(os.getpid(), signal.SIGTERM)

        asyncio.create_task(delayed_exit())

        logger.info("Graceful shutdown complete - process will exit shortly")
        return result

    return app
