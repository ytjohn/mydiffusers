"""Browse API routes for viewing past generations."""

import shutil
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from PIL import Image
from pydantic import BaseModel, Field

from mydiffuser.config import RUNS_DIR, THUMBS_CACHE_DIR
from mydiffuser.utils.paths import (
    find_run_dir,
    get_run_type,
    list_all_runs,
    read_json,
)

router = APIRouter(prefix="/api/runs", tags=["browse"])

# Thumbnail settings
THUMB_SIZE = 256


class RunSummary(BaseModel):
    """Summary of a generation run for listing."""

    id: str
    type: str
    prompt_preview: str
    timestamp: str
    source_run_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class RunDetail(BaseModel):
    """Full details of a generation run."""

    id: str
    type: str
    prompt: str
    preset: str
    seed: int
    height: int
    width: int
    num_inference_steps: int
    guidance_scale: float
    seconds: float | None = None
    source_run_id: str | None = None
    backend: str | None = None


class RunListResponse(BaseModel):
    """Paginated list of runs."""

    runs: list[RunSummary]
    total: int
    page: int
    pages: int
    limit: int


def _parse_timestamp(run_id: str) -> str:
    """Extract human-readable timestamp from run ID.

    Run IDs are formatted as YYYYMMDD-HHMMSS-<uuid8>
    """
    parts = run_id.split("-")
    if len(parts) >= 2:
        date_part = parts[0]
        time_part = parts[1]
        if len(date_part) == 8 and len(time_part) == 6:
            date_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
            time_str = f"{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
            return f"{date_str} {time_str}"
    return run_id


def _get_prompt_preview(run_dir_path: Path, max_len: int = 100) -> str:
    """Read first line of prompt, truncated."""
    prompt_file = run_dir_path / "prompt.txt"
    if prompt_file.exists():
        try:
            text = prompt_file.read_text(encoding="utf-8").strip()
            first_line = text.split("\n")[0]
            if len(first_line) > max_len:
                return first_line[: max_len - 3] + "..."
            return first_line
        except Exception:
            pass
    return ""


def _get_run_meta(run_dir_path: Path) -> dict[str, Any]:
    """Read meta.json from a run directory."""
    meta_file = run_dir_path / "meta.json"
    if meta_file.exists():
        try:
            return read_json(meta_file)
        except Exception:
            pass
    return {}


def _get_source_run_id(run_dir_path: Path) -> str | None:
    """Get source_run_id from meta.json if present."""
    meta = _get_run_meta(run_dir_path)
    return meta.get("source_run_id")


def _validate_run_path(run_id: str) -> Path:
    """Validate run ID and return path, raising HTTPException if invalid."""
    # Prevent path traversal
    if "/" in run_id or "\\" in run_id or ".." in run_id:
        raise HTTPException(status_code=400, detail="Invalid run ID")

    run_dir_path = find_run_dir(run_id)
    if run_dir_path is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # Extra safety: ensure resolved path is under RUNS_DIR
    resolved = run_dir_path.resolve()
    runs_resolved = RUNS_DIR.resolve()
    if runs_resolved not in resolved.parents and resolved != runs_resolved:
        raise HTTPException(status_code=400, detail="Invalid run ID")

    return run_dir_path


@router.get("/tags")
def get_all_tags() -> dict:
    """Get all unique tags from SQLite database."""
    from mydiffuser.client import database
    tags = database.get_all_tags()
    return {"tags": tags}


@router.get("", response_model=RunListResponse)
def list_runs(
    type: Literal["all", "image", "video", "img2img"] = Query(
        default="all", description="Filter by run type"
    ),
    include_tags: str = Query(default="", description="Comma-separated tags to include (OR logic)"),
    show_nsfw: bool = Query(default=False, description="Include NSFW content in results"),
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=24, ge=1, le=100, description="Items per page"),
) -> RunListResponse:
    """List generation runs from SQLite database, newest first.

    Supports filtering by type, tags, and pagination.
    Tag filtering logic:
    - No tags selected: Show all runs
    - Tags selected: Show ONLY runs with those tags (OR logic)
    - show_nsfw=False: Exclude nsfw content from results (default)
    - show_nsfw=True: Include nsfw content in results
    """
    from mydiffuser.client import database

    # Parse included tags
    included = [t.strip() for t in include_tags.split(",") if t.strip()] if include_tags else []

    # Query database
    runs_data, total = database.get_runs(
        run_type=type,
        include_tags=included,
        show_nsfw=show_nsfw,
        page=page,
        limit=limit
    )

    # Convert to RunSummary objects
    runs = []
    for data in runs_data:
        runs.append(RunSummary(
            id=data['id'],
            type=data['type'],
            prompt_preview=data['prompt'][:100] if data['prompt'] else '',
            timestamp=_parse_timestamp(data['id']),
            source_run_id=data.get('source_run_id'),
            tags=data.get('tags', [])
        ))

    pages = (total + limit - 1) // limit if total > 0 else 1

    return RunListResponse(
        runs=runs,
        total=total,
        page=page,
        pages=pages,
        limit=limit,
    )


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str) -> RunDetail:
    """Get full details of a run."""
    run_dir_path = _validate_run_path(run_id)
    run_type = get_run_type(run_dir_path)

    # Read prompt
    prompt_file = run_dir_path / "prompt.txt"
    prompt = ""
    if prompt_file.exists():
        try:
            prompt = prompt_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    # Try new meta.json format first
    meta = _get_run_meta(run_dir_path)

    if "params" in meta:
        # New unified format
        params = meta.get("params", {})
        return RunDetail(
            id=run_id,
            type=run_type,
            prompt=prompt or meta.get("prompt", ""),
            preset=params.get("preset", "custom"),
            seed=params.get("seed", 0),
            height=params.get("height", 1024),
            width=params.get("width", 1024),
            num_inference_steps=params.get("num_inference_steps", 8),
            guidance_scale=params.get("guidance_scale", 0.0),
            seconds=meta.get("seconds_elapsed"),
            source_run_id=meta.get("source_run_id"),
            backend=meta.get("backend"),
        )

    # Fall back to legacy format (resolved.json + meta.json)
    resolved_file = run_dir_path / "resolved.json"
    resolved: dict = {}
    if resolved_file.exists():
        try:
            resolved = read_json(resolved_file)
        except Exception:
            pass

    # Legacy meta for timing
    seconds = meta.get("seconds")

    return RunDetail(
        id=run_id,
        type=run_type,
        prompt=prompt,
        preset=resolved.get("preset", "custom"),
        seed=resolved.get("seed", 0),
        height=resolved.get("height", 1024),
        width=resolved.get("width", 1024),
        num_inference_steps=resolved.get("num_inference_steps", 8),
        guidance_scale=resolved.get("guidance_scale", 0.0),
        seconds=seconds,
        source_run_id=None,
        backend=None,
    )


@router.get("/{run_id}/thumb")
def get_thumbnail(run_id: str) -> Response:
    """Get thumbnail for a run.

    For new runs, returns thumb.jpg from run directory.
    For legacy runs, generates and caches thumbnail.
    """
    run_dir_path = _validate_run_path(run_id)

    # Check for new-style embedded thumbnail first
    thumb_in_dir = run_dir_path / "thumb.jpg"
    if thumb_in_dir.exists():
        return Response(
            content=thumb_in_dir.read_bytes(),
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # Fall back to cached thumbnail for legacy runs
    THUMBS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_thumb = THUMBS_CACHE_DIR / f"{run_id}.jpg"

    if not cached_thumb.exists():
        # Find output image
        output_png = run_dir_path / "output.png"
        if not output_png.exists():
            raise HTTPException(status_code=404, detail="Output image not found")

        try:
            with Image.open(output_png) as img:
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
                img.save(cached_thumb, "JPEG", quality=85, optimize=True)
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to generate thumbnail: {e}"
            ) from None

    return Response(
        content=cached_thumb.read_bytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/{run_id}/image")
def get_full_image(run_id: str) -> Response:
    """Get the full-size output image."""
    run_dir_path = _validate_run_path(run_id)

    output_png = run_dir_path / "output.png"
    if not output_png.exists():
        raise HTTPException(status_code=404, detail="Output image not found")

    return Response(
        content=output_png.read_bytes(),
        media_type="image/png",
    )


@router.get("/{run_id}/video")
def get_video(run_id: str) -> FileResponse:
    """Get the output video (for video runs).

    Uses FileResponse to support HTTP range requests for video streaming.
    Returns with inline disposition for browser playback.
    """
    run_dir_path = _validate_run_path(run_id)

    output_mp4 = run_dir_path / "output.mp4"
    if not output_mp4.exists():
        raise HTTPException(status_code=404, detail="Output video not found")

    # Don't set filename to avoid content-disposition: attachment
    # This allows inline video playback in browsers
    return FileResponse(
        path=output_mp4,
        media_type="video/mp4",
    )


@router.delete("/{run_id}")
def delete_run(run_id: str) -> dict:
    """Delete a run and its cached thumbnail."""
    run_dir_path = _validate_run_path(run_id)

    # Delete cached thumbnail if exists
    cached_thumb = THUMBS_CACHE_DIR / f"{run_id}.jpg"
    if cached_thumb.exists():
        try:
            cached_thumb.unlink()
        except Exception:
            pass

    # Also try old .png format
    cached_thumb_png = THUMBS_CACHE_DIR / f"{run_id}.png"
    if cached_thumb_png.exists():
        try:
            cached_thumb_png.unlink()
        except Exception:
            pass

    # Delete run directory
    try:
        shutil.rmtree(run_dir_path)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete run: {e}"
        ) from None

    # Delete from SQLite database
    from mydiffuser.client import database
    database.delete_run(run_id)

    return {"deleted": run_id}


class UpdateRunRequest(BaseModel):
    """Request model for updating run metadata."""

    tags: list[str] | None = None


@router.patch("/{run_id}")
def update_run(run_id: str, update: UpdateRunRequest) -> dict:
    """Update run metadata (e.g., tags)."""
    run_dir_path = _validate_run_path(run_id)
    meta_file = run_dir_path / "meta.json"

    if not meta_file.exists():
        raise HTTPException(status_code=404, detail="Metadata not found")

    try:
        meta = read_json(meta_file)
        if update.tags is not None:
            meta["tags"] = update.tags

        # Write updated meta.json
        from mydiffuser.utils.paths import write_json
        write_json(meta_file, meta)

        # Re-index in SQLite
        from mydiffuser.client import database
        database.index_run(run_id, meta)

        return {"updated": run_id, "tags": meta.get("tags", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update: {e}")
