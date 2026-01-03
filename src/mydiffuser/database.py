"""
Database enhancements for VRAM and time estimation tracking.
"""

import json
import sqlite3
from typing import Any

from mydiffuser.config import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "performance.db"


class PerformanceTracker:
    """Tracks job performance data for VRAM and time estimation"""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()

    def init_database(self):
        """Initialize the performance tracking database"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                model_type TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                vram_predicted_total REAL,
                vram_predicted_inference REAL,
                vram_predicted_model REAL,
                vram_actual_total REAL,
                vram_actual_inference REAL,
                vram_actual_model REAL,
                model_was_loaded BOOLEAN,
                time_predicted_seconds REAL,
                time_actual_seconds REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indices for efficient queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_performance_model
            ON job_performance(model_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_performance_worker
            ON job_performance(worker_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_performance_created
            ON job_performance(created_at)
        """)

        conn.commit()
        conn.close()

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
        """Record job performance data for ML training"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO job_performance (
                job_id, worker_id, model_id, model_type, parameters_json,
                vram_predicted_total, vram_predicted_inference, vram_predicted_model,
                vram_actual_total, vram_actual_inference, vram_actual_model,
                model_was_loaded, time_predicted_seconds, time_actual_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                job_id,
                worker_id,
                model_id,
                model_type,
                json.dumps(parameters),
                vram_estimates.get("total"),
                vram_estimates.get("inference"),
                vram_estimates.get("model"),
                vram_actual.get("total"),
                vram_actual.get("inference"),
                vram_actual.get("model"),
                model_was_loaded,
                time_estimates.get("predicted"),
                time_actual,
            ),
        )

        conn.commit()
        conn.close()

    def get_performance_stats(
        self, model_id: str, days_back: int = 90
    ) -> dict[str, Any]:
        """Get performance statistics for a model"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            f"""
            SELECT
                AVG(vram_actual_total) as avg_vram,
                AVG(time_actual_seconds) as avg_time,
                COUNT(*) as job_count,
                AVG(vram_actual_total - vram_predicted_total) as vram_accuracy,
                AVG(time_actual_seconds - time_predicted_seconds) as time_accuracy
            FROM job_performance
            WHERE model_id = ? AND created_at > datetime('now', '-{days_back} days')
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
        """Get recent job performance data for ML training"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM job_performance
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (limit,),
        )

        columns = [description[0] for description in cursor.description]
        results = [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]

        for result in results:
            result["parameters"] = json.loads(result["parameters_json"])
            del result["parameters_json"]

        conn.close()
        return results


# Global instance
performance_tracker = PerformanceTracker()
