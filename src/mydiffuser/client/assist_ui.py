"""Assist UI routes for prompt improvement interface."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from mydiffuser.client import database

router = APIRouter()

# Setup Jinja2 templates
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/assist", response_class=HTMLResponse)
async def assist_page(request: Request, session_id: str | None = None):
    """Render assist page for prompt improvement.

    Args:
        request: FastAPI request
        session_id: Optional session ID to load existing conversation

    Returns:
        HTML page with chat-style interface
    """
    context = {
        "request": request,
        "session_id": session_id,
    }

    # If session_id provided, load the session
    if session_id:
        session = database.get_assist_session(session_id)
        if session:
            context["session"] = session
        else:
            raise HTTPException(status_code=404, detail="Session not found")

    return templates.TemplateResponse("assist.html", context)


@router.get("/assist/sessions", response_class=HTMLResponse)
async def assist_sessions_page(request: Request):
    """Render assist sessions list page.

    Returns:
        HTML page listing all sessions
    """
    # Get recent sessions
    sessions = database.list_assist_sessions(limit=50)

    context = {
        "request": request,
        "sessions": sessions,
    }

    return templates.TemplateResponse("assist_sessions.html", context)
