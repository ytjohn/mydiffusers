"""Generation presets for image and video."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mydiffuser.models.requests import GenerateImageRequest

# Image generation presets
PRESETS = {
    # Fast iteration preset
    "draft": {
        "height": 832,
        "width": 832,
        "num_inference_steps": 4,
        "guidance_scale": 0.0,
    },
    # Higher quality preset
    "final": {
        "height": 1024,
        "width": 1024,
        "num_inference_steps": 8,
        "guidance_scale": 0.0,
    },
}

# Video generation presets (for future use)
VIDEO_PRESETS = {
    "draft": {
        "fps": 12,
        "duration_seconds": 5,
        "num_inference_steps": 15,
        "guidance_scale": 3.0,
    },
    "final": {
        "fps": 16,
        "duration_seconds": 7,
        "num_inference_steps": 25,
        "guidance_scale": 3.0,
    },
}


def apply_preset(req: "GenerateImageRequest") -> dict:
    """Apply preset defaults and request overrides.

    Returns a dict of effective params (height, width, steps, guidance_scale).
    Request fields override preset values when explicitly provided.

    Args:
        req: The generation request with optional overrides

    Returns:
        Dict with resolved generation parameters

    Raises:
        ValueError: If parameters fail validation
    """
    if req.preset in ("draft", "final"):
        base = dict(PRESETS[req.preset])
    else:
        # Custom preset uses final defaults as base
        base = {
            "height": 1024,
            "width": 1024,
            "num_inference_steps": 9,
            "guidance_scale": 0.0,
        }

    # Override with request values if provided
    if req.height is not None:
        base["height"] = req.height
    if req.width is not None:
        base["width"] = req.width
    if req.num_inference_steps is not None:
        base["num_inference_steps"] = req.num_inference_steps
    if req.guidance_scale is not None:
        base["guidance_scale"] = req.guidance_scale

    # Validation
    h, w = base["height"], base["width"]
    if h % 8 != 0 or w % 8 != 0:
        raise ValueError("height and width must be multiples of 8")
    if not (256 <= h <= 2048 and 256 <= w <= 2048):
        raise ValueError("height/width must be within 256..2048")

    return base

