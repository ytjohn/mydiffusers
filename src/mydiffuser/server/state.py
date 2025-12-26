"""Shared server state to avoid circular imports."""

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mydiffuser.generators.image import ImageGenerator

# Global generator instance (loaded at startup)
image_generator: "ImageGenerator | None" = None

# Lock to serialize inference (GPU can only do one at a time)
infer_lock = asyncio.Lock()


def get_image_generator() -> "ImageGenerator":
    """Get the loaded image generator instance."""
    if image_generator is None:
        raise RuntimeError("Image generator not loaded")
    return image_generator


def get_infer_lock() -> asyncio.Lock:
    """Get the inference lock for serializing GPU access."""
    return infer_lock

