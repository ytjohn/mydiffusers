"""Browse API routes for viewing past generations."""

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel

from mydiffuser.config import OUTPUT_DIR, RUNS_IMAGE_DIR

router = APIRouter(prefix="/api/runs", tags=["browse"])

# Thumbnail cache directory
THUMBS_DIR = OUTPUT_DIR / ".thumbs"
THUMB_SIZE = 256


class RunSummary(BaseModel):
    """Summary of a generation run for listing."""

    id: str
    prompt_preview: str
    timestamp: str


class RunDetail(BaseModel):
    """Full details of a generation run."""

    id: str
    prompt: str
    preset: str
    seed: int
    height: int
    width: int
    num_inference_steps: int
    guidance_scale: float
    seconds: float | None = None


class RunListResponse(BaseModel):
    """Paginated list of runs."""

    runs: list[RunSummary]
    total: int
    limit: int
    offset: int


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


def _get_prompt_preview(run_dir: Path, max_len: int = 100) -> str:
    """Read first line of prompt, truncated."""
    prompt_file = run_dir / "prompt.txt"
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


def _validate_run_path(run_id: str) -> Path:
    """Validate run ID and return path, raising HTTPException if invalid."""
    # Prevent path traversal
    if "/" in run_id or "\\" in run_id or ".." in run_id:
        raise HTTPException(status_code=400, detail="Invalid run ID")

    run_dir = RUNS_IMAGE_DIR / run_id
    if not run_dir.exists() or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="Run not found")

    # Extra safety: ensure resolved path is under RUNS_IMAGE_DIR
    resolved = run_dir.resolve()
    if RUNS_IMAGE_DIR.resolve() not in resolved.parents:
        raise HTTPException(status_code=400, detail="Invalid run ID")

    return run_dir


@router.get("", response_model=RunListResponse)
def list_runs(limit: int = 24, offset: int = 0) -> RunListResponse:
    """List generation runs, newest first."""
    if not RUNS_IMAGE_DIR.exists():
        return RunListResponse(runs=[], total=0, limit=limit, offset=offset)

    # Get all run directories, sorted by name descending (newest first)
    all_dirs = sorted(
        [d for d in RUNS_IMAGE_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )

    total = len(all_dirs)
    paginated = all_dirs[offset : offset + limit]

    runs = []
    for run_dir in paginated:
        runs.append(
            RunSummary(
                id=run_dir.name,
                prompt_preview=_get_prompt_preview(run_dir),
                timestamp=_parse_timestamp(run_dir.name),
            )
        )

    return RunListResponse(runs=runs, total=total, limit=limit, offset=offset)


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str) -> RunDetail:
    """Get full details of a run."""
    run_dir = _validate_run_path(run_id)

    # Read prompt
    prompt_file = run_dir / "prompt.txt"
    prompt = ""
    if prompt_file.exists():
        try:
            prompt = prompt_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    # Read resolved params
    resolved_file = run_dir / "resolved.json"
    resolved: dict = {}
    if resolved_file.exists():
        try:
            resolved = json.loads(resolved_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Read meta for timing
    meta_file = run_dir / "meta.json"
    seconds = None
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            seconds = meta.get("seconds")
        except Exception:
            pass

    return RunDetail(
        id=run_id,
        prompt=prompt,
        preset=resolved.get("preset", "custom"),
        seed=resolved.get("seed", 0),
        height=resolved.get("height", 1024),
        width=resolved.get("width", 1024),
        num_inference_steps=resolved.get("num_inference_steps", 8),
        guidance_scale=resolved.get("guidance_scale", 0.0),
        seconds=seconds,
    )


@router.get("/{run_id}/thumb")
def get_thumbnail(run_id: str) -> Response:
    """Get thumbnail for a run, generating and caching if needed."""
    run_dir = _validate_run_path(run_id)

    # Check cache
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    thumb_path = THUMBS_DIR / f"{run_id}.png"

    if not thumb_path.exists():
        # Generate thumbnail
        output_png = run_dir / "output.png"
        if not output_png.exists():
            raise HTTPException(status_code=404, detail="Output image not found")

        try:
            with Image.open(output_png) as img:
                # Maintain aspect ratio
                img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
                img.save(thumb_path, "PNG")
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to generate thumbnail: {e}"
            ) from None

    # Return cached thumbnail
    return Response(
        content=thumb_path.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/{run_id}/image")
def get_full_image(run_id: str) -> Response:
    """Get the full-size output image."""
    run_dir = _validate_run_path(run_id)

    output_png = run_dir / "output.png"
    if not output_png.exists():
        raise HTTPException(status_code=404, detail="Output image not found")

    return Response(
        content=output_png.read_bytes(),
        media_type="image/png",
    )


@router.delete("/{run_id}")
def delete_run(run_id: str) -> dict:
    """Delete a run and its thumbnail."""
    run_dir = _validate_run_path(run_id)

    # Delete thumbnail if exists
    thumb_path = THUMBS_DIR / f"{run_id}.png"
    if thumb_path.exists():
        try:
            thumb_path.unlink()
        except Exception:
            pass

    # Delete run directory
    try:
        shutil.rmtree(run_dir)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete run: {e}"
        ) from None

    return {"deleted": run_id}

