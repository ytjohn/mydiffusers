"""Text-to-image generator using Z-Image-Turbo."""

import logging
import time

import torch
from diffusers import ZImagePipeline
from PIL import Image

from mydiffuser.config import (
    DEVICE,
    DTYPE,
    IMAGE_MODEL_ID,
    OUTPUT_TYPE,
    WARMUP_GUIDANCE,
    WARMUP_HEIGHT,
    WARMUP_STEPS,
    WARMUP_WIDTH,
)
from mydiffuser.generators.base import BaseGenerator

logger = logging.getLogger(__name__)


class ImageGenerator(BaseGenerator):
    """Text-to-image generator using Tongyi Z-Image-Turbo.

    Optimized for AMD GPUs via ROCm.
    """

    def __init__(self) -> None:
        super().__init__()
        self._pipe: ZImagePipeline | None = None

    def load_model(self) -> None:
        """Load the Z-Image-Turbo pipeline."""
        start_time = time.time()
        logger.info(
            "Loading Z-Image-Turbo model... dtype=%s device=%s",
            DTYPE,
            DEVICE,
        )

        self._pipe = ZImagePipeline.from_pretrained(
            IMAGE_MODEL_ID,
            torch_dtype=DTYPE,
            low_cpu_mem_usage=False,
        ).to(DEVICE)

        self._model = self._pipe
        self._is_loaded = True
        logger.info("Model loaded in %.2fs", time.time() - start_time)

    def warmup(self) -> None:
        """Run a warmup inference to prime the model."""
        self.ensure_loaded()

        logger.info(
            "Running pipeline warmup... height=%d width=%d steps=%d guidance=%.2f",
            WARMUP_HEIGHT,
            WARMUP_WIDTH,
            WARMUP_STEPS,
            WARMUP_GUIDANCE,
        )

        warm_start = time.time()
        assert self._pipe is not None
        _ = self._pipe(  # type: ignore[operator]
            prompt="warmup",
            height=WARMUP_HEIGHT,
            width=WARMUP_WIDTH,
            num_inference_steps=WARMUP_STEPS,
            guidance_scale=WARMUP_GUIDANCE,
            generator=torch.Generator(DEVICE).manual_seed(0),
            output_type=OUTPUT_TYPE,
        )
        torch.cuda.synchronize()
        logger.info("Pipeline warmup completed in %.2fs", time.time() - warm_start)

    def generate(
        self,
        prompt: str,
        height: int,
        width: int,
        num_inference_steps: int,
        guidance_scale: float,
        seed: int,
        run_id: str = "",
    ) -> tuple[Image.Image, float]:
        """Generate an image from a text prompt.

        Args:
            prompt: Text description of the image to generate
            height: Output image height (must be multiple of 8)
            width: Output image width (must be multiple of 8)
            num_inference_steps: Number of denoising steps
            guidance_scale: Classifier-free guidance scale (0.0 for turbo)
            seed: Random seed for reproducibility
            run_id: Optional run ID for logging

        Returns:
            Tuple of (PIL Image, generation time in seconds)
        """
        self.ensure_loaded()

        t0 = time.time()
        logger.info("phase: start, runid=%s", run_id)

        gen = torch.Generator(DEVICE).manual_seed(seed)
        assert self._pipe is not None
        out = self._pipe(  # type: ignore[operator]
            prompt=prompt,
            height=height,
            width=width,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            generator=gen,
            output_type=OUTPUT_TYPE,
        )

        t1 = time.time()
        logger.info("phase: pipe() done in %.2fs, runid=%s", t1 - t0, run_id)

        torch.cuda.synchronize()
        t2 = time.time()
        logger.info("phase: cuda.synchronize done in %.2fs, runid=%s", t2 - t1, run_id)

        img = out.images[0]
        dt = time.time() - t0
        logger.info("phase: total done in %.2fs, runid=%s", dt, run_id)

        return img, dt

