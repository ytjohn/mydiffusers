"""Path utilities and run directory management."""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from mydiffuser.config import OUTPUT_DIR, RUNS_IMAGE_DIR, RUNS_VIDEO_DIR


def new_run_id() -> str:
    """Generate a new unique, time-ordered run ID.

    Format: YYYYMMDD-HHMMSS-<short-uuid>
    Example: 20251225-214523-a1b2c3d4

    This format:
    - Sorts chronologically by default
    - Is human-readable (you can see when it was created)
    - Includes a short UUID suffix for uniqueness within the same second
    """
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"{timestamp}-{short_uuid}"


def run_dir(kind: str, run_id: str) -> Path:
    """Get or create a run directory for the given kind and ID.

    Args:
        kind: Either "image" or "video"
        run_id: Unique run identifier

    Returns:
        Path to the run directory (created if needed)
    """
    if kind == "image":
        d = RUNS_IMAGE_DIR / run_id
    elif kind == "video":
        d = RUNS_VIDEO_DIR / run_id
    else:
        raise ValueError("kind must be image|video")
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_text(path: Path, content: str) -> None:
    """Write text content to a file."""
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, obj: dict) -> None:
    """Write a dict as formatted JSON to a file."""
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def safe_under_outputs(path_str: str) -> Path:
    """Resolve a path and verify it's under OUTPUT_DIR.

    Args:
        path_str: Relative path string

    Returns:
        Resolved absolute Path

    Raises:
        ValueError: If path escapes OUTPUT_DIR
    """
    from mydiffuser.config import PROJECT_ROOT

    p = (PROJECT_ROOT / path_str).resolve()
    if OUTPUT_DIR.resolve() not in p.parents and p != OUTPUT_DIR.resolve():
        raise ValueError("path must be under outputs/")
    return p


def safe_output_path(rel_path: str) -> Path:
    """Validate and create a safe output path for saving files.

    Prevents path traversal and ensures valid image extensions.

    Args:
        rel_path: Relative path for the output file

    Returns:
        Absolute Path to the output file

    Raises:
        ValueError: If path is invalid or has unsupported extension
    """
    rel = Path(rel_path)

    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("save_path must be a relative path under outputs/")

    if rel.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        if rel.suffix == "":
            rel = rel.with_suffix(".png")
        else:
            raise ValueError("Unsupported file extension. Use png/jpg/jpeg/webp.")

    out = (OUTPUT_DIR / rel).resolve()
    if OUTPUT_DIR.resolve() not in out.parents and out != OUTPUT_DIR.resolve():
        raise ValueError("save_path must stay under outputs/")

    out.parent.mkdir(parents=True, exist_ok=True)
    return out

