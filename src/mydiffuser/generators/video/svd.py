"""Stable Video Diffusion backend (placeholder for future implementation)."""

import logging
from pathlib import Path

from PIL import Image

from mydiffuser.generators.video.base import BaseVideoGenerator

logger = logging.getLogger(__name__)


class SVDGenerator(BaseVideoGenerator):
    """Stable Video Diffusion image-to-video generator.

    TODO: Implement using diffusers StableVideoDiffusionPipeline
    once ROCm compatibility is verified.
    """

    def load_model(self) -> None:
        """Load the SVD pipeline."""
        raise NotImplementedError(
            "SVD generator not yet implemented. "
            "Requires StableVideoDiffusionPipeline and ROCm compatibility testing."
        )

    def warmup(self) -> None:
        """Run warmup inference."""
        raise NotImplementedError("SVD generator not yet implemented")

    def generate(
        self,
        input_image: Image.Image,
        prompt: str,
        fps: int,
        duration_seconds: float,
        num_inference_steps: int,
        guidance_scale: float,
        seed: int,
        output_path: Path,
        run_id: str = "",
    ) -> tuple[Path, float, int]:
        """Generate video from image."""
        raise NotImplementedError("SVD generator not yet implemented")
