"""
Client-side VRAM and time estimation service.

Provides accurate resource estimates for job parameters based on
actual measurements and model loading state. Uses data-driven predictions
when available, falls back to hardcoded estimates otherwise.
"""

import logging
from dataclasses import dataclass
from typing import Any, ClassVar

from mydiffuser.client.performance_estimator import performance_estimator

logger = logging.getLogger(__name__)


@dataclass
class JobEstimate:
    """Container for job resource estimates"""

    vram_total_needed: float
    vram_inference_only: float
    vram_model_base: float
    model_loaded: bool
    time_estimate_seconds: float
    worker_available: bool
    recommendations: list[str]


class JobEstimator:
    """Estimates VRAM and time for job parameters"""

    # Actual timing data from your performance database
    TIMING_BASELINES: ClassVar[dict[str, dict[str, float]]] = {
        "Tongyi-MAI/Z-Image-Turbo": {
            "832x480@4steps": 7.4,  # Your actual measurement
            "832x480@6steps": 10.9,  # Your actual measurement
            "832x480@5steps": 18.4,  # With guidance=8.0
            "1920x1080@30steps": 3915.0,  # Your actual measurement
        },
        "Wan-AI/Wan2.2-TI2V-5B-Diffusers": {
            "1280x704@36frames@15steps": 2132.0,  # Your actual measurement (35.5 min)
        },
        "qwen2-vl-7b": {
            "default": 30  # seconds for typical query (Qwen2-VL-2B is fast)
        },
    }

    def __init__(self):
        pass  # Skip VRAM predictor for now

    def check_model_loaded(self, worker_id: str, model_id: str) -> bool:
        """Check if model is loaded on worker - simplified for now"""
        return False

    def _get_model_type(self, model_id: str) -> str:
        """Determine model type from model ID"""
        if "Image" in model_id or "Z-Image" in model_id:
            return "image"
        elif "Wan" in model_id and "I2V" in model_id:
            return "video"
        elif "qwen" in model_id.lower():
            return "assistant"
        else:
            return "image"

    def estimate_image_job(
        self, model_id: str, parameters: dict[str, Any], worker_id: str, gpu_arch: str
    ) -> JobEstimate:
        """Estimate VRAM and time for image job.

        Uses data-driven predictions when available, falls back to hardcoded estimates.

        Args:
            model_id: Model identifier
            parameters: Job parameters
            worker_id: Worker identifier
            gpu_arch: GPU architecture (e.g., "gfx1151")
        """
        model_loaded = self.check_model_loaded(worker_id, model_id)

        # Extract parameters
        width = parameters.get("width", 832)
        height = parameters.get("height", 480)
        steps = parameters.get("num_inference_steps", 4)
        guidance = parameters.get("guidance_scale", 0.3)

        # Try data-driven prediction first using worker's GPU architecture
        prediction = performance_estimator.predict(
            model_id=model_id,
            gpu_arch=gpu_arch,
            generation_type="image",
            width=width,
            height=height,
            steps=steps,
            guidance=guidance,
        )

        if prediction:
            vram_total, time_estimate = prediction
            logger.debug(
                f"Using learned model for {model_id}: "
                f"VRAM={vram_total:.1f}GB, time={time_estimate:.1f}s"
            )
        else:
            # Fallback to hardcoded estimates
            logger.debug(f"Using hardcoded estimates for {model_id} (insufficient training data)")

            # Base VRAM from your actual measurements (19.3GB for 1920x1080)
            base_vram = 19.3
            base_pixels = 1920 * 1080
            current_pixels = width * height

            # Sublinear scaling based on your measurements
            scaling_factor = (current_pixels / base_pixels) ** 0.8
            vram_total = base_vram * scaling_factor

            # Calculate time based on actual measurements
            base_pixels = 832 * 480
            current_pixels = width * height

            # Time scaling based on your actual data
            base_time = 7.4  # 832x480@4steps actual measurement
            resolution_factor = (current_pixels / base_pixels) ** 0.85  # Sublinear scaling
            steps_factor = steps / 4.0
            guidance_factor = (
                1.0 + (max(guidance - 0.3, 0) / 7.7) * 1.5
            )  # 0.3→8.0 increases time by ~50%

            time_estimate = base_time * resolution_factor * steps_factor * guidance_factor

        return JobEstimate(
            vram_total_needed=vram_total,
            vram_inference_only=(vram_total - 19.3) if model_loaded else vram_total,
            vram_model_base=19.3 if not model_loaded else 0.0,
            model_loaded=model_loaded,
            time_estimate_seconds=max(time_estimate, 5.0),  # Minimum 5 seconds
            worker_available=True,
            recommendations=[],
        )

    def estimate_video_job(
        self, model_id: str, parameters: dict[str, Any], worker_id: str, gpu_arch: str
    ) -> JobEstimate:
        """Estimate VRAM and time for video job.

        Uses data-driven predictions when available, falls back to hardcoded estimates.

        Args:
            model_id: Model identifier
            parameters: Job parameters
            worker_id: Worker identifier
            gpu_arch: GPU architecture (e.g., "gfx1151")
        """
        model_loaded = self.check_model_loaded(worker_id, model_id)

        # Extract parameters
        width = parameters.get("width", 1280)
        height = parameters.get("height", 704)
        frames = parameters.get("num_frames", 36)
        steps = parameters.get("num_inference_steps", 15)

        # Try data-driven prediction first using worker's GPU architecture
        prediction = performance_estimator.predict(
            model_id=model_id,
            gpu_arch=gpu_arch,
            generation_type="video",
            width=width,
            height=height,
            steps=steps,
            frames=frames,
        )

        if prediction:
            vram_total, time_estimate = prediction
            logger.debug(
                f"Using learned model for {model_id}: "
                f"VRAM={vram_total:.1f}GB, time={time_estimate:.1f}s"
            )
        else:
            # Fallback to hardcoded estimates
            logger.debug(f"Using hardcoded estimates for {model_id} (insufficient training data)")

            # Base VRAM from your actual measurements (11.7GB for 1280x704@36frames@15steps)
            base_vram = 11.7
            base_pixels = 1280 * 704
            current_pixels = width * height

            # Sublinear scaling based on your measurements
            scaling_factor = (current_pixels / base_pixels) ** 0.85
            vram_total = base_vram * scaling_factor

            # Calculate time based on actual measurements
            base_pixels = 1280 * 704
            base_frames = 36
            base_steps = 15

            current_pixels = width * height

            # Time scaling based on your actual data (2132s for 1280x704@36frames@15steps)
            base_time = 2132.0  # Your actual measurement in seconds
            resolution_factor = (current_pixels / base_pixels) ** 0.9  # Sublinear scaling
            frames_factor = frames / base_frames
            steps_factor = steps / base_steps

            time_estimate = base_time * resolution_factor * frames_factor * steps_factor

        return JobEstimate(
            vram_total_needed=vram_total,
            vram_inference_only=(vram_total - 11.7) if model_loaded else vram_total,
            vram_model_base=11.7 if not model_loaded else 0.0,
            model_loaded=model_loaded,
            time_estimate_seconds=max(time_estimate, 60.0),  # Minimum 1 minute
            worker_available=True,
            recommendations=[],
        )

    def estimate_assistant_job(
        self, model_id: str, parameters: dict[str, Any], worker_id: str, gpu_arch: str
    ) -> JobEstimate:
        """Estimate VRAM and time for assistant job

        Args:
            model_id: Model identifier
            parameters: Job parameters
            worker_id: Worker identifier
            gpu_arch: GPU architecture (e.g., "gfx1151")
        """
        model_loaded = self.check_model_loaded(worker_id, model_id)

        # VRAM calculation - use actual measurements as base
        width = parameters.get("width", 1920)
        height = parameters.get("height", 1080)

        # Base VRAM from your actual measurements (19.3GB for 1920x1080)
        base_vram = 19.3
        base_pixels = 1920 * 1080
        current_pixels = width * height

        # Sublinear scaling based on your measurements
        scaling_factor = (current_pixels / base_pixels) ** 0.8
        vram_total = base_vram * scaling_factor

        # Time estimation - Qwen2-VL-2B is fast, typically 10-30s per analysis
        # Use 30s as reasonable default (was 300s which is too conservative)
        time_estimate = 30

        return JobEstimate(
            vram_total_needed=vram_total,
            vram_inference_only=(vram_total - 19.3) if model_loaded else vram_total,
            vram_model_base=19.3 if not model_loaded else 0.0,
            model_loaded=model_loaded,
            time_estimate_seconds=time_estimate,
            worker_available=True,
            recommendations=[],
        )

    def estimate_job(
        self,
        job_type: str,
        model_id: str,
        parameters: dict[str, Any],
        worker_id: str,
        gpu_arch: str,
    ) -> JobEstimate:
        """Main estimation function

        Args:
            job_type: Type of job ("image", "video", "assistant")
            model_id: Model identifier
            parameters: Job parameters
            worker_id: Worker identifier
            gpu_arch: GPU architecture (e.g., "gfx1151")
        """
        if job_type == "image":
            return self.estimate_image_job(model_id, parameters, worker_id, gpu_arch)
        elif job_type == "video":
            return self.estimate_video_job(model_id, parameters, worker_id, gpu_arch)
        elif job_type == "assistant":
            return self.estimate_assistant_job(model_id, parameters, worker_id, gpu_arch)
        else:
            raise ValueError(f"Unknown job type: {job_type}")


# Global instance
job_estimator = JobEstimator()
