"""Generation presets for image and video."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mydiffuser.models.requests import GenerateImageRequest, GenerateVideoRequest

# Image generation presets
# Using 16:9 landscape aspect ratio for video-friendly output
# Wan2.2 5B model prefers 1280x704 (720p) or 832x480 (480p)
PRESETS = {
    # Fast iteration preset - 480p landscape (video-friendly)
    "draft": {
        "height": 480,
        "width": 832,
        "num_inference_steps": 4,
        "guidance_scale": 0.0,
    },
    # Higher quality preset - 720p landscape (video-friendly)
    "final": {
        "height": 704,
        "width": 1280,
        "num_inference_steps": 8,
        "guidance_scale": 0.0,
    },
}

# Common aspect ratios for image generation
# These match Wan2.2 video model preferred resolutions
IMAGE_ASPECT_RATIOS = {
    "landscape": {"width": 1280, "height": 704},   # 16:9 landscape 720p
    "portrait": {"width": 704, "height": 1280},    # 9:16 portrait 720p
    "square": {"width": 1024, "height": 1024},     # 1:1 square
    "landscape_480": {"width": 832, "height": 480},  # 16:9 landscape 480p
    "portrait_480": {"width": 480, "height": 832},   # 9:16 portrait 480p
}

# Video generation presets for Wan2.2
# See https://huggingface.co/Wan-AI for available models
VIDEO_PRESETS = {
    # Fast iteration - fewer steps
    "draft": {
        "model": "Wan-AI/Wan2.2-I2V-A14B-Diffusers",
        "fps": 12,
        "duration_seconds": 3,
        "num_inference_steps": 15,
        "guidance_scale": 3.0,
    },
    # Balanced quality
    "final": {
        "model": "Wan-AI/Wan2.2-I2V-A14B-Diffusers",
        "fps": 16,
        "duration_seconds": 5,
        "num_inference_steps": 30,
        "guidance_scale": 3.5,
    },
    # Higher quality - more steps
    "hq": {
        "model": "Wan-AI/Wan2.2-I2V-A14B-Diffusers",
        "fps": 24,
        "duration_seconds": 7,
        "num_inference_steps": 50,
        "guidance_scale": 4.0,
    },
}


def apply_preset(req: "GenerateImageRequest") -> dict:
    """Apply preset defaults and request overrides.

    Returns a dict of effective params (height, width, steps, guidance_scale).
    Request fields override preset values when explicitly provided.

    Priority for dimensions:
    1. aspect_ratio (if specified) - uses VIDEO-friendly dimensions
    2. height/width (if specified) - explicit override
    3. preset defaults

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
            "height": 704,
            "width": 1280,
            "num_inference_steps": 9,
            "guidance_scale": 0.0,
        }

    # Apply aspect ratio if specified (takes priority over preset dimensions)
    if req.aspect_ratio is not None:
        aspect = IMAGE_ASPECT_RATIOS.get(req.aspect_ratio)
        if aspect:
            base["height"] = aspect["height"]
            base["width"] = aspect["width"]

    # Override with explicit request values if provided
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


def apply_video_preset(req: "GenerateVideoRequest") -> dict:
    """Apply video preset defaults and request overrides.

    Returns a dict of effective params for video generation.
    Request fields override preset values when explicitly provided.

    Args:
        req: The video generation request with optional overrides

    Returns:
        Dict with resolved video generation parameters

    Raises:
        ValueError: If parameters fail validation
    """
    if req.preset in ("draft", "final", "hq"):
        base = dict(VIDEO_PRESETS[req.preset])
    else:
        # Custom preset uses draft defaults as base
        base = {
            "model": "Wan-AI/Wan2.1-I2V-1.3B-480P",
            "resolution": "480p",
            "fps": 12,
            "duration_seconds": 5,
            "num_inference_steps": 15,
            "guidance_scale": 3.0,
        }

    # Override with request values if provided
    if req.fps is not None:
        base["fps"] = req.fps
    if req.duration_seconds is not None:
        base["duration_seconds"] = req.duration_seconds
    if req.num_inference_steps is not None:
        base["num_inference_steps"] = req.num_inference_steps
    if req.guidance_scale is not None:
        base["guidance_scale"] = req.guidance_scale

    # Validation - cast to proper types for comparison
    fps_val = base["fps"]
    duration_val = base["duration_seconds"]
    if not isinstance(fps_val, (int, float)) or fps_val < 8 or fps_val > 30:
        raise ValueError("fps must be between 8 and 30")
    valid_duration = isinstance(duration_val, (int, float)) and 1 <= duration_val <= 30
    if not valid_duration:
        raise ValueError("duration_seconds must be between 1 and 30")

    return base

