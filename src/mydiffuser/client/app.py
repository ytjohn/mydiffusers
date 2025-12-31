"""Client FastAPI application (UI without PyTorch dependencies).

This is a lightweight UI server that:
- Provides browsing interface for viewing results
- Submits jobs to remote workers via HTTP
- Fetches results from workers and saves locally
- Has NO PyTorch/GPU dependencies (can run anywhere)
"""

import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from mydiffuser import __version__
from mydiffuser.config import ensure_output_dirs

logger = logging.getLogger(__name__)

# Get path to static files and templates
CLIENT_DIR = Path(__file__).parent
STATIC_DIR = CLIENT_DIR / "static"
TEMPLATES_DIR = CLIENT_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager (startup/shutdown)."""
    # Startup
    logger.info("Client UI server starting up...")

    # Ensure output directories exist
    ensure_output_dirs()

    # Initialize SQLite database
    from mydiffuser.client import database
    database.init_database()
    logger.info("SQLite database initialized")

    logger.info("Client UI startup complete (no models loaded)")

    yield

    # Shutdown
    logger.info("Client UI server shutting down...")


def create_app() -> FastAPI:
    """Create and configure the client FastAPI application.

    Returns:
        Configured FastAPI app instance
    """
    app = FastAPI(
        title="MyDiffuser Client UI",
        version=__version__,
        description="Client UI for submitting jobs to remote workers",
        lifespan=lifespan,
    )

    # Include browse API routes (read-only viewing of results)
    # MIGRATION: Using client browse routes instead of server
    from mydiffuser.client import browse_routes
    app.include_router(browse_routes.router)

    # Include browse UI (HTML page for viewing results)
    # MIGRATION: Using client browse UI instead of server (Phase 2)
    from mydiffuser.client import browse_ui
    app.include_router(browse_ui.router)

    # Include client API routes (job submission, status, etc.)
    from mydiffuser.client import routes
    app.include_router(routes.router)

    # Include client UI forms (HTML forms for job submission)
    from mydiffuser.client import ui
    app.include_router(ui.router)

    # Mount static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
        logger.info(f"Mounted static files from {STATIC_DIR}")
    else:
        logger.warning(f"Static directory not found: {STATIC_DIR}")

    # Simple health check
    @app.get("/health")
    async def health():
        """Client health check."""
        return {
            "status": "healthy",
            "type": "client",
            "version": __version__,
        }

    # Root endpoint - redirect to generate image
    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Root endpoint - generate image page."""
        return templates.TemplateResponse(
            "generate_image.html",
            {"request": request}
        )

    return app


# For development: uvicorn mydiffuser.client.app:app --reload
app = create_app()
