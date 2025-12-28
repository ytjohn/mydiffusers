"""Path utilities and run directory management."""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from PIL import Image

from mydiffuser.config import (
    OUTPUT_DIR,
    RUNS_DIR,
    RUNS_IMAGE_DIR,
    RUNS_VIDEO_DIR,
    THUMB_SIZE,
)

# Run types supported by the system
RunType = Literal["image", "video", "img2img"]


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


def run_dir(run_id: str, run_type: RunType | None = None) -> Path:
    """Get or create a run directory for the given ID.

    New unified structure: outputs/run/{run_id}/
    Legacy structure: outputs/run/{type}/{run_id}/

    Args:
        run_id: Unique run identifier
        run_type: Optional type for legacy compatibility (deprecated)

    Returns:
        Path to the run directory (created if needed)
    """
    # New unified structure (no type subfolder)
    if run_type is None:
        d = RUNS_DIR / run_id
    # Legacy compatibility for existing runs
    elif run_type == "image":
        d = RUNS_IMAGE_DIR / run_id
    elif run_type == "video":
        d = RUNS_VIDEO_DIR / run_id
    else:
        d = RUNS_DIR / run_id

    d.mkdir(parents=True, exist_ok=True)
    return d


def find_run_dir(run_id: str) -> Path | None:
    """Find a run directory, checking both new and legacy locations.

    Args:
        run_id: The run ID to find

    Returns:
        Path to the run directory if found, None otherwise
    """
    # Check new unified location first
    unified = RUNS_DIR / run_id
    if unified.exists() and unified.is_dir():
        return unified

    # Check legacy image location
    legacy_image = RUNS_IMAGE_DIR / run_id
    if legacy_image.exists() and legacy_image.is_dir():
        return legacy_image

    # Check legacy video location
    legacy_video = RUNS_VIDEO_DIR / run_id
    if legacy_video.exists() and legacy_video.is_dir():
        return legacy_video

    return None


def get_run_type(run_dir_path: Path) -> RunType:
    """Determine the type of a run from its meta.json or directory location.

    Args:
        run_dir_path: Path to the run directory

    Returns:
        The run type
    """
    # Check meta.json first (new structure)
    meta_file = run_dir_path / "meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
            run_type = meta.get("type", "image")
            if run_type in ("image", "video", "img2img"):
                return run_type
        except (json.JSONDecodeError, KeyError):
            pass

    # Infer from directory location (legacy)
    if RUNS_VIDEO_DIR in run_dir_path.parents or run_dir_path.parent == RUNS_VIDEO_DIR:
        return "video"
    if RUNS_IMAGE_DIR in run_dir_path.parents or run_dir_path.parent == RUNS_IMAGE_DIR:
        return "image"

    # Check for output files
    if (run_dir_path / "output.mp4").exists():
        return "video"

    return "image"


def write_text(path: Path, content: str) -> None:
    """Write text content to a file."""
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, obj: dict) -> None:
    """Write a dict as formatted JSON to a file."""
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def read_json(path: Path) -> dict:
    """Read a JSON file and return as dict."""
    return json.loads(path.read_text(encoding="utf-8"))


def generate_thumbnail(source_path: Path, thumb_path: Path) -> bool:
    """Generate a thumbnail from an image.

    Args:
        source_path: Path to source image (PNG, JPG, etc.)
        thumb_path: Path to save thumbnail

    Returns:
        True if successful, False otherwise
    """
    try:
        with Image.open(source_path) as img:
            # Convert to RGB if necessary (handles RGBA, etc.)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Resize maintaining aspect ratio
            img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)

            # Save as JPEG for smaller file size
            img.save(thumb_path, "JPEG", quality=85, optimize=True)
            return True
    except Exception:
        return False


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


def list_all_runs() -> list[Path]:
    """List all run directories from both new and legacy locations.

    Returns:
        List of run directory paths, sorted by run_id (newest first)
    """
    runs: list[Path] = []

    # New unified location (direct children of RUNS_DIR that are dirs)
    if RUNS_DIR.exists():
        for item in RUNS_DIR.iterdir():
            # Skip legacy subdirectories
            if item.name in ("image", "video"):
                continue
            if item.is_dir() and not item.name.startswith("."):
                runs.append(item)

    # Legacy image location
    if RUNS_IMAGE_DIR.exists():
        for item in RUNS_IMAGE_DIR.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                runs.append(item)

    # Legacy video location
    if RUNS_VIDEO_DIR.exists():
        for item in RUNS_VIDEO_DIR.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                runs.append(item)

    # Sort by directory name (which is the run_id, time-ordered)
    runs.sort(key=lambda p: p.name, reverse=True)
    return runs
