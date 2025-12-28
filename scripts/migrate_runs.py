#!/usr/bin/env python3
"""Migrate legacy runs to the new unified folder structure.

This script:
1. Moves runs from outputs/run/image/{id}/ to outputs/run/{id}/
2. Moves runs from outputs/run/video/{id}/ to outputs/run/{id}/
3. Updates meta.json to include the new unified format
4. Generates thumb.jpg if missing

Usage:
    python scripts/migrate_runs.py [--dry-run]

Options:
    --dry-run    Show what would be done without making changes
"""

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mydiffuser.config import (
    IMAGE_MODEL_ID,
    RUNS_DIR,
    RUNS_IMAGE_DIR,
    RUNS_VIDEO_DIR,
)
from mydiffuser.utils.paths import generate_thumbnail


def get_legacy_runs() -> list[tuple[Path, str]]:
    """Get all legacy runs with their type.

    Returns:
        List of (run_dir_path, run_type) tuples
    """
    runs = []

    # Image runs
    if RUNS_IMAGE_DIR.exists():
        for item in RUNS_IMAGE_DIR.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                runs.append((item, "image"))

    # Video runs
    if RUNS_VIDEO_DIR.exists():
        for item in RUNS_VIDEO_DIR.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                runs.append((item, "video"))

    return runs


def read_legacy_meta(run_dir: Path) -> dict:
    """Read and parse legacy meta.json if it exists."""
    meta_file = run_dir / "meta.json"
    if meta_file.exists():
        try:
            return json.loads(meta_file.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def read_legacy_resolved(run_dir: Path) -> dict:
    """Read and parse legacy resolved.json if it exists."""
    resolved_file = run_dir / "resolved.json"
    if resolved_file.exists():
        try:
            return json.loads(resolved_file.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def read_prompt(run_dir: Path) -> str:
    """Read prompt.txt if it exists."""
    prompt_file = run_dir / "prompt.txt"
    if prompt_file.exists():
        try:
            return prompt_file.read_text().strip()
        except Exception:
            pass
    return ""


def create_unified_meta(
    run_id: str,
    run_type: str,
    legacy_meta: dict,
    legacy_resolved: dict,
    prompt: str,
) -> dict:
    """Create a new unified meta.json from legacy data."""
    # Extract parameters from legacy format
    params = {
        "preset": legacy_resolved.get("preset", legacy_meta.get("preset", "custom")),
        "seed": legacy_resolved.get("seed", legacy_meta.get("seed", 0)),
    }

    if run_type == "image":
        params.update({
            "height": legacy_resolved.get("height", legacy_meta.get("height", 1024)),
            "width": legacy_resolved.get("width", legacy_meta.get("width", 1024)),
            "num_inference_steps": legacy_resolved.get(
                "num_inference_steps",
                legacy_meta.get("num_inference_steps", 8),
            ),
            "guidance_scale": legacy_resolved.get(
                "guidance_scale",
                legacy_meta.get("guidance_scale", 0.0),
            ),
        })
        outputs = {"image": "output.png", "thumb": "thumb.jpg"}
        backend = IMAGE_MODEL_ID
    else:
        params.update({
            "fps": legacy_meta.get("fps", 12),
            "duration_seconds": legacy_meta.get("duration_seconds", 5),
            "num_inference_steps": legacy_meta.get("num_inference_steps", 15),
            "guidance_scale": legacy_meta.get("guidance_scale", 3.0),
        })
        outputs = {"video": "output.mp4", "input": "input.png", "thumb": "thumb.jpg"}
        backend = legacy_meta.get("backend", "unknown")

    # Parse timestamp from run_id (format: YYYYMMDD-HHMMSS-uuid or YYYYMMDD-HHMMSS_uuid)
    timestamp = None
    try:
        parts = run_id.replace("_", "-").split("-")
        if len(parts) >= 2:
            date_part = parts[0]
            time_part = parts[1]
            if len(date_part) == 8 and len(time_part) >= 6:
                time_part = time_part[:6]  # Take first 6 chars
                dt = datetime.strptime(f"{date_part}{time_part}", "%Y%m%d%H%M%S")
                timestamp = dt.replace(tzinfo=UTC).isoformat()
    except Exception:
        pass

    if not timestamp:
        timestamp = datetime.now(UTC).isoformat()

    return {
        "type": run_type,
        "run_id": run_id,
        "timestamp": timestamp,
        "prompt": prompt,
        "source_run_id": legacy_meta.get("source_run_id"),
        "backend": backend,
        "params": params,
        "outputs": outputs,
        "device": legacy_meta.get("device", "cuda"),
        "dtype": legacy_meta.get("dtype", "torch.bfloat16"),
        "seconds_elapsed": legacy_meta.get("seconds", legacy_meta.get("seconds_elapsed")),
    }


def migrate_run(
    source_dir: Path,
    run_type: str,
    dry_run: bool = False,
) -> bool:
    """Migrate a single run to the unified structure.

    Returns:
        True if migration succeeded, False if skipped
    """
    run_id = source_dir.name
    target_dir = RUNS_DIR / run_id

    # Skip if already in unified location
    if target_dir.exists():
        print(f"  SKIP {run_id} (already exists in unified location)")
        return False

    # Read legacy data
    legacy_meta = read_legacy_meta(source_dir)
    legacy_resolved = read_legacy_resolved(source_dir)
    prompt = read_prompt(source_dir)

    # Create new unified meta
    new_meta = create_unified_meta(
        run_id, run_type, legacy_meta, legacy_resolved, prompt
    )

    if dry_run:
        print(f"  WOULD MOVE {run_type}: {source_dir.name}")
        print(f"    -> {target_dir}")
        return True

    # Move the directory
    print(f"  MOVING {run_type}: {run_id}")
    shutil.move(str(source_dir), str(target_dir))

    # Write new meta.json
    meta_file = target_dir / "meta.json"
    meta_file.write_text(json.dumps(new_meta, indent=2, default=str))

    # Generate thumbnail if missing
    thumb_path = target_dir / "thumb.jpg"
    if not thumb_path.exists():
        # Try output.png for images, input.png for videos
        if run_type == "image":
            source_img = target_dir / "output.png"
        else:
            source_img = target_dir / "input.png"
            if not source_img.exists():
                source_img = target_dir / "output.png"

        if source_img.exists():
            generate_thumbnail(source_img, thumb_path)
            print(f"    Generated thumbnail")

    # Remove old resolved.json (data is now in meta.json)
    resolved_file = target_dir / "resolved.json"
    if resolved_file.exists():
        resolved_file.unlink()

    return True


def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("DRY RUN - no changes will be made\n")

    runs = get_legacy_runs()

    if not runs:
        print("No legacy runs found to migrate.")
        return

    print(f"Found {len(runs)} legacy runs to migrate\n")

    migrated = 0
    skipped = 0

    for source_dir, run_type in runs:
        if migrate_run(source_dir, run_type, dry_run):
            migrated += 1
        else:
            skipped += 1

    print(f"\nMigration complete:")
    print(f"  Migrated: {migrated}")
    print(f"  Skipped:  {skipped}")

    if not dry_run and migrated > 0:
        # Clean up empty legacy directories
        for legacy_dir in [RUNS_IMAGE_DIR, RUNS_VIDEO_DIR]:
            if legacy_dir.exists():
                remaining = list(legacy_dir.iterdir())
                # Filter out .DS_Store and similar
                remaining = [r for r in remaining if not r.name.startswith(".")]
                if not remaining:
                    print(f"\nRemoving empty directory: {legacy_dir}")
                    shutil.rmtree(legacy_dir)


if __name__ == "__main__":
    main()

