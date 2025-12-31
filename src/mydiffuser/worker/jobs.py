"""Job execution logic for worker.

Handles running image and video generation tasks with progress tracking.
"""

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from mydiffuser.config import DEVICE, DTYPE, PROJECT_ROOT
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
    """Create a callback function for PyTorch pipeline step updates."""

    def callback(pipe, step_index: int, timestep, callback_kwargs):
        # Check if this is a post-processing phase (VAE decode)
        if isinstance(callback_kwargs, dict) and callback_kwargs.get("phase") == "vae_decode":
            state.update_step(
                job_id, total_steps, f"Post-processing (VAE decode)..."
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
        img, dt = generator.generate(
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
            },
            "outputs": {
                "image": "output.png",
                "thumb": "thumb.jpg",
            },
            "device": DEVICE,
            "dtype": str(DTYPE),
            "seconds_elapsed": dt,
        }
        write_json(rd / "meta.json", meta)

        logger.info(f"[{job_id}] Image generation complete in {dt:.2f}s -> {rid}")

        # Mark job complete
        state.mark_complete(job_id, rid, dt, "Image generation complete")

        return rid, rd

    except Exception as e:
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
        _, elapsed, num_frames = generator.generate(
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
                "resolution": params.get("resolution", "480p"),
                "fps": params["fps"],
                "duration_seconds": params["duration_seconds"],
                "num_inference_steps": params["num_inference_steps"],
                "guidance_scale": params["guidance_scale"],
            },
            "outputs": {
                "video": "output.mp4",
                "input": "input.png",
                "thumb": "thumb.jpg",
            },
            "device": DEVICE,
            "dtype": str(DTYPE),
            "seconds_elapsed": elapsed,
            "num_frames": num_frames,
        }
        write_json(rd / "meta.json", meta)

        logger.info(f"[{job_id}] Video generation complete in {elapsed:.2f}s -> {rid}")

        # Mark job complete
        state.mark_complete(job_id, rid, elapsed, "Video generation complete")

        return rid, rd

    except Exception as e:
        logger.exception(f"[{job_id}] Video generation failed")
        state.mark_failed(job_id, str(e))
        raise
