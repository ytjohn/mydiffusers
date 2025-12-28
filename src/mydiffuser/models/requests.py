"""Request models for API endpoints."""

from typing import Literal

from pydantic import BaseModel, Field

PresetName = Literal["draft", "final", "custom"]
VideoPresetName = Literal["draft", "final", "hq", "custom"]
VideoModelSize = Literal["14B", "5B"]
AspectRatio = Literal["landscape", "portrait", "square"]


class GenerateImageRequest(BaseModel):
    """Request model for text-to-image generation."""

    prompt: str = Field(..., min_length=1)

    preset: PresetName = Field("final", description="draft|final|custom")

    # Aspect ratio - determines dimensions for video-friendly output
    # landscape: 1280x704 (16:9), portrait: 704x1280 (9:16), square: 1024x1024
    aspect_ratio: AspectRatio | None = Field(
        None,
        description="Aspect ratio: landscape (16:9), portrait (9:16), square (1:1)",
    )

    # If preset is draft/final, these can be omitted and defaults come from the preset.
    # If preset is custom, these are used (or their defaults below).
    # Note: aspect_ratio overrides height/width if both are specified.
    height: int | None = Field(None, ge=256, le=2048, multiple_of=8)
    width: int | None = Field(None, ge=256, le=2048, multiple_of=8)

    num_inference_steps: int | None = Field(None, ge=1, le=50)
    guidance_scale: float | None = Field(None, ge=0.0, le=20.0)

    seed: int = Field(42, ge=0, le=2**31 - 1)


class GenerateVideoRequest(BaseModel):
    """Request model for image-to-video generation."""

    # Source image - either from a prior run or a path under outputs/
    source_run_id: str | None = Field(
        None, description="ID of a prior image generation run to use as source"
    )
    image_path: str | None = Field(
        None, description="Path to source image under outputs/"
    )

    prompt: str = Field(
        ...,
        min_length=1,
        description="Motion prompt describing desired animation",
    )

    preset: VideoPresetName = Field("draft", description="draft|final| |custom")

    # Model size selection - 14B (best quality) or 5B (faster, less VRAM)
    model_size: VideoModelSize | None = Field(
        None,
        description="Model size: 14B (~28GB, best) or 5B (~10GB, 720p)",
    )

    duration_seconds: float | None = Field(None, ge=1.0, le=30.0)
    fps: int | None = Field(None, ge=8, le=30)

    num_inference_steps: int | None = Field(None, ge=1, le=100)
    guidance_scale: float | None = Field(None, ge=0.0, le=20.0)

    seed: int = Field(42, ge=0, le=2**31 - 1)

