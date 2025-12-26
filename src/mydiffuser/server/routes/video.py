"""Video generation endpoints (placeholder for future implementation)."""

from fastapi import APIRouter, HTTPException

from mydiffuser.models.requests import GenerateVideoRequest
from mydiffuser.models.responses import GenerateVideoResponse

router = APIRouter()


@router.post("/generate_video", response_model=GenerateVideoResponse)
async def generate_video(req: GenerateVideoRequest):
    """Generate a video from an image and motion prompt.

    Not yet implemented - requires video generation backend.
    """
    raise HTTPException(
        status_code=501,
        detail="Video generation not yet implemented. "
        "See plan-for-video.md for implementation roadmap.",
    )

