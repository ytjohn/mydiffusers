"""Shared inference state for model management.

This module manages GPU model loading, unloading, and lazy loading
for both image and video generation. Used by both the worker and
the legacy server.
"""

import asyncio
import gc
import logging
from typing import TYPE_CHECKING, Literal

import torch

from mydiffuser.config import LAZY_LOADING

if TYPE_CHECKING:
    from mydiffuser.generators.image import ImageGenerator
    from mydiffuser.generators.video.wan import WanVideoGenerator
    from mydiffuser.inference.assistant import PromptAssistant

logger = logging.getLogger(__name__)

# Global generator instances (loaded at startup or on-demand)
image_generator: "ImageGenerator | None" = None
video_generator: "WanVideoGenerator | None" = None
prompt_assistant: "PromptAssistant | None" = None

# Track which model type is currently loaded (for lazy loading)
_active_model: Literal["image", "video", "assistant", None] = None

# Lock to serialize inference (GPU can only do one at a time)
infer_lock = asyncio.Lock()


def _unload_all_models() -> None:
    """Unload all models and free GPU memory aggressively.

    This performs multiple rounds of garbage collection and cache clearing
    to ensure all GPU memory is released before loading a new model.
    """
    global image_generator, video_generator, prompt_assistant, _active_model

    if image_generator is not None:
        logger.info("Unloading image generator...")
        image_generator.unload()  # Properly unload (moves to CPU, deletes, gc)
        image_generator = None

    if video_generator is not None:
        logger.info("Unloading video generator...")
        video_generator.unload()  # Properly unload (moves to CPU, deletes, gc)
        video_generator = None

    if prompt_assistant is not None:
        logger.info("Unloading prompt assistant...")
        prompt_assistant.unload()
        prompt_assistant = None

    _active_model = None

    # Aggressive memory cleanup - multiple rounds
    # This helps with memory fragmentation on AMD ROCm
    if torch.cuda.is_available():
        # First round
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

        # Second round - catches any lazy deallocations
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

        # Third round with IPC collect if available
        gc.collect()
        torch.cuda.empty_cache()
        try:
            torch.cuda.ipc_collect()  # Collect IPC memory
        except AttributeError:
            pass  # Not available on all PyTorch versions
        torch.cuda.synchronize()

        # Report memory status
        import time
        time.sleep(0.5)  # Brief pause to let GPU settle
        free_mem = torch.cuda.mem_get_info()[0] / (1024**3)
        total_mem = torch.cuda.mem_get_info()[1] / (1024**3)
        logger.info(
            "GPU memory after cleanup: %.1f GiB free / %.1f GiB total",
            free_mem, total_mem
        )
    else:
        gc.collect()

    logger.info("GPU memory cleared")


def ensure_image_generator() -> "ImageGenerator":
    """Get the image generator, loading it if necessary (lazy loading).

    In lazy loading mode, this will unload the video generator first
    to free GPU memory. Warmup is skipped since the first real request
    serves the same purpose.
    """
    global image_generator, _active_model

    if image_generator is not None and image_generator.is_loaded:
        return image_generator

    # In lazy mode, unload other models first
    if LAZY_LOADING and _active_model == "video":
        logger.info("Lazy loading: swapping video → image model")
        _unload_all_models()

    # Load the image generator (skip warmup - first request is the warmup)
    from mydiffuser.generators.image import ImageGenerator

    logger.info("Loading image generator (lazy, no warmup)...")
    image_generator = ImageGenerator()
    image_generator.load_model()
    # Skip warmup in lazy mode - the real request will be the first inference
    _active_model = "image"
    logger.info("Image generator ready")

    return image_generator


def ensure_video_generator(model_id: str | None = None) -> "WanVideoGenerator":
    """Get the video generator, loading it if necessary (lazy loading).

    In lazy loading mode, this will unload the image generator first
    to free GPU memory. Warmup is skipped since the first real request
    serves the same purpose.

    Args:
        model_id: Optional model ID to load. If the current generator has a
            different model loaded, it will be swapped. Defaults to VIDEO_MODEL_ID.
    """
    global video_generator, _active_model

    from mydiffuser.config import VIDEO_MODEL_ID

    target_model = model_id or VIDEO_MODEL_ID

    # Check if we already have the right model loaded
    if video_generator is not None and video_generator.is_loaded:
        if video_generator.model_id == target_model:
            return video_generator
        else:
            # Different model requested, need to swap
            logger.info(
                "Video model swap: %s → %s",
                video_generator.model_id, target_model
            )
            _unload_all_models()

    # In lazy mode, unload other models first
    if LAZY_LOADING and _active_model == "image":
        logger.info("Lazy loading: swapping image → video model")
        _unload_all_models()

    # Load the video generator (skip warmup - first request is the warmup)
    from mydiffuser.generators.video.wan import WanVideoGenerator

    logger.info("Loading video generator (lazy, no warmup): %s", target_model)
    video_generator = WanVideoGenerator(model_id=target_model)
    video_generator.load_model()
    # Skip warmup in lazy mode - the real request will be the first inference
    _active_model = "video"
    logger.info("Video generator ready")

    return video_generator


def get_image_generator() -> "ImageGenerator":
    """Get the loaded image generator instance.

    Use ensure_image_generator() for lazy loading support.
    """
    if image_generator is None:
        raise RuntimeError("Image generator not loaded")
    return image_generator


def get_video_generator() -> "WanVideoGenerator":
    """Get the loaded video generator instance.

    Use ensure_video_generator() for lazy loading support.
    """
    if video_generator is None:
        raise RuntimeError("Video generator not loaded")
    return video_generator


def get_infer_lock() -> asyncio.Lock:
    """Get the inference lock for serializing GPU access."""
    return infer_lock


def get_active_model() -> Literal["image", "video", "assistant", None]:
    """Get the currently active model type."""
    return _active_model


def ensure_prompt_assistant() -> "PromptAssistant":
    """Get the prompt assistant, loading it if necessary.

    The assistant can coexist with the image generator (~34GB total).
    It will be unloaded when video generation is requested.

    Returns:
        Loaded PromptAssistant instance
    """
    global prompt_assistant, _active_model

    if prompt_assistant is not None:
        return prompt_assistant

    # In lazy mode, only unload video generator (assistant can coexist with image gen)
    if LAZY_LOADING and _active_model == "video":
        logger.info("Lazy loading: unloading video model for assistant")
        _unload_all_models()

    # Load the assistant
    from mydiffuser.inference.assistant import PromptAssistant

    logger.info("Loading prompt assistant...")
    prompt_assistant = PromptAssistant()
    prompt_assistant.load()
    _active_model = "assistant"
    logger.info("Prompt assistant ready")

    return prompt_assistant


def get_prompt_assistant() -> "PromptAssistant":
    """Get the loaded prompt assistant instance.

    Use ensure_prompt_assistant() for lazy loading support.
    """
    if prompt_assistant is None:
        raise RuntimeError("Prompt assistant not loaded")
    return prompt_assistant


def unload_all_models() -> dict:
    """Public API to unload all models and free GPU memory.

    Returns a dict with status and memory info.
    """
    _unload_all_models()

    result = {"status": "ok", "message": "All models unloaded"}

    if torch.cuda.is_available():
        free_mem = torch.cuda.mem_get_info()[0] / (1024**3)
        total_mem = torch.cuda.mem_get_info()[1] / (1024**3)
        result["gpu_memory"] = {
            "free_gib": round(free_mem, 1),
            "total_gib": round(total_mem, 1),
        }

    return result


def unload_model(model_type: Literal["image", "video", "assistant"]) -> dict:
    """Unload a specific model and free its GPU memory.

    Args:
        model_type: Type of model to unload ("image", "video", or "assistant")

    Returns:
        Dict with status and memory info

    Raises:
        ValueError: If model_type is invalid
    """
    global image_generator, video_generator, prompt_assistant, _active_model

    if model_type == "image":
        if image_generator is None:
            return {"status": "ok", "message": "Image model not loaded"}
        logger.info("Unloading image generator...")
        image_generator.unload()
        image_generator = None
        if _active_model == "image":
            _active_model = None
        message = "Image model unloaded"

    elif model_type == "video":
        if video_generator is None:
            return {"status": "ok", "message": "Video model not loaded"}
        logger.info("Unloading video generator...")
        video_generator.unload()
        video_generator = None
        if _active_model == "video":
            _active_model = None
        message = "Video model unloaded"

    elif model_type == "assistant":
        if prompt_assistant is None:
            return {"status": "ok", "message": "Assistant model not loaded"}
        logger.info("Unloading prompt assistant...")
        prompt_assistant.unload()
        prompt_assistant = None
        if _active_model == "assistant":
            _active_model = None
        message = "Assistant model unloaded"

    else:
        raise ValueError(f"Invalid model_type: {model_type}")

    # Cleanup GPU memory
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

    result = {"status": "ok", "message": message}

    if torch.cuda.is_available():
        free_mem = torch.cuda.mem_get_info()[0] / (1024**3)
        total_mem = torch.cuda.mem_get_info()[1] / (1024**3)
        result["gpu_memory"] = {
            "free_gib": round(free_mem, 1),
            "total_gib": round(total_mem, 1),
        }

    return result


# Re-export shutdown functions for backwards compatibility
