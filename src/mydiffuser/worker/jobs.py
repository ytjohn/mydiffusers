"""Job execution logic for worker.

Handles running image and video generation tasks with progress tracking.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from mydiffuser.config import DEVICE, DTYPE, GPU_ARCH, GPU_NAME
from mydiffuser.models.requests import GenerateImageRequest, GenerateVideoRequest
from mydiffuser.utils.paths import (
    generate_thumbnail,
    new_run_id,
    worker_run_dir,
    write_json,
    write_text,
)
from mydiffuser.utils.presets import apply_preset, apply_video_preset
from mydiffuser.worker import state

if TYPE_CHECKING:
    from mydiffuser.generators.image import ImageGenerator
    from mydiffuser.generators.video.wan import WanVideoGenerator

logger = logging.getLogger(__name__)


def _create_step_callback(job_id: str, total_steps: int):
    """Create a callback function for PyTorch pipeline step updates.

    The callback checks for cancellation between steps and signals the pipeline to stop.
    """

    def callback(pipe, step_index: int, timestep, callback_kwargs):
        # Check for cancellation first
        if state.is_cancelled(job_id):
            logger.info(f"[{job_id}] Cancellation detected at step {step_index + 1}/{total_steps}")
            # Signal pipeline to stop by returning None or empty dict
            # Different pipelines handle this differently,
            # so we'll handle cleanup in execute_* functions
            # For now, just mark as cancelled and let the exception bubble up
            state.mark_cancelled(job_id)
            # Raise an exception to stop generation immediately
            raise InterruptedError(f"Job {job_id} cancelled by user")

        # Check if this is a post-processing phase (VAE decode)
        if isinstance(callback_kwargs, dict) and callback_kwargs.get("phase") == "vae_decode":
            state.update_step(
                job_id, total_steps, "Post-processing (VAE decode)..."
            )
        else:
            # Normal inference step
            state.update_step(
                job_id, step_index + 1, f"Inference step {step_index + 1}/{total_steps}"
            )
        return callback_kwargs

    return callback


def execute_image_job(
    job_id: str,
    request: GenerateImageRequest,
    generator: "ImageGenerator",
) -> tuple[str, Path]:
    """Execute an image generation job.

    Args:
        job_id: Unique job identifier
        request: Image generation request
        generator: Loaded image generator instance

    Returns:
        Tuple of (run_id, run_directory_path)

    Raises:
        Exception: If generation fails
    """
    try:
        # Apply preset
        params = apply_preset(request)

        # Initialize progress tracking
        state.init_job(job_id, params["num_inference_steps"])

        # Create run ID and directory (worker temp storage)
        rid = new_run_id()
        rd = worker_run_dir(rid)

        # Save inputs
        write_json(rd / "request.json", request.model_dump())
        write_text(rd / "prompt.txt", request.prompt)

        logger.info(
            f"[{job_id}] Starting image generation: preset={request.preset} "
            f"h={params['height']} w={params['width']} steps={params['num_inference_steps']} "
            f"guidance={params['guidance_scale']:.2f} seed={request.seed}"
        )

        # Create callback for progress updates
        callback = _create_step_callback(job_id, params["num_inference_steps"])

        # Run generation
        img, dt, vram_data, timing_breakdown = generator.generate(
            prompt=request.prompt,
            height=params["height"],
            width=params["width"],
            num_inference_steps=params["num_inference_steps"],
            guidance_scale=params["guidance_scale"],
            seed=request.seed,
            run_id=rid,
            callback_on_step_end=callback,
        )

        # Save output
        out_path = rd / "output.png"
        img.save(out_path)

        # Generate thumbnail
        thumb_path = rd / "thumb.jpg"
        generate_thumbnail(out_path, thumb_path)

        # Save metadata
        meta = {
            "type": "image",
            "run_id": rid,
            "timestamp": datetime.now(UTC).isoformat(),
            "prompt": request.prompt,
            "tags": request.tags,
            "source_run_id": None,
            "backend": generator.model_id if hasattr(generator, "model_id") else "z-image",
            "params": {
                "preset": request.preset,
                "seed": request.seed,
                "height": params["height"],
                "width": params["width"],
                "num_inference_steps": params["num_inference_steps"],
                "guidance_scale": params["guidance_scale"],
                "model_id": generator.model_id if hasattr(generator, "model_id") else None,
            },
            "outputs": {
                "image": "output.png",
                "thumb": "thumb.jpg",
            },
            "device": DEVICE,
            "dtype": str(DTYPE),
            "gpu_name": GPU_NAME,
            "gpu_arch": GPU_ARCH,
            "seconds_elapsed": dt,
            "vram_used": vram_data.get("allocated", 0.0),
            "vram_reserved": vram_data.get("reserved", 0.0),
            "timing": timing_breakdown,
        }
        write_json(rd / "meta.json", meta)

        logger.info(f"[{job_id}] Image generation complete in {dt:.2f}s -> {rid}")

        # Mark job complete
        state.mark_complete(job_id, rid, dt, "Image generation complete")

        return rid, rd

    except InterruptedError:
        # Job was cancelled by user - ensure GPU operations complete
        logger.info(f"[{job_id}] Image generation cancelled")

        # Critical: Synchronize GPU to ensure all kernels complete
        # Cancelling mid-inference can leave GPU in bad state if not synced
        try:
            import torch
            if torch.cuda.is_available():
                logger.info(f"[{job_id}] Synchronizing GPU after cancellation...")
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                logger.info(f"[{job_id}] GPU synchronized successfully")
        except Exception as e:
            logger.warning(f"[{job_id}] GPU sync after cancellation failed: {e}")

        # State is already marked as cancelled by the callback
        raise

    except Exception as e:
        # Cleanup GPU before propagating exception to prevent state accumulation
        try:
            import torch
            if torch.cuda.is_available():
                logger.info(f"[{job_id}] Synchronizing GPU after failure...")
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                logger.info(f"[{job_id}] GPU synchronized successfully")
        except Exception as cleanup_error:
            logger.warning(f"[{job_id}] GPU sync after failure failed: {cleanup_error}")

        logger.exception(f"[{job_id}] Image generation failed")
        state.mark_failed(job_id, str(e))
        raise


def execute_video_job(
    job_id: str,
    request: GenerateVideoRequest,
    source_image: Image.Image,
    generator: "WanVideoGenerator",
) -> tuple[str, Path]:
    """Execute a video generation job.

    Args:
        job_id: Unique job identifier
        request: Video generation request
        source_image: Source image for I2V
        generator: Loaded video generator instance

    Returns:
        Tuple of (run_id, run_directory_path)

    Raises:
        Exception: If generation fails
    """
    try:
        # Apply preset
        params = apply_video_preset(request)

        # Initialize progress tracking
        state.init_job(job_id, params["num_inference_steps"])

        # Create run ID and directory (worker temp storage)
        rid = new_run_id()
        rd = worker_run_dir(rid)

        # Save source image
        input_path = rd / "input.png"
        source_image.save(input_path, "PNG")

        # Save inputs
        write_json(rd / "request.json", request.model_dump())
        write_text(rd / "prompt.txt", request.prompt)

        logger.info(
            f"[{job_id}] Starting video generation: preset={request.preset} "
            f"fps={params['fps']} duration={params['duration_seconds']}s "
            f"steps={params['num_inference_steps']} resolution={params.get('resolution', '480p')} "
            f"seed={request.seed}"
        )

        # Create callback for progress updates
        callback = _create_step_callback(job_id, params["num_inference_steps"])

        # Run generation
        output_path = rd / "output.mp4"
        _, elapsed, num_frames, vram_data, timing_breakdown = generator.generate(
            input_image=source_image,
            prompt=request.prompt,
            fps=params["fps"],
            duration_seconds=params["duration_seconds"],
            num_inference_steps=params["num_inference_steps"],
            guidance_scale=params["guidance_scale"],
            seed=request.seed,
            output_path=output_path,
            run_id=rid,
            resolution=params.get("resolution", "480p"),
            callback_on_step_end=callback,
        )

        # Generate thumbnail from input image
        thumb_path = rd / "thumb.jpg"
        generate_thumbnail(input_path, thumb_path)

        # Calculate actual output dimensions based on resolution and aspect ratio
        resolution_str = params.get("resolution", "480p")
        img_width, img_height = source_image.size
        is_landscape = img_width >= img_height
        if resolution_str == "720p":
            video_width, video_height = (1280, 704) if is_landscape else (704, 1280)
        else:  # 480p (default)
            video_width, video_height = (832, 480) if is_landscape else (480, 832)

        # Save metadata
        meta = {
            "type": "video",
            "run_id": rid,
            "timestamp": datetime.now(UTC).isoformat(),
            "prompt": request.prompt,
            "tags": request.tags,
            "source_run_id": request.source_run_id,
            "backend": generator.model_id if hasattr(generator, "model_id") else "wan2.2",
            "params": {
                "preset": request.preset,
                "seed": request.seed,
                "resolution": resolution_str,
                "width": video_width,
                "height": video_height,
                "fps": params["fps"],
                "duration_seconds": params["duration_seconds"],
                "num_inference_steps": params["num_inference_steps"],
                "guidance_scale": params["guidance_scale"],
                "model_id": generator.model_id if hasattr(generator, "model_id") else None,
            },
            "outputs": {
                "video": "output.mp4",
                "input": "input.png",
                "thumb": "thumb.jpg",
            },
            "device": DEVICE,
            "dtype": str(DTYPE),
            "gpu_name": GPU_NAME,
            "gpu_arch": GPU_ARCH,
            "seconds_elapsed": elapsed,
            "num_frames": num_frames,
            "vram_used": vram_data.get("allocated", 0.0),
            "vram_reserved": vram_data.get("reserved", 0.0),
            "timing": timing_breakdown,
        }
        write_json(rd / "meta.json", meta)

        logger.info(f"[{job_id}] Video generation complete in {elapsed:.2f}s -> {rid}")

        # Mark job complete
        state.mark_complete(job_id, rid, elapsed, "Video generation complete")

        return rid, rd

    except InterruptedError:
        # Job was cancelled by user - ensure GPU operations complete
        logger.info(f"[{job_id}] Video generation cancelled")

        # Critical: Synchronize GPU to ensure all kernels complete
        # Cancelling mid-inference can leave GPU in bad state if not synced
        try:
            import torch
            if torch.cuda.is_available():
                logger.info(f"[{job_id}] Synchronizing GPU after cancellation...")
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                logger.info(f"[{job_id}] GPU synchronized successfully")
        except Exception as e:
            logger.warning(f"[{job_id}] GPU sync after cancellation failed: {e}")

        # State is already marked as cancelled by the callback
        raise

    except Exception as e:
        # Cleanup GPU before propagating exception to prevent state accumulation
        try:
            import torch
            if torch.cuda.is_available():
                logger.info(f"[{job_id}] Synchronizing GPU after failure...")
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                logger.info(f"[{job_id}] GPU synchronized successfully")
        except Exception as cleanup_error:
            logger.warning(f"[{job_id}] GPU sync after failure failed: {cleanup_error}")

        logger.exception(f"[{job_id}] Video generation failed")
        state.mark_failed(job_id, str(e))
        raise
