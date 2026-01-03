"""
Database enhancements for VRAM and time estimation tracking.

NOTE: As of schema v5, performance data is stored in outputs/runs.db
instead of data/performance.db. This module provides backwards-compatible
access to the unified database.
"""

import sqlite3
from pathlib import Path
from typing import Any

# Use runs.db as the primary database (consolidated in schema v5)
DB_PATH = Path("outputs/runs.db")


class PerformanceTracker:
    """Tracks job performance data for VRAM and time estimation.

    As of schema v5, this class writes directly to runs.db instead of
    a separate performance.db file.
    """

    def __init__(self):
        # Ensure runs.db exists (will be created by client/database.py init)
        if not DB_PATH.exists():
            from mydiffuser.client.database import init_database
            init_database()

    def init_database(self):
        """Initialize the performance tracking database.

        NOTE: This is now handled by client/database.py migrate_v5.
        Kept for backwards compatibility but does nothing.
        """
        pass

    def record_job_performance(
        self,
        job_id: str,
        worker_id: str,
        model_id: str,
        model_type: str,
        parameters: dict[str, Any],
        vram_estimates: dict[str, float],
        vram_actual: dict[str, float],
        model_was_loaded: bool,
        time_estimates: dict[str, float],
        time_actual: float,
    ):
        """Record job performance data directly in runs table.

        NOTE: As of schema v5, performance data is stored in the runs table.
        This method updates the corresponding run record with performance data.
        """
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        try:
            # Update the run record with performance data
            # job_id corresponds to run_id in the runs table
            conn.execute(
                """
                UPDATE runs
                SET
                    vram_predicted_total = ?,
                    vram_actual_total = ?,
                    vram_actual_inference = ?,
                    time_predicted_seconds = ?
                WHERE id = ?
            """,
                (
                    vram_estimates.get("total"),
                    vram_actual.get("total"),
                    vram_actual.get("inference"),
                    time_estimates.get("predicted"),
                    job_id,
                ),
            )

            conn.commit()
        except Exception as e:
            conn.rollback()
            # Log but don't fail - performance tracking is non-critical
            import logging
            logging.warning(f"Failed to record performance for {job_id}: {e}")
        finally:
            conn.close()

    def get_performance_stats(
        self, model_id: str, days_back: int = 90
    ) -> dict[str, Any]:
        """Get performance statistics for a model from runs table."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Query runs table instead of job_performance
        cursor.execute(
            f"""
            SELECT
                AVG(vram_actual_total) as avg_vram,
                AVG(seconds_elapsed) as avg_time,
                COUNT(*) as job_count,
                AVG(vram_actual_total - vram_predicted_total) as vram_accuracy,
                AVG(seconds_elapsed - time_predicted_seconds) as time_accuracy
            FROM runs
            WHERE model_id = ?
              AND timestamp > datetime('now', '-{days_back} days')
              AND vram_actual_total IS NOT NULL
        """,
            (model_id,),
        )

        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                "avg_vram_gb": result[0] or 0,
                "avg_time_seconds": result[1] or 0,
                "job_count": result[2] or 0,
                "vram_accuracy_gb": result[3] or 0,
                "time_accuracy_seconds": result[4] or 0,
            }
        return {}

    def get_recent_jobs(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Get recent job performance data from runs table for ML training."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        cursor = conn.cursor()

        # Query runs table for recent jobs with performance data
        cursor.execute(
            """
            SELECT
                id as job_id,
                model_id,
                type as model_type,
                width, height, num_inference_steps, guidance_scale,
                num_frames, fps, duration_seconds,
                vram_predicted_total, vram_actual_total, vram_actual_inference,
                time_predicted_seconds, seconds_elapsed as time_actual_seconds,
                inference_seconds, decode_seconds, encode_seconds,
                gpu_name, gpu_arch,
                timestamp as created_at
            FROM runs
            WHERE vram_actual_total IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT ?
        """,
            (limit,),
        )

        results = [dict(row) for row in cursor.fetchall()]

        # Reconstruct parameters dict for backwards compatibility
        for result in results:
            result["parameters"] = {
                "width": result.get("width"),
                "height": result.get("height"),
                "num_inference_steps": result.get("num_inference_steps"),
                "guidance_scale": result.get("guidance_scale"),
                "num_frames": result.get("num_frames"),
                "fps": result.get("fps"),
                "duration_seconds": result.get("duration_seconds"),
            }
            # Remove None values
            result["parameters"] = {k: v for k, v in result["parameters"].items() if v is not None}

        conn.close()
        return results


# Global instance
performance_tracker = PerformanceTracker()
