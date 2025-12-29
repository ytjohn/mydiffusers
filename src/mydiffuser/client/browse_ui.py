"""Browse UI endpoint for viewing past generations."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/browse")
def browse_page(request: Request):
    """Browse page for viewing past generations."""
    return templates.TemplateResponse("browse.html", {"request": request})
