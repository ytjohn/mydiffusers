"""Worker health dashboard UI."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

# Setup Jinja2 templates
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/health-dashboard", response_class=HTMLResponse)
def health_dashboard(request: Request):
    """Worker health monitoring dashboard."""
    return templates.TemplateResponse("health_dashboard.html", {"request": request})
