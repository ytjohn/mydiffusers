"""Admin dashboard UI routes."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

# Setup Jinja2 templates
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/admin/performance", response_class=HTMLResponse)
def performance_dashboard(request: Request):
    """Performance prediction tuning dashboard."""
    return templates.TemplateResponse("performance_dashboard.html", {"request": request})
