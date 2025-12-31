"""Assistant API routes for prompt improvement with Qwen2-VL."""

import base64
import logging
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile, File
from PIL import Image

from mydiffuser.client import database
from mydiffuser.client.worker_client import WorkerClient
from mydiffuser.client.config import list_workers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assist", tags=["assist"])


@router.post("/analyze")
async def analyze_image(
    session_id: Annotated[str | None, Form()] = None,
    goal: Annotated[str | None, Form()] = None,
    run_id: Annotated[str | None, Form()] = None,
    image_path: Annotated[str | None, Form()] = None,
    image_base64: Annotated[str | None, Form()] = None,
    image_file: UploadFile | None = File(None),
    current_prompt: Annotated[str, Form()] = "",
    user_message: Annotated[str | None, Form()] = None,
):
    """Analyze an image and provide prompt improvement suggestions.

    Args:
        session_id: Existing session ID (or create new one if None)
        goal: Session goal (required if session_id is None)
        run_id: Run ID to analyze (loads from outputs/run/{run_id}/)
        image_path: Direct path to image file
        image_base64: Base64-encoded image data
        image_file: Uploaded image file
        current_prompt: The prompt that generated this image
        user_message: Optional user feedback/issue description

    Returns:
        Dict with analysis, suggestions, and session info
    """
    # Create or validate session
    if session_id is None:
        if not goal:
            raise HTTPException(
                status_code=400,
                detail="Must provide 'goal' when creating a new session"
            )
        session_id = database.create_assist_session(goal)
        turn_number = 1
    else:
        # Get existing session to determine turn number
        session = database.get_assist_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        turn_number = session['turn_count'] + 1

    # Load image from one of the sources
    image = None
    image_path_str = None

    try:
        if run_id:
            # Load from run directory
            run_path = Path("outputs/run") / run_id
            # Try to find the image file
            image_files = list(run_path.glob("*.png")) + list(run_path.glob("*.jpg"))
            if not image_files:
                raise HTTPException(
                    status_code=404,
                    detail=f"No image found in {run_path}"
                )
            image_path_str = str(image_files[0])
            image = Image.open(image_files[0])

        elif image_path:
            # Load from direct path
            image_path_obj = Path(image_path)
            if not image_path_obj.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Image not found: {image_path}"
                )
            image_path_str = image_path
            image = Image.open(image_path_obj)

        elif image_base64:
            # Decode base64
            image_data = base64.b64decode(image_base64)
            image = Image.open(BytesIO(image_data))
            image_path_str = None  # No persistent path

        elif image_file:
            # Load from uploaded file
            contents = await image_file.read()
            image = Image.open(BytesIO(contents))
            image_path_str = None  # No persistent path

        else:
            raise HTTPException(
                status_code=400,
                detail="Must provide one of: run_id, image_path, image_base64, or image_file"
            )

    except Exception as e:
        logger.error(f"Failed to load image: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to load image: {e}")

    # Get first available worker
    workers = list_workers()
    if not workers:
        raise HTTPException(
            status_code=503,
            detail="No workers available for analysis"
        )

    worker_config = workers[0]  # Use first worker (typically local)
    worker_endpoint = worker_config["endpoint"]

    # Call worker to analyze the image
    try:
        with WorkerClient(worker_endpoint, timeout=60.0) as client:
            result = client.analyze_image_prompt(
                image=image,
                current_prompt=current_prompt,
                user_message=user_message,
                max_new_tokens=512,
            )
    except Exception as e:
        logger.error(f"Worker analysis failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Worker analysis failed: {e}"
        )

    # Store turn in database
    try:
        turn_id = database.add_assist_turn(
            session_id=session_id,
            turn_number=turn_number,
            run_id=run_id,
            current_prompt=current_prompt,
            user_message=user_message,
            assistant_response=result['raw_response'],
            suggested_prompts=result['suggestions'],
            model_used="Qwen2-VL-2B-Instruct"
        )
    except Exception as e:
        logger.error(f"Failed to store turn: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to store turn: {e}")

    # Return response with session info
    return {
        "session_id": session_id,
        "turn_id": turn_id,
        "turn_number": turn_number,
        "analysis": result['analysis'],
        "suggestions": result['suggestions'],
        "raw_response": result['raw_response'],
    }


@router.get("/sessions")
async def list_sessions(
    limit: int = 20,
    status: str | None = None
):
    """List recent assist sessions.

    Args:
        limit: Maximum sessions to return (default 20)
        status: Optional filter by status ('active', 'resolved', 'abandoned')

    Returns:
        List of session dicts (without turns)
    """
    try:
        sessions = database.list_assist_sessions(limit=limit, status=status)
        return {"sessions": sessions}
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {e}")


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get conversation history for a session.

    Args:
        session_id: Session UUID

    Returns:
        Dict with session info and all turns
    """
    session = database.get_assist_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


@router.post("/sessions/{session_id}/resolve")
async def resolve_session(
    session_id: str,
    final_prompt: Annotated[str, Form()],
    final_run_id: Annotated[str | None, Form()] = None
):
    """Mark session as resolved with final prompt.

    Args:
        session_id: Session UUID
        final_prompt: The final improved prompt
        final_run_id: Optional run_id of final generation

    Returns:
        Success confirmation
    """
    # Verify session exists
    session = database.get_assist_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        database.resolve_assist_session(
            session_id=session_id,
            final_prompt=final_prompt,
            final_run_id=final_run_id
        )
        return {"status": "ok", "message": "Session resolved"}
    except Exception as e:
        logger.error(f"Failed to resolve session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resolve session: {e}")
