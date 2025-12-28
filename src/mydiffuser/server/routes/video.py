"""Video generation endpoints."""

import logging
import shutil
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from PIL import Image

from mydiffuser.config import (
    DEVICE,
    DTYPE,
    LAZY_LOADING,
    PROJECT_ROOT,
    VIDEO_MODEL_SIZE,
    VIDEO_MODELS,
)
from mydiffuser.models.requests import GenerateVideoRequest
from mydiffuser.models.responses import GenerateVideoResponse
from mydiffuser.server.state import (
    ensure_video_generator,
    get_infer_lock,
    get_video_generator,
)
from mydiffuser.utils.paths import (
    find_run_dir,
    generate_thumbnail,
    new_run_id,
    run_dir,
    write_json,
    write_text,
)
from mydiffuser.utils.presets import apply_video_preset

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_source_image(req: GenerateVideoRequest) -> tuple["Image.Image", str | None]:
    """Get the source image from either source_run_id or image_path.

    Returns:
        Tuple of (PIL Image, source_run_id or None)

    Raises:
        HTTPException: If source cannot be found or loaded
    """
    source_run_id = None

    if req.source_run_id:
        # Load from a prior run
        source_dir = find_run_dir(req.source_run_id)
        if source_dir is None:
            raise HTTPException(
                status_code=404,
                detail=f"Source run not found: {req.source_run_id}",
            )

        # Try to find the output image
        output_path = source_dir / "output.png"
        if not output_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Source run has no output image: {req.source_run_id}",
            )

        source_run_id = req.source_run_id
        image_path = output_path

    elif req.image_path:
        # Load from explicit path (must be under outputs/)
        from mydiffuser.utils.paths import safe_under_outputs

        try:
            image_path = safe_under_outputs(req.image_path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

        if not image_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Image not found: {req.image_path}",
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="Either source_run_id or image_path must be provided",
        )

    # Load the image
    try:
        loaded_img: Image.Image = Image.open(image_path)
        if loaded_img.mode != "RGB":
            loaded_img = loaded_img.convert("RGB")
        return loaded_img, source_run_id
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to load source image: {e}",
        ) from None


@router.post("/generate_video", response_model=GenerateVideoResponse)
async def generate_video(req: GenerateVideoRequest) -> GenerateVideoResponse:
    """Generate a video from an image and motion prompt.

    The source image can be specified either by:
    - source_run_id: ID of a prior image generation run
    - image_path: Path to an image under outputs/

    The video is saved to a new run directory.
    """
    # In lazy loading mode, the generator will be loaded during inference
    # In eager mode, check if video is available before proceeding
    if not LAZY_LOADING:
        try:
            generator = get_video_generator()
            if not generator.is_loaded:
                raise HTTPException(
                    status_code=503,
                    detail="Video model not loaded. "
                    "Video generation may not be enabled on this server.",
                )
        except RuntimeError:
            raise HTTPException(
                status_code=503,
                detail="Video generation not available. "
                "Check that video dependencies are installed.",
            ) from None

    # Apply preset and get resolved params
    try:
        params = apply_video_preset(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    # Get source image
    source_image, source_run_id = _get_source_image(req)

    # Create run directory (unified structure)
    rid = new_run_id()
    rd = run_dir(rid)

    # Copy source image to run directory
    input_path = rd / "input.png"
    source_image.save(input_path, "PNG")

    # Save request and prompt
    write_json(rd / "request.json", req.model_dump())
    write_text(rd / "prompt.txt", req.prompt)

    output_path = rd / "output.mp4"

    # Determine which model to use
    model_size = req.model_size or VIDEO_MODEL_SIZE
    model_id = VIDEO_MODELS.get(model_size, VIDEO_MODELS["14B"])

    logger.info(
        "Generate video preset=%s model=%s fps=%d duration=%.1fs steps=%d seed=%d",
        req.preset,
        model_size,
        params["fps"],
        params["duration_seconds"],
        params["num_inference_steps"],
        req.seed,
    )

    # Run generation with inference lock
    async with get_infer_lock():
        # In lazy mode, load video model now (swaps out image model if needed)
        # Pass the model_id to allow dynamic model switching
        generator = (
            ensure_video_generator(model_id=model_id)
            if LAZY_LOADING
            else get_video_generator()
        )

        try:
            _, elapsed, num_frames = generator.generate(
                input_image=source_image,
                prompt=req.prompt,
                fps=params["fps"],
                duration_seconds=params["duration_seconds"],
                num_inference_steps=params["num_inference_steps"],
                guidance_scale=params["guidance_scale"],
                seed=req.seed,
                output_path=output_path,
                run_id=rid,
            )
        except Exception as e:
            # Clean up on failure
            try:
                shutil.rmtree(rd)
            except Exception:
                pass
            raise HTTPException(
                status_code=500, detail=f"Video generation failed: {e}"
            ) from None

    # Generate thumbnail from input image
    thumb_path = rd / "thumb.jpg"
    generate_thumbnail(input_path, thumb_path)

    # Save metadata
    meta = {
        "type": "video",
        "run_id": rid,
        "timestamp": datetime.now(UTC).isoformat(),
        "prompt": req.prompt,
        "source_run_id": source_run_id,
        "backend": model_id,
        "model_size": model_size,
        "params": {
            "preset": req.preset,
            "seed": req.seed,
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

    saved_rel = str(output_path.relative_to(PROJECT_ROOT))
    logger.info("Saved video %s in %.2fs (%d frames)", saved_rel, elapsed, num_frames)

    return GenerateVideoResponse(
        run_id=rid,
        run_dir=str(rd.relative_to(PROJECT_ROOT)),
        saved_to=saved_rel,
        seconds_elapsed=elapsed,
        fps=params["fps"],
        duration_seconds=params["duration_seconds"],
        num_frames=num_frames,
        seed=req.seed,
        preset=req.preset,
        source_run_id=source_run_id,
    )
