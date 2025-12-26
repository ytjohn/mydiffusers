"""Base class for video generation backends."""

import logging
from abc import abstractmethod
from pathlib import Path

from PIL import Image

from mydiffuser.generators.base import BaseGenerator

logger = logging.getLogger(__name__)


class BaseVideoGenerator(BaseGenerator):
    """Abstract base class for image-to-video generators.

    Subclasses implement specific backends (SVD, Tune-A-Video, etc.)
    """

    @abstractmethod
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
        """Generate a video from an input image and motion prompt.

        Args:
            input_image: Source PIL Image
            prompt: Motion/animation prompt
            fps: Frames per second
            duration_seconds: Video duration
            num_inference_steps: Denoising steps
            guidance_scale: Classifier-free guidance scale
            seed: Random seed
            output_path: Where to save the output video
            run_id: Optional run ID for logging

        Returns:
            Tuple of (output_path, generation_time_seconds, num_frames)
        """
