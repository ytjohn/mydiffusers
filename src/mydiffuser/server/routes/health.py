"""Health check endpoint."""

from fastapi import APIRouter

from mydiffuser.config import DEVICE, DTYPE
from mydiffuser.server.state import get_image_generator
from mydiffuser.utils.presets import PRESETS

router = APIRouter()


@router.get("/health")
def health():
    """Return server health status and configuration."""
    try:
        generator = get_image_generator()
        model_loaded = generator.is_loaded
    except RuntimeError:
        model_loaded = False

    return {
        "ok": True,
        "device": DEVICE,
        "dtype": str(DTYPE),
        "model_loaded": model_loaded,
        "presets": PRESETS,
    }
