"""FastAPI application factory."""

import logging

from fastapi import FastAPI

from mydiffuser import __version__
from mydiffuser.config import configure_torch_backends, ensure_output_dirs
from mydiffuser.generators.image import ImageGenerator
from mydiffuser.server import state
from mydiffuser.server.routes import health, image
from mydiffuser.server.ui import router as ui_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="mydiffuser",
        description="Image and video generation server for AMD GPUs",
        version=__version__,
    )

    # Include route modules
    app.include_router(health.router, tags=["health"])
    app.include_router(image.router, tags=["image"])
    app.include_router(ui_router, tags=["ui"])

    @app.on_event("startup")
    def startup():
        """Initialize the application on startup."""
        # Setup logging
        logging.basicConfig(level=logging.INFO)

        # Configure torch for AMD
        configure_torch_backends()

        # Ensure output directories exist
        ensure_output_dirs()

        # Load and warm up the image generator
        state.image_generator = ImageGenerator()
        state.image_generator.load_model()
        state.image_generator.warmup()

        logger.info("Application startup complete")

    return app
