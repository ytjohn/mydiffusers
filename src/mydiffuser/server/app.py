"""FastAPI application factory."""

import gc
import logging
import signal
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI

from mydiffuser import __version__
from mydiffuser.config import (
    LAZY_LOADING,
    VIDEO_ENABLED,
    configure_torch_backends,
    ensure_output_dirs,
    log_config_summary,
)
from mydiffuser.generators.image import ImageGenerator
from mydiffuser.server import state
from mydiffuser.server.browse_ui import router as browse_ui_router
from mydiffuser.server.routes import browse, health, image, video
from mydiffuser.server.state import check_shutdown, request_shutdown
from mydiffuser.server.ui import router as ui_router
from mydiffuser.server.video_ui import router as video_ui_router

logger = logging.getLogger(__name__)


def _handle_signal(signum: int, frame) -> None:
    """Handle termination signals by setting shutdown flag.

    First signal sets the shutdown flag for graceful shutdown.
    Second signal forces immediate exit.
    """
    sig_name = signal.Signals(signum).name

    if state.is_shutdown_requested():
        # Second signal - force immediate exit
        logger.warning("Received second %s, forcing immediate exit!", sig_name)
        import sys
        sys.exit(1)

    logger.info("Received %s, requesting shutdown...", sig_name)
    logger.info("Press Ctrl+C again to force immediate exit.")
    request_shutdown()


def _cleanup_gpu_memory() -> None:
    """Clear any residual GPU memory from previous runs.

    Call this on startup to ensure we have a clean slate.
    """
    gc.collect()
    if torch.cuda.is_available():

        free_mem = torch.cuda.mem_get_info()[0] / (1024**3)
        total_mem = torch.cuda.mem_get_info()[1] / (1024**3)
        logger.info(
            "GPU memory: %.1f GiB free / %.1f GiB total",
            free_mem, total_mem
        )
        logger.info("GPU memory at startup: %.1f GiB free / %.1f GiB total",
            free_mem, total_mem
        )

        # Clear cached allocations
        torch.cuda.empty_cache()
        # Synchronize to ensure cleanup is complete
        torch.cuda.synchronize()
        # Report available memory
        after_free_mem = torch.cuda.mem_get_info()[0] / (1024**3)
        after_total_mem = torch.cuda.mem_get_info()[1] / (1024**3)
        logger.info(
            "GPU memory after cleanup: %.1f GiB free / %.1f GiB total",
            after_free_mem, after_total_mem
        )
        if after_free_mem > free_mem:
            logger.warning(
                "GPU memory increased after cleanup: %.1f -> %.1f GiB",
                free_mem, after_free_mem
            )
        else:
            logger.info(
                "GPU memory after cleanup: %.1f -> %.1f GiB",
                free_mem, after_free_mem
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown."""
    # --- Startup ---
    logging.basicConfig(level=logging.INFO)

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Log configuration (helps debug ROCm vs CUDA issues)
    log_config_summary()

    # Clean up any residual GPU memory from previous runs
    _cleanup_gpu_memory()

    # Configure torch backends (SDP, etc.)
    configure_torch_backends()

    # Ensure output directories exist
    ensure_output_dirs()

    # In lazy loading mode, defer model loading to first request
    if LAZY_LOADING:
        logger.info(
            "Lazy loading enabled - models will load on first request. "
            "Image and video models will swap as needed."
        )
        if VIDEO_ENABLED:
            logger.info(
                "Video generation available (will load on first /generate_video)"
            )
        else:
            logger.info("Video generation disabled (MYDIFFUSER_VIDEO=0)")
        logger.info("Application startup complete")
        yield

        # Shutdown
        logger.info("Application shutting down...")
        state._unload_all_models()
        logger.info("Application shutdown complete")
        return

    # --- Eager loading mode (default) ---

    # Load and warm up the image generator
    try:
        state.image_generator = ImageGenerator()
        state.image_generator.load_model()
        check_shutdown()  # Check before warmup
        # state.image_generator.warmup()
        state._active_model = "image"
        logger.info("Image generator ready")
    except state.ShutdownRequested:
        logger.info("Shutdown requested during image generator startup")
        yield
        return

    # Optionally load video generator if enabled (non-lazy mode)
    if VIDEO_ENABLED:
        try:
            check_shutdown()  # Check before video loading
            from mydiffuser.generators.video.wan import WanVideoGenerator

            state.video_generator = WanVideoGenerator()
            state.video_generator.load_model()
            check_shutdown()  # Check before warmup
            # state.video_generator.warmup()
            state._active_model = "video"  # Video was loaded last
            logger.info("Video generator ready")
        except state.ShutdownRequested:
            logger.info("Shutdown requested during video generator startup")
            yield
            return
        except Exception as e:
            logger.warning("Video generator failed to load: %s", e)
            logger.info(
                "Video generation disabled. "
                "Install video dependencies to enable."
            )
    else:
        logger.info("Video generation disabled (MYDIFFUSER_VIDEO=0)")

    logger.info("Application startup complete")

    # --- Run ---
    yield

    # --- Shutdown ---
    logger.info("Application shutting down...")

    # Cleanup generators
    if state.image_generator is not None:
        state.image_generator = None
    if state.video_generator is not None:
        state.video_generator = None

    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="mydiffuser",
        description="Image and video generation server for AMD GPUs",
        version=__version__,
        lifespan=lifespan,
    )

    # Include route modules
    app.include_router(health.router, tags=["health"])
    app.include_router(image.router, tags=["image"])
    app.include_router(video.router, tags=["video"])
    app.include_router(browse.router, tags=["browse"])
    app.include_router(ui_router, tags=["ui"])
    app.include_router(browse_ui_router, tags=["ui"])
    app.include_router(video_ui_router, tags=["ui"])

    return app
