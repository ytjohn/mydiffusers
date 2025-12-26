"""Request models for API endpoints."""

from typing import Literal

from pydantic import BaseModel, Field

PresetName = Literal["draft", "final", "custom"]


class GenerateImageRequest(BaseModel):
    """Request model for text-to-image generation."""

    prompt: str = Field(..., min_length=1)

    preset: PresetName = Field("final", description="draft|final|custom")

    # If preset is draft/final, these can be omitted and defaults come from the preset.
    # If preset is custom, these are used (or their defaults below).
    height: int | None = Field(None, ge=256, le=2048, multiple_of=8)
    width: int | None = Field(None, ge=256, le=2048, multiple_of=8)

    num_inference_steps: int | None = Field(None, ge=1, le=50)
    guidance_scale: float | None = Field(None, ge=0.0, le=20.0)

    seed: int = Field(42, ge=0, le=2**31 - 1)


class GenerateVideoRequest(BaseModel):
    """Request model for image-to-video generation."""

    # Source image - either from a prior run or a path under outputs/
    image_run_id: str | None = Field(
        None, description="UUID of a prior image generation run"
    )
    image_path: str | None = Field(
        None, description="Path to source image under outputs/"
    )

    prompt: str = Field(
        ...,
        min_length=1,
        description="Motion prompt describing desired animation",
    )

    preset: PresetName = Field("draft", description="draft|final|custom")

    duration_seconds: float | None = Field(None, ge=1.0, le=30.0)
    fps: int | None = Field(None, ge=8, le=30)

    num_inference_steps: int | None = Field(None, ge=1, le=100)
    guidance_scale: float | None = Field(None, ge=0.0, le=20.0)

    seed: int = Field(42, ge=0, le=2**31 - 1)

    backend: str = Field("svd", description="Video generation backend: svd|tuneavideo")

