"""Admin API routes for database maintenance and system management."""

import asyncio
import csv
import io
import logging
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import StreamingResponse

from mydiffuser.client import database
from mydiffuser.client.performance_estimator import performance_estimator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Track background backfill task
_backfill_task: asyncio.Task | None = None
_backfill_stats: dict | None = None


@router.post("/backfill")
async def trigger_backfill(
    force_refresh: Annotated[bool, Form()] = False,
):
    """Trigger database backfill from meta.json files in background.

    Reads all meta.json files from outputs/run/* directories and populates
    missing columns in the runs table (params, device, dtype, etc.).

    Args:
        force_refresh: If True, update ALL runs even if they already have params

    Returns:
        Acknowledgment that backfill started. Use /api/admin/backfill/status to check progress.
    """
    global _backfill_task, _backfill_stats

    # Check if backfill is already running
    if _backfill_task and not _backfill_task.done():
        raise HTTPException(
            status_code=409,
            detail="Backfill already in progress. Please wait for it to complete."
        )

    logger.info(f"Starting backfill in background (force_refresh={force_refresh})...")

    # Reset stats
    _backfill_stats = None

    # Run backfill in executor to avoid blocking (don't await it!)
    async def run_backfill():
        global _backfill_stats
        loop = asyncio.get_event_loop()
        _backfill_stats = await loop.run_in_executor(
            None, database.backfill_runs, force_refresh, None
        )
        logger.info(f"Backfill complete: {_backfill_stats}")

    _backfill_task = asyncio.create_task(run_backfill())

    return {
        "status": "started",
        "message": (
            "Backfill started in background. "
            "Use /api/admin/backfill/status to check progress."
        ),
    }


@router.get("/backfill/status")
async def get_backfill_status():
    """Get status of last backfill operation.

    Returns:
        Status dict with: running (bool), stats (dict if complete)
    """
    global _backfill_task, _backfill_stats

    if _backfill_task is None:
        return {
            "running": False,
            "stats": None,
            "message": "No backfill has been run yet"
        }

    if not _backfill_task.done():
        return {
            "running": True,
            "stats": None,
            "message": "Backfill in progress..."
        }

    return {
        "running": False,
        "stats": _backfill_stats,
        "message": "Backfill complete"
    }


@router.get("/performance/stats")
async def get_performance_stats():
    """Get performance prediction statistics and accuracy metrics.

    Returns:
        Dict with trained models, sample counts, accuracy metrics, and scatter plot data
    """
    with database.get_db() as conn:
        # Get trained model statistics
        cursor = conn.execute(
            """
            SELECT model_id, gpu_arch, generation_type, sample_count,
                   mae_vram, mape_time, last_trained_at
            FROM performance_predictions
            ORDER BY last_trained_at DESC
            """
        )
        trained_models = []
        for row in cursor.fetchall():
            trained_models.append({
                "model_id": row[0],
                "gpu_arch": row[1],
                "generation_type": row[2],
                "sample_count": row[3],
                "mae_vram": round(row[4], 2) if row[4] else None,
                "mape_time": round(row[5], 1) if row[5] else None,
                "last_trained_at": row[6],
            })

        # Get total sample counts by model and type (only where model_id is known)
        cursor = conn.execute(
            """
            SELECT
                COALESCE(model_id, 'Unknown Model') as model_id,
                type,
                COUNT(*) as samples,
                COUNT(CASE WHEN vram_actual_total IS NOT NULL THEN 1 END) as with_vram,
                COUNT(CASE WHEN seconds_elapsed IS NOT NULL THEN 1 END) as with_time
            FROM runs
            WHERE model_id IS NOT NULL
            GROUP BY model_id, type
            ORDER BY samples DESC
            """
        )
        sample_counts = []
        for row in cursor.fetchall():
            sample_counts.append({
                "model_id": row[0],
                "type": row[1],
                "total_samples": row[2],
                "with_vram": row[3],
                "with_time": row[4],
            })

        # Get scatter plot data for VRAM predictions (last 100 samples per model)
        cursor = conn.execute(
            """
            SELECT model_id, type, vram_predicted_total, vram_actual_total
            FROM runs
            WHERE vram_predicted_total IS NOT NULL
              AND vram_actual_total IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 200
            """
        )
        vram_scatter = []
        for row in cursor.fetchall():
            vram_scatter.append({
                "model_id": row[0],
                "type": row[1],
                "predicted": round(row[2], 2),
                "actual": round(row[3], 2),
            })

        # Get scatter plot data for time predictions (last 100 samples per model)
        cursor = conn.execute(
            """
            SELECT model_id, type, time_predicted_seconds, seconds_elapsed
            FROM runs
            WHERE time_predicted_seconds IS NOT NULL
              AND seconds_elapsed IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 200
            """
        )
        time_scatter = []
        for row in cursor.fetchall():
            time_scatter.append({
                "model_id": row[0],
                "type": row[1],
                "predicted": round(row[2], 1),
                "actual": round(row[3], 1),
            })

    return {
        "trained_models": trained_models,
        "sample_counts": sample_counts,
        "scatter_data": {
            "vram": vram_scatter,
            "time": time_scatter,
        },
    }


@router.post("/performance/retrain")
async def trigger_retrain(
    model_id: Annotated[str, Form()],
    gpu_arch: Annotated[str, Form()],
    generation_type: Annotated[str, Form()],
):
    """Manually trigger model retraining for a specific model/GPU/type combination.

    Args:
        model_id: Model identifier (e.g., "Tongyi-MAI/Z-Image-Turbo")
        gpu_arch: GPU architecture (e.g., "gfx1151")
        generation_type: "image" or "video"

    Returns:
        Training results with coefficients and accuracy metrics
    """
    logger.info(f"Manual retrain triggered for {model_id} on {gpu_arch} ({generation_type})")

    try:
        coefficients = performance_estimator.train_model(model_id, gpu_arch, generation_type)

        if coefficients is None:
            min_samples = performance_estimator.MIN_SAMPLES
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient training data (need at least {min_samples} samples)",
            )

        return {
            "status": "success",
            "message": f"Model retrained successfully with {coefficients.sample_count} samples",
            "coefficients": {
                "sample_count": coefficients.sample_count,
                "mae_vram": round(coefficients.mae_vram, 2),
                "mape_time": round(coefficients.mape_time, 1),
                "vram_base": round(coefficients.vram_base, 2),
                "vram_pixel_coef": coefficients.vram_pixel_coef,
                "time_base": round(coefficients.time_base, 2),
                "time_pixel_coef": coefficients.time_pixel_coef,
                "time_step_coef": round(coefficients.time_step_coef, 2),
            },
        }
    except Exception as e:
        logger.error(f"Retrain failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/performance/cleanup")
async def cleanup_predictions():
    """Clean up bad prediction data (e.g., hardcoded 300s defaults).

    Removes time_predicted_seconds = 300 from runs table as these were
    early hardcoded defaults that skew the training data.

    Returns:
        Number of rows cleaned up
    """
    with database.get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE runs
            SET time_predicted_seconds = NULL
            WHERE time_predicted_seconds = 300
            """
        )
        conn.commit()
        count = cursor.rowcount

    logger.info(f"Cleaned up {count} rows with hardcoded 300s predictions")
    return {
        "status": "success",
        "rows_cleaned": count,
        "message": f"Removed {count} hardcoded 300s predictions"
    }


@router.get("/performance/export")
async def export_performance_data():
    """Export all performance data as CSV for external analysis.

    Returns:
        CSV file with columns: run_id, timestamp, model_id, gpu_arch, type,
        width, height, steps, frames, vram_predicted, vram_actual, time_predicted, time_actual
    """
    with database.get_db() as conn:
        cursor = conn.execute(
            """
            SELECT id, timestamp, model_id, gpu_arch, type,
                   width, height, num_inference_steps, num_frames,
                   vram_predicted_total, vram_actual_total,
                   time_predicted_seconds, seconds_elapsed
            FROM runs
            WHERE vram_actual_total IS NOT NULL
               OR seconds_elapsed IS NOT NULL
            ORDER BY timestamp DESC
            """
        )
        rows = cursor.fetchall()

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "run_id", "timestamp", "model_id", "gpu_arch", "type",
        "width", "height", "steps", "frames",
        "vram_predicted_gb", "vram_actual_gb",
        "time_predicted_s", "time_actual_s",
        "vram_error_gb", "time_error_s", "time_error_pct"
    ])

    # Data rows
    for row in rows:
        vram_pred = row[9]
        vram_actual = row[10]
        time_pred = row[11]
        time_actual = row[12]

        vram_error = (vram_actual - vram_pred) if (vram_pred and vram_actual) else None
        time_error = (time_actual - time_pred) if (time_pred and time_actual) else None
        time_error_pct = (time_error / time_actual * 100) if (time_error and time_actual) else None

        writer.writerow([
            row[0],  # run_id
            row[1],  # timestamp
            row[2],  # model_id
            row[3],  # gpu_arch
            row[4],  # type
            row[5],  # width
            row[6],  # height
            row[7],  # steps
            row[8],  # frames
            vram_pred,
            vram_actual,
            time_pred,
            time_actual,
            round(vram_error, 2) if vram_error else None,
            round(time_error, 1) if time_error else None,
            round(time_error_pct, 1) if time_error_pct else None,
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=performance_data.csv"}
    )
