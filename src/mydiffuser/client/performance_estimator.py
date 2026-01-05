"""
Data-driven performance estimation using regression models.

Learns from actual performance data in runs.db to predict VRAM usage
and generation time. Falls back to hardcoded estimates if insufficient data.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from mydiffuser.client.database import get_db

logger = logging.getLogger(__name__)


@dataclass
class ModelCoefficients:
    """Coefficients for performance prediction models"""

    # Time prediction (MULTIPLICATIVE MODEL):
    #   time_per_step = base + pixel_coef * pixels^exp + guidance_coef * guidance
    #   total_time = time_per_step * steps
    time_base: float  # Base time per step (seconds)
    time_pixel_coef: float  # Coefficient for pixel scaling
    time_step_coef: float  # Pixel exponent (0.0 to 1.0)
    time_guidance_coef: float = 0.0  # Coefficient for guidance_scale

    # VRAM prediction: vram = base + pixel_coef * pixels^0.8
    vram_base: float = 0.0
    vram_pixel_coef: float = 0.0

    sample_count: int = 0
    mae_vram: float = 0.0  # Mean absolute error for VRAM
    mape_time: float = 0.0  # Mean absolute percentage error for time


class PerformanceEstimator:
    """Learns from actual data to predict job performance"""

    MIN_SAMPLES = 5  # Minimum samples needed to train

    def __init__(self):
        """Initialize estimator"""
        self.coefficients_cache: dict[str, ModelCoefficients] = {}
        self._load_cached_coefficients()

    def _load_cached_coefficients(self):
        """Load pre-trained coefficients from database"""
        try:
            with get_db() as conn:
                cursor = conn.execute(
                    "SELECT model_id, gpu_arch, generation_type, coefficients_json "
                    "FROM performance_predictions"
                )
                for row in cursor.fetchall():
                    model_id = row[0]
                    gpu_arch = row[1]
                    gen_type = row[2]
                    coef_json = json.loads(row[3])

                    key = f"{model_id}:{gpu_arch}:{gen_type}"
                    self.coefficients_cache[key] = ModelCoefficients(**coef_json)

            logger.info(f"Loaded {len(self.coefficients_cache)} cached prediction models")
        except Exception as e:
            logger.warning(f"Failed to load cached coefficients: {e}")

    def _get_training_data(
        self, model_id: str, gpu_arch: str, generation_type: str
    ) -> list[dict]:
        """Get training data from runs.db for a specific model/GPU/type"""
        with get_db() as conn:
            # Query runs with performance data
            cursor = conn.execute(
                """
                SELECT
                    width, height, num_inference_steps, num_frames,
                    vram_actual_total, seconds_elapsed,
                    time_predicted_seconds, vram_predicted_total,
                    guidance_scale
                FROM runs
                WHERE type = ?
                  AND model_id = ?
                  AND gpu_arch = ?
                  AND vram_actual_total IS NOT NULL
                  AND seconds_elapsed IS NOT NULL
                  AND width IS NOT NULL
                  AND height IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 1000
            """,
                (generation_type, model_id, gpu_arch),
            )

            rows = cursor.fetchall()

        # Convert to list of dicts
        data = []
        for row in rows:
            data.append(
                {
                    "width": row[0],
                    "height": row[1],
                    "steps": row[2],
                    "frames": row[3] or 1,  # Default to 1 for image
                    "vram_actual": row[4],
                    "time_actual": row[5],
                    "time_predicted": row[6],
                    "vram_predicted": row[7],
                    "guidance": row[8] or 0.3,  # Default guidance if NULL
                }
            )

        return data

    def train_model(
        self, model_id: str, gpu_arch: str, generation_type: str
    ) -> ModelCoefficients | None:
        """Train regression model from actual data

        Args:
            model_id: Model identifier
            gpu_arch: GPU architecture (e.g., gfx1151)
            generation_type: "image" or "video"

        Returns:
            ModelCoefficients if training successful, None if insufficient data
        """
        data = self._get_training_data(model_id, gpu_arch, generation_type)

        if len(data) < self.MIN_SAMPLES:
            logger.info(
                f"Insufficient data for {model_id} on {gpu_arch}: "
                f"{len(data)} samples (need {self.MIN_SAMPLES})"
            )
            return None

        logger.info(f"Training model for {model_id} on {gpu_arch} with {len(data)} samples")

        # Prepare features
        pixels = np.array([d["width"] * d["height"] for d in data])
        steps = np.array([d["steps"] for d in data])
        guidance = np.array([d["guidance"] for d in data])
        vram_actual = np.array([d["vram_actual"] for d in data])
        time_actual = np.array([d["time_actual"] for d in data])

        # MULTIPLICATIVE MODEL: time = time_per_step * steps
        # where time_per_step = f(resolution, guidance)
        #
        # This is the correct model because:
        # 1. Resolution and guidance determine time_per_step (s/it)
        # 2. Steps scale linearly: total_time = time_per_step * steps
        time_per_step = time_actual / steps

        # Fit VRAM model: vram = base + pixel_coef * pixels^0.8
        pixels_vram_scaled = pixels**0.8
        X_vram = np.column_stack([np.ones(len(pixels)), pixels_vram_scaled])
        vram_coef, _, _, _ = np.linalg.lstsq(X_vram, vram_actual, rcond=None)
        vram_base, vram_pixel_coef = vram_coef

        # Fit time_per_step model: time_per_step = base + pixel_coef * pixels^exp
        # Try different exponents to find best fit with valid coefficients
        best_mape = float("inf")
        best_coeffs = None
        best_exp = None

        # Test exponents from 0.0 (no dependency) to 1.0 (linear)
        for pixel_exp in [0.0, 0.3, 0.5, 0.7, 0.85, 1.0]:
            if pixel_exp == 0.0:
                pixels_scaled = np.ones(len(pixels))
            else:
                pixels_scaled = pixels**pixel_exp

            # Include guidance as a feature
            X_time = np.column_stack([np.ones(len(pixels)), pixels_scaled, guidance])
            time_coef, _, _, _ = np.linalg.lstsq(X_time, time_per_step, rcond=None)
            time_base_candidate, time_pixel_coef_candidate, time_guidance_coef_candidate = (
                time_coef
            )

            # Validate: base must be positive (physically impossible to have negative base)
            if time_base_candidate < 0:
                continue

            # Calculate predictions and error
            time_per_step_pred = X_time @ time_coef
            time_pred = time_per_step_pred * steps
            mape = np.mean(np.abs((time_actual - time_pred) / time_actual)) * 100

            if mape < best_mape:
                best_mape = mape
                best_coeffs = (
                    time_base_candidate,
                    time_pixel_coef_candidate,
                    time_guidance_coef_candidate,
                )
                best_exp = pixel_exp

        if best_coeffs is None:
            logger.warning(
                f"Could not find valid model for {model_id} on {gpu_arch}: "
                f"all tested exponents resulted in negative base. "
                f"Using fallback estimates."
            )
            return None

        time_base, time_pixel_coef, time_guidance_coef = best_coeffs
        time_step_coef = best_exp  # Store exponent in step_coef field for compatibility

        # Calculate final predictions and errors
        if best_exp == 0.0:
            pixels_time_scaled = np.ones(len(pixels))
        else:
            pixels_time_scaled = pixels**best_exp
        X_time = np.column_stack([np.ones(len(pixels)), pixels_time_scaled, guidance])
        time_per_step_pred = X_time @ np.array([time_base, time_pixel_coef, time_guidance_coef])
        time_pred = time_per_step_pred * steps
        vram_pred = X_vram @ vram_coef

        mae_vram = np.mean(np.abs(vram_actual - vram_pred))
        mape_time = best_mape

        logger.info(f"  VRAM MAE: {mae_vram:.2f} GB")
        logger.info(f"  Time MAPE: {mape_time:.1f}%")
        logger.info(f"  Pixel exponent: {best_exp:.2f}")

        # Validate model quality - reject if predictions are terrible
        MAX_MAPE = 100.0  # Reject models with >100% time prediction error
        if mape_time > MAX_MAPE:
            logger.warning(
                f"Model quality too low for {model_id} on {gpu_arch}: "
                f"MAPE={mape_time:.1f}% (max {MAX_MAPE}%). "
                f"Keeping fallback estimates. Check for outliers in training data."
            )
            return None

        coefficients = ModelCoefficients(
            time_base=float(time_base),
            time_pixel_coef=float(time_pixel_coef),
            time_step_coef=float(time_step_coef),
            time_guidance_coef=float(time_guidance_coef),
            vram_base=float(vram_base),
            vram_pixel_coef=float(vram_pixel_coef),
            sample_count=len(data),
            mae_vram=float(mae_vram),
            mape_time=float(mape_time),
        )

        # Store in database
        self._save_coefficients(model_id, gpu_arch, generation_type, coefficients)

        # Update cache
        key = f"{model_id}:{gpu_arch}:{generation_type}"
        self.coefficients_cache[key] = coefficients

        return coefficients

    def _save_coefficients(
        self,
        model_id: str,
        gpu_arch: str,
        generation_type: str,
        coefficients: ModelCoefficients,
    ):
        """Save trained coefficients to database"""
        coef_dict = {
            "time_base": coefficients.time_base,
            "time_pixel_coef": coefficients.time_pixel_coef,
            "time_step_coef": coefficients.time_step_coef,
            "time_guidance_coef": coefficients.time_guidance_coef,
            "vram_base": coefficients.vram_base,
            "vram_pixel_coef": coefficients.vram_pixel_coef,
            "sample_count": coefficients.sample_count,
            "mae_vram": coefficients.mae_vram,
            "mape_time": coefficients.mape_time,
        }

        with get_db() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO performance_predictions
                (model_id, gpu_arch, generation_type, coefficients_json,
                 sample_count, last_trained_at, mae_vram, mape_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    model_id,
                    gpu_arch,
                    generation_type,
                    json.dumps(coef_dict),
                    coefficients.sample_count,
                    datetime.now(UTC).isoformat(),
                    coefficients.mae_vram,
                    coefficients.mape_time,
                ),
            )

    def predict(
        self,
        model_id: str,
        gpu_arch: str,
        generation_type: str,
        width: int,
        height: int,
        steps: int,
        frames: int = 1,
        guidance: float = 0.3,
    ) -> tuple[float, float] | None:
        """Predict VRAM and time using learned model

        Args:
            model_id: Model identifier
            gpu_arch: GPU architecture
            generation_type: "image" or "video"
            width, height: Image dimensions
            steps: Number of inference steps
            frames: Number of frames (for video)
            guidance: Guidance scale (default 0.3)

        Returns:
            Tuple of (vram_gb, time_seconds) or None if no model available
        """
        key = f"{model_id}:{gpu_arch}:{generation_type}"
        coefficients = self.coefficients_cache.get(key)

        if not coefficients:
            # Try to train on-demand
            coefficients = self.train_model(model_id, gpu_arch, generation_type)
            if not coefficients:
                return None

        pixels = width * height

        # VRAM prediction (unchanged)
        pixels_vram_scaled = pixels**0.8
        vram_predicted = (
            coefficients.vram_base + coefficients.vram_pixel_coef * pixels_vram_scaled
        )

        # Time prediction using MULTIPLICATIVE MODEL: time = time_per_step * steps
        # where time_per_step = base + pixel_coef * pixels^exp + guidance_coef * guidance
        pixel_exp = coefficients.time_step_coef
        if pixel_exp == 0.0:
            pixels_time_scaled = 1.0
        else:
            pixels_time_scaled = pixels**pixel_exp

        # Calculate time_per_step including guidance effect, then multiply by steps
        time_per_step = (
            coefficients.time_base
            + coefficients.time_pixel_coef * pixels_time_scaled
            + coefficients.time_guidance_coef * guidance
        )
        time_predicted = time_per_step * steps

        # Apply frame scaling for video (linear with frames)
        if generation_type == "video" and frames > 1:
            time_predicted *= frames / 36  # Normalize to 36 frame baseline

        return max(vram_predicted, 1.0), max(time_predicted, 5.0)

    def should_retrain(self, model_id: str, gpu_arch: str, generation_type: str) -> bool:
        """Check if model should be retrained

        Retrains if:
        - No cached model exists
        - New data available since last training (check sample counts)
        """
        key = f"{model_id}:{gpu_arch}:{generation_type}"
        cached_coef = self.coefficients_cache.get(key)

        if not cached_coef:
            return True

        # Check if new data is available
        data = self._get_training_data(model_id, gpu_arch, generation_type)
        new_sample_count = len(data)

        # Retrain if we have 10+ new samples
        if new_sample_count >= cached_coef.sample_count + 10:
            logger.info(
                f"New data available for {model_id}: "
                f"{new_sample_count} samples (was {cached_coef.sample_count})"
            )
            return True

        return False


    def check_and_train_if_needed(self, model_id: str, gpu_arch: str, generation_type: str):
        """Check if retraining is needed and train if so.

        This should be called after completing jobs to keep models up-to-date.
        """
        if self.should_retrain(model_id, gpu_arch, generation_type):
            logger.info(f"Triggering background training for {model_id}")
            try:
                self.train_model(model_id, gpu_arch, generation_type)
            except Exception as e:
                logger.error(f"Background training failed: {e}")


# Global instance
performance_estimator = PerformanceEstimator()
