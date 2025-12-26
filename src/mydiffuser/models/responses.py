"""Response models for API endpoints."""


from pydantic import BaseModel


class GenerateImageResponse(BaseModel):
    """Response model for image generation."""

    run_id: str
    run_dir: str
    saved_to: str | None = None
    seconds: float
    seed: int
    height: int
    width: int
    num_inference_steps: int
    guidance_scale: float
    preset: str


class GenerateVideoResponse(BaseModel):
    """Response model for video generation."""

    run_id: str
    run_dir: str
    saved_to: str
    seconds_elapsed: float
    fps: int
    duration_seconds: float
    num_frames: int
    seed: int
    preset: str
    backend: str

