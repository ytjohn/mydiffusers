"""
VRAM Prediction Utility for MyDiffuser

Provides accurate GPU memory usage predictions for image and video generation
tasks based on model parameters and system configuration.
"""

import logging
import math
from dataclasses import dataclass
from typing import Any, ClassVar

import torch

logger = logging.getLogger(__name__)


@dataclass
class VRAMEstimate:
    """Container for VRAM usage estimates"""

    model_base_gb: float
    resolution_factor: float
    frame_factor: float = 1.0
    batch_factor: float = 1.0
    dtype_factor: float = 1.0
    safety_buffer_gb: float = 2.0
    total_estimate_gb: float = 0.0
    available_gb: float = 0.0
    is_safe: bool = True


class VRAMPredictor:
    """
    Predicts GPU VRAM usage for diffusion models based on empirical data
    and theoretical calculations.
    """

    # Base model sizes (GB) - measured from YOUR actual baseline results
    MODEL_SIZES: ClassVar[dict[str, dict[str, float]]] = {
        "image": {
            "z-image-turbo": 19.3,  # YOUR measured baseline - 1920x1080 image generation
            "stable-diffusion-xl": 19.3,  # Same as yours
            "stable-diffusion-1.5": 19.3,  # Same as yours
        },
        "video": {
            "wan-2.1-5b": 11.7,  # YOUR measured baseline - 1280x704 video generation
            "wan-2.1-14b": 27.5,  # Conservative estimate
        },
        "assistant": {
            "qwen2-vl-7b": 13.4,  # YOUR measured baseline
            "qwen2-vl-2b": 4.1,  # YOUR measured baseline
        },
    }

    # Resolution multipliers (relative to 512x512 baseline)
    RESOLUTION_MULTIPLIERS: ClassVar[dict[str, dict[int | tuple[int, int], float]]] = {
        "square": {
            256: 0.25,
            384: 0.56,
            512: 1.0,
            768: 2.25,
            1024: 4.0,
            1152: 5.06,
            1280: 6.25,
            1536: 9.0,
        },
        "widescreen": {
            (512, 288): 0.56,
            (768, 432): 1.27,
            (1024, 576): 2.25,
            (1152, 648): 2.85,
            (1280, 720): 3.52,
            (1536, 864): 5.06,
            (1920, 1080): 7.91,
        },
    }

    # Data type memory factors
    DTYPE_FACTORS: ClassVar[dict[str, float]] = {
        "float32": 1.0,
        "float16": 0.5,
        "bfloat16": 0.5,
        "int8": 0.25,
    }

    def __init__(self):
        """Initialize VRAM predictor with current GPU info"""
        self.gpu_info = self._get_gpu_info()

    def _get_gpu_info(self) -> dict[str, Any]:
        """Get current GPU information"""
        if not torch.cuda.is_available():
            return {"available": False, "total_gb": 0, "free_gb": 0}

        try:
            total_bytes = torch.cuda.get_device_properties(0).total_memory
            free_bytes, _ = torch.cuda.mem_get_info()

            return {
                "available": True,
                "total_gb": total_bytes / (1024**3),
                "free_gb": free_bytes / (1024**3),
                "device_name": torch.cuda.get_device_name(0),
                "compute_capability": torch.cuda.get_device_capability(0),
            }
        except Exception as e:
            logger.warning(f"Failed to get GPU info: {e}")
            return {"available": False, "total_gb": 0, "free_gb": 0}

    def estimate_image_vram(
        self,
        model_name: str = "z-image-turbo",
        width: int = 512,
        height: int = 512,
        batch_size: int = 1,
        dtype: str = "float16",
        num_inference_steps: int = 20,
        guidance_scale: float = 0.0,
    ) -> VRAMEstimate:
        """
        Estimate VRAM usage for image generation

        Args:
            model_name: Name of the image model
            width: Image width in pixels
            height: Image height in pixels
            batch_size: Number of images to generate simultaneously
            dtype: Data type (float32, float16, bfloat16)
            num_inference_steps: Number of denoising steps

        Returns:
            VRAMEstimate object with detailed breakdown
        """
        # Get base model size (your actual measurement)
        model_base = self.MODEL_SIZES["image"].get(
            model_name, self.MODEL_SIZES["image"]["z-image-turbo"]
        )

        # Calculate scaling based on your actual 19.3GB for 1920x1080
        base_pixels = 1920 * 1080  # Your baseline resolution
        current_pixels = width * height

        # Sublinear scaling based on pixel count
        scaling_factor = (current_pixels / base_pixels) ** 0.8
        scaled_estimate = model_base * scaling_factor

        # Apply batch size and dtype factors
        dtype_factor = self.DTYPE_FACTORS.get(dtype, 0.5)
        batch_factor = max(1.0, batch_size)

        total_estimate = scaled_estimate * batch_factor * dtype_factor

        return VRAMEstimate(
            model_base_gb=model_base,
            resolution_factor=scaling_factor,
            batch_factor=batch_factor,
            dtype_factor=dtype_factor,
            safety_buffer_gb=2.0,
            total_estimate_gb=total_estimate,
            available_gb=self.gpu_info["free_gb"],
            is_safe=total_estimate < self.gpu_info["free_gb"] * 0.9,
        )

    def estimate_video_vram(
        self,
        model_name: str = "wan-2.1-5b",
        width: int = 832,
        height: int = 480,
        num_frames: int = 16,
        batch_size: int = 1,
        dtype: str = "float16",
        num_inference_steps: int = 20,
        guidance_scale: float = 3.0,
    ) -> VRAMEstimate:
        """
        Estimate VRAM usage for video generation

        Args:
            model_name: Name of the video model (5B or 14B)
            width: Video width in pixels
            height: Video height in pixels
            num_frames: Number of frames to generate
            batch_size: Number of videos to generate simultaneously
            dtype: Data type (float32, float16, bfloat16)
            num_inference_steps: Number of denoising steps

        Returns:
            VRAMEstimate object with detailed breakdown
        """
        # Get base model size (your actual measurement)
        model_base = self.MODEL_SIZES["video"].get(
            model_name, self.MODEL_SIZES["video"]["wan-2.1-5b"]
        )

        # Calculate scaling based on your actual 11.7GB for 1280x704@36frames
        base_pixels = 1280 * 704  # Your baseline resolution for video
        base_frames = 36  # Your baseline frames for video

        current_pixels = width * height
        current_frames = num_frames

        # Sublinear scaling for both pixels and frames
        pixel_factor = max(0.5, (current_pixels / base_pixels) ** 0.7)
        frame_factor = max(0.3, (current_frames / base_frames) ** 0.6)

        scaled_estimate = model_base * pixel_factor * frame_factor

        # Apply batch size and dtype factors
        dtype_factor = self.DTYPE_FACTORS.get(dtype, 0.5)
        batch_factor = max(1.0, batch_size)

        total_estimate = scaled_estimate * batch_factor * dtype_factor

        return VRAMEstimate(
            model_base_gb=model_base,
            resolution_factor=pixel_factor,
            frame_factor=frame_factor,
            batch_factor=batch_factor,
            dtype_factor=dtype_factor,
            safety_buffer_gb=3.0,
            total_estimate_gb=total_estimate,
            available_gb=self.gpu_info["free_gb"],
            is_safe=total_estimate < self.gpu_info["free_gb"] * 0.85,
        )

    def estimate_assistant_vram(
        self,
        model_name: str = "qwen2-vl-7b",
        max_sequence_length: int = 2048,
        batch_size: int = 1,
        dtype: str = "float16",
    ) -> VRAMEstimate:
        """
        Estimate VRAM usage for language/vision models

        Args:
            model_name: Name of the assistant model
            max_sequence_length: Maximum input sequence length
            batch_size: Batch size for processing
            dtype: Data type

        Returns:
            VRAMEstimate object
        """
        model_base = self.MODEL_SIZES["assistant"].get(
            model_name, self.MODEL_SIZES["assistant"]["qwen2-vl-7b"]
        )

        dtype_factor = self.DTYPE_FACTORS.get(dtype, 0.5)

        # Sequence length has significant impact on memory
        seq_factor = max(1.0, (max_sequence_length or 2048) / 2048.0)

        total_estimate = (
            model_base * dtype_factor + (seq_factor * batch_size * 0.5) + 1.0
        )

        return VRAMEstimate(
            model_base_gb=model_base,
            resolution_factor=1.0,
            batch_factor=batch_size,
            dtype_factor=dtype_factor,
            safety_buffer_gb=1.0,
            total_estimate_gb=total_estimate,
            available_gb=self.gpu_info["free_gb"],
            is_safe=total_estimate < self.gpu_info["free_gb"] * 0.9,
        )

    def _calculate_resolution_factor(self, width: int, height: int) -> float:
        """Calculate resolution scaling factor relative to 512x512"""
        width = width or 512
        height = height or 512
        base_pixels = 512 * 512
        current_pixels = width * height

        # Use square root scaling - memory grows with sqrt of pixel count
        # This accounts for attention mechanisms and other factors
        return math.sqrt(current_pixels / base_pixels)

    def check_compatibility(self, model_type: str, **kwargs) -> dict[str, Any]:
        """
        Check if a generation request is compatible with available VRAM

        Args:
            model_type: 'image', 'video', or 'assistant'
            **kwargs: Model-specific parameters

        Returns:
            Dictionary with compatibility info and recommendations
        """
        if model_type == "image":
            estimate = self.estimate_image_vram(**kwargs)
        elif model_type == "video":
            estimate = self.estimate_video_vram(**kwargs)
        elif model_type == "assistant":
            estimate = self.estimate_assistant_vram(**kwargs)
        else:
            raise ValueError(f"Unknown model type: {model_type}")

        recommendations = []
        if not estimate.is_safe:
            free_gb = estimate.available_gb
            needed_gb = estimate.total_estimate_gb

            if model_type == "video" and kwargs.get("model_name") == "wan-2.1-14b":
                recommendations.append(
                    "Switch to wan-2.1-5b model to reduce VRAM usage"
                )

            if kwargs.get("width", 1024) > 768 or kwargs.get("height", 1024) > 768:
                recommendations.append("Reduce resolution to 768x768 or lower")

            if kwargs.get("batch_size", 1) > 1:
                recommendations.append("Reduce batch size to 1")

            if kwargs.get("num_frames", 16) > 16:
                recommendations.append("Reduce frame count to 16 or lower")

            recommendations.append(
                f"Consider freeing up approximately {needed_gb - free_gb:.1f}GB of VRAM"
            )

        return {
            "estimate": estimate,
            "compatible": estimate.is_safe,
            "recommendations": recommendations,
            "free_gb": estimate.available_gb,
            "needed_gb": estimate.total_estimate_gb,
        }

    def get_system_summary(self) -> dict[str, Any]:
        """Get comprehensive system VRAM summary"""
        return {
            "gpu_info": self.gpu_info,
            "model_sizes": self.MODEL_SIZES,
            "current_status": {
                "free_gb": self.gpu_info["free_gb"],
                "total_gb": self.gpu_info["total_gb"],
                "utilization": 1.0
                - (self.gpu_info["free_gb"] / max(self.gpu_info["total_gb"], 1)),
            },
        }


# Global instance for easy access
vram_predictor = VRAMPredictor()
