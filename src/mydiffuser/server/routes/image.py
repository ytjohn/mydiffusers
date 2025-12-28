"""Image generation endpoints."""

import io
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from mydiffuser.config import DEVICE, DTYPE, IMAGE_MODEL_ID, LAZY_LOADING, PROJECT_ROOT
from mydiffuser.models.requests import GenerateImageRequest
from mydiffuser.models.responses import GenerateImageResponse
from mydiffuser.server.state import (
    ensure_image_generator,
    get_image_generator,
    get_infer_lock,
)
from mydiffuser.utils.paths import (
    generate_thumbnail,
    new_run_id,
    run_dir,
    write_json,
    write_text,
)
from mydiffuser.utils.presets import apply_preset

logger = logging.getLogger(__name__)

router = APIRouter()


def _generate_and_save(req: GenerateImageRequest) -> tuple[dict, str, Path, Path]:
    """Shared logic: applies preset, runs inference, saves all files.

    Returns:
        Tuple of (metadata_dict, run_id, run_dir_path, output_png_path)
    """
    try:
        params = apply_preset(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    # In lazy loading mode, this will load the model if needed (and swap out video)
    generator = ensure_image_generator() if LAZY_LOADING else get_image_generator()

    # Create run ID and directory (unified structure - no type subfolder)
    rid = new_run_id()
    rd = run_dir(rid)  # New unified path

    # Save inputs
    write_json(rd / "request.json", req.model_dump())
    write_text(rd / "prompt.txt", req.prompt)

    logger.info(
        "Generate preset=%s h=%d w=%d steps=%d guidance=%.2f seed=%d",
        req.preset,
        params["height"],
        params["width"],
        params["num_inference_steps"],
        params["guidance_scale"],
        req.seed,
    )

    img, dt = generator.generate(
        prompt=req.prompt,
        height=params["height"],
        width=params["width"],
        num_inference_steps=params["num_inference_steps"],
        guidance_scale=params["guidance_scale"],
        seed=req.seed,
        run_id=rid,
    )

    out_path = rd / "output.png"
    img.save(out_path)

    # Generate thumbnail at save time
    thumb_path = rd / "thumb.jpg"
    generate_thumbnail(out_path, thumb_path)

    saved_rel = str(out_path.relative_to(PROJECT_ROOT))
    logger.info("Saved %s in %.2fs", saved_rel, dt)

    # Build unified meta.json with type field
    meta = {
        "type": "image",
        "run_id": rid,
        "timestamp": datetime.now(UTC).isoformat(),
        "prompt": req.prompt,
        "source_run_id": None,
        "backend": IMAGE_MODEL_ID,
        "params": {
            "preset": req.preset,
            "seed": req.seed,
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

    # Return flattened meta for API response compatibility
    flat_meta = {
        "seconds": dt,
        "seed": req.seed,
        "preset": req.preset,
        "height": params["height"],
        "width": params["width"],
        "num_inference_steps": params["num_inference_steps"],
        "guidance_scale": params["guidance_scale"],
        "device": DEVICE,
        "dtype": str(DTYPE),
    }

    return flat_meta, rid, rd, out_path


@router.post("/generate", response_model=GenerateImageResponse)
async def generate(req: GenerateImageRequest):
    """Generate an image and return metadata as JSON.

    The image is saved to disk; response includes the path.
    """
    # In lazy loading mode, the model will be loaded during generation
    if not LAZY_LOADING:
        try:
            generator = get_image_generator()
            if not generator.is_loaded:
                raise HTTPException(status_code=503, detail="Model not loaded")
        except RuntimeError:
            raise HTTPException(status_code=503, detail="Model not loaded") from None

    async with get_infer_lock():
        meta, rid, rd, out_path = _generate_and_save(req)

    return GenerateImageResponse(
        run_id=rid,
        run_dir=str(rd.relative_to(PROJECT_ROOT)),
        saved_to=str(out_path.relative_to(PROJECT_ROOT)),
        seconds=meta["seconds"],
        seed=meta["seed"],
        height=meta["height"],
        width=meta["width"],
        num_inference_steps=meta["num_inference_steps"],
        guidance_scale=meta["guidance_scale"],
        preset=meta["preset"],
    )


@router.post("/generate_image")
async def generate_image(req: GenerateImageRequest):
    """Generate an image and return PNG bytes directly.

    Response headers include X-Gen-Meta with generation metadata.
    Also saves the image and metadata to disk.
    """
    # In lazy loading mode, the model will be loaded during generation
    if not LAZY_LOADING:
        try:
            generator = get_image_generator()
            if not generator.is_loaded:
                raise HTTPException(status_code=503, detail="Model not loaded")
        except RuntimeError:
            raise HTTPException(status_code=503, detail="Model not loaded") from None

    async with get_infer_lock():
        meta, _, _, out_path = _generate_and_save(req)

    # Read the saved PNG and return it
    buf = io.BytesIO()
    from PIL import Image
    img = Image.open(out_path)
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"X-Gen-Meta": json.dumps(meta)},
    )
