"""Wan2.x image-to-video generator (ROCm/CUDA).

Notes:
- Pipeline runs on DEVICE (usually "cuda" on NVIDIA, "cuda" on ROCm too).
- VAE decode device is controlled by VAE_DEVICE (defaults to DEVICE in config.py).
  - On ROCm, you may want VAE_DEVICE="cpu" for stability / memory constraints.
  - On big NVIDIA GPUs (e.g., H100), VAE_DEVICE="cuda" is usually much faster.
"""

import logging
import time
from pathlib import Path
from typing import Any

import torch
from PIL import Image

from mydiffuser.config import (
    DEVICE,
    DTYPE,
    VAE_DEVICE,
    VAE_DTYPE,
    VIDEO_MODEL_ID,
    configure_torch_backends,
)
from mydiffuser.generators.video.base import BaseVideoGenerator
from mydiffuser.shutdown import check_shutdown, is_shutdown_requested

logger = logging.getLogger(__name__)

CPU_VAE_DTYPE = torch.float32

def _shutdown_callback(
    pipe: Any, step: int, timestep: Any, callback_kwargs: dict
) -> dict:
    """Callback to check for shutdown between inference steps."""
    if step % 5 == 0:
        logger.info("Video inference step %d, timestep %.1f", step, float(timestep))

    if is_shutdown_requested():
        logger.info("Shutdown requested at step %d, aborting video inference", step)
        raise InterruptedError("Video inference interrupted by shutdown request")

    return callback_kwargs


def _decoded_to_pil_frames(decoded: torch.Tensor) -> list[Image.Image]:
    """Convert decoded VAE output tensor into a list of PIL frames."""
    if decoded is None:
        raise RuntimeError("decoded is None")

    x = decoded.detach().to("cpu", dtype=torch.float32)

    # Many VAEs output [-1, 1]; mapping to [0, 1] is usually safe.
    x = (x + 1.0) / 2.0
    x = x.clamp(0.0, 1.0)

    if x.ndim == 5:
        # (B, C, T, H, W) or (B, T, C, H, W)
        if x.shape[1] in (1, 3, 4):
            x = x[0].permute(1, 2, 3, 0)  # (T, H, W, C)
        else:
            x = x[0].permute(0, 2, 3, 1)  # (T, H, W, C)
    elif x.ndim == 4:
        # (B, C, H, W) -> (1, H, W, C)
        x = x[0].permute(1, 2, 0).unsqueeze(0)
    else:
        raise RuntimeError(f"Unexpected decoded ndim={x.ndim}, shape={tuple(x.shape)}")

    x = (x * 255.0).round().to(torch.uint8)

    frames: list[Image.Image] = []
    for t in range(x.shape[0]):
        arr = x[t].numpy()
        if arr.shape[-1] == 4:
            arr = arr[..., :3]
        elif arr.shape[-1] == 1:
            arr = arr.repeat(3, axis=-1)
        frames.append(Image.fromarray(arr, mode="RGB"))

    return frames


def _calculate_output_size(
    input_image: Image.Image, resolution: str = "480p"
) -> tuple[int, int]:
    """Calculate output video size based on input aspect ratio and resolution.

    Args:
        input_image: Input PIL image
        resolution: "480p" or "720p"

    Returns:
        (width, height) tuple for video output

    Notes:
        - Detects landscape vs portrait from input image
        - WAN2.2 native resolution is 720p (1280×704 landscape, 704×1280 portrait)
        - 480p is 832×480 landscape, 480×832 portrait
        - Square images default to landscape (wider dimensions)
    """
    width, height = input_image.size
    is_landscape = width >= height  # >= handles square images as landscape

    if resolution == "720p":
        return (1280, 704) if is_landscape else (704, 1280)
    else:  # 480p (default for backward compatibility)
        return (832, 480) if is_landscape else (480, 832)


class WanVideoGenerator(BaseVideoGenerator):
    """Wan2.2 Image-to-Video generator."""

    def __init__(self, model_id: str | None = None) -> None:
        super().__init__()
        self.model_id = model_id or VIDEO_MODEL_ID
        self._pipe: object | None = None

    def unload(self) -> None:
        if self._pipe is not None:
            try:
                if hasattr(self._pipe, "to"):
                    self._pipe.to("cpu")
            except Exception:
                pass
            del self._pipe
            self._pipe = None

        super().unload()

    def load_model(self) -> None:
        if self._is_loaded:
            logger.info("Wan model already loaded")
            return

        check_shutdown()
        logger.info("Loading Wan I2V model: %s", self.model_id)

        configure_torch_backends()

        try:
            from diffusers import WanImageToVideoPipeline

            self._pipe = WanImageToVideoPipeline.from_pretrained(
                self.model_id,
                torch_dtype=DTYPE,
                low_cpu_mem_usage=True,
                use_safetensors=True,
            )
            self._pipe.to(DEVICE)

            check_shutdown()
            self._is_loaded = True
            logger.info("Wan model loaded successfully")

        except ImportError as e:
            raise RuntimeError(
                "diffusers not installed or Wan pipeline not available. "
                "Make sure you have diffusers >= 0.36.0"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to load Wan model: {e}") from e

    def warmup(self) -> None:
        self.ensure_loaded()
        check_shutdown()
        logger.info("Warming up Wan model...")
        try:
            start = time.perf_counter()
            if callable(self._pipe):
                logger.info("Warmup completed in %.2fs", time.perf_counter() - start)
            else:
                logger.warning("Pipeline not callable, skipping warmup")
        except Exception as e:
            logger.warning("Warmup failed (non-fatal): %s", e)

    def _cleanup_gpu_memory(self, log_prefix: str = "") -> None:
        """Clear GPU memory cache after a run to prevent OOM on subsequent runs."""
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            free_mem = torch.cuda.mem_get_info()[0] / (1024**3)
            total_mem = torch.cuda.mem_get_info()[1] / (1024**3)
            logger.info(
                "%sGPU memory after cleanup: %.1f GiB free / %.1f GiB total",
                log_prefix, free_mem, total_mem
            )

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
        callback_on_step_end = None,
        resolution: str = "480p",
    ) -> tuple[Path, float, int]:
        self.ensure_loaded()
        check_shutdown()

        assert self._pipe is not None, "Pipeline not loaded"

        log_prefix = f"[{run_id}] " if run_id else ""
        logger.info(
            "%sGenerating video: %ds @ %dfps, steps=%d, guidance=%.1f, seed=%d",
            log_prefix,
            int(duration_seconds),
            fps,
            num_inference_steps,
            guidance_scale,
            seed,
        )

        # Calculate number of frames (Wan requirement: (num_frames - 1) divisible by 4)
        num_frames = max(5, int(duration_seconds * fps))
        num_frames = ((num_frames - 1 + 2) // 4) * 4 + 1

        if input_image.mode != "RGB":
            input_image = input_image.convert("RGB")

        generator = torch.Generator(device=DEVICE).manual_seed(seed)

        # Calculate output size based on input aspect ratio and resolution
        output_size = _calculate_output_size(input_image, resolution)
        logger.info(
            "%sOutput resolution: %s, detected %s orientation, size=%dx%d",
            log_prefix,
            resolution,
            "landscape" if output_size[0] > output_size[1] else "portrait",
            output_size[0],
            output_size[1],
        )

        start_time = time.perf_counter()

        try:
            logger.info("%sStarting pipeline inference...", log_prefix)

            # Chain callbacks if custom callback provided
            if callback_on_step_end is not None:
                def _combined_callback(pipe, step_index, timestep, callback_kwargs):
                    # Run shutdown check first
                    shutdown_result = _shutdown_callback(pipe, step_index, timestep, callback_kwargs)
                    # Then run custom callback
                    custom_result = callback_on_step_end(pipe, step_index, timestep, callback_kwargs)
                    return custom_result
                final_callback = _combined_callback
            else:
                final_callback = _shutdown_callback

            result = self._pipe(  # type: ignore[operator]
                image=input_image,
                prompt=prompt,
                num_frames=num_frames,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                generator=generator,
                width=output_size[0],
                height=output_size[1],
                callback_on_step_end=final_callback,
                output_type="latent",
                return_dict=True,
            )

            infer_elapsed = time.perf_counter() - start_time
            logger.info(
                "%sInference complete in %.2fs (latents only)",
                log_prefix, infer_elapsed
            )

            # --- extract latents ---
            if hasattr(result, "frames"):
                latents = result.frames
            elif hasattr(result, "latents"):
                latents = result.latents
            elif isinstance(result, dict):
                latents = result.get("frames") or result.get("latents")
                if latents is None:
                    raise RuntimeError(f"Result keys: {list(result.keys())}")
            else:
                raise RuntimeError(f"Unexpected result type: {type(result)}")

            # Wan commonly returns list-of-one-tensor
            if isinstance(latents, list):
                if len(latents) != 1:
                    raise RuntimeError(
                        f"Expected a single latent tensor, got list of {len(latents)}: "
                        f"{[type(x) for x in latents]}"
                    )
                latents = latents[0]

            if not isinstance(latents, torch.Tensor):
                raise RuntimeError(
                    f"Expected latents to be torch.Tensor, got {type(latents)}"
                )

            logger.info(
                "%sLatents: shape=%s dtype=%s device=%s",
                log_prefix,
                tuple(latents.shape),
                latents.dtype,
                latents.device,
            )

            # Trigger post-processing callback (VAE decode starting)
            if callback_on_step_end is not None:
                try:
                    logger.info("%sTriggering post-processing callback", log_prefix)
                    callback_on_step_end(
                        self._pipe,
                        num_inference_steps,  # Signal completion of denoising
                        0,  # No timestep for post-processing
                        {"phase": "vae_decode"}
                    )
                except Exception as e:
                    logger.warning("%sPost-processing callback failed: %s", log_prefix, e)

            # --- VAE decode ---
            # Device and dtype come from config.py (auto-detected based on ROCm vs CUDA)
            # ROCm: CPU + fp32 (GPU conv3d crashes)
            # CUDA: GPU + fp16 (fast)
            vae_target_device = VAE_DEVICE
            vae_target_dtype = VAE_DTYPE

            if not hasattr(self._pipe, "vae") or self._pipe.vae is None:
                raise RuntimeError("Pipeline has no VAE for decode")

            vae_param = next(self._pipe.vae.parameters())
            vae_orig_device = vae_param.device
            vae_orig_dtype = vae_param.dtype

            moved_vae = False
            decode_start = time.perf_counter()
            try:
                # Move VAE if needed
                need_move = (
                    vae_orig_device.type != vae_target_device
                    or vae_orig_dtype != vae_target_dtype
                )
                if need_move:
                    self._pipe.vae.to(vae_target_device, dtype=vae_target_dtype)
                    moved_vae = True

                logger.info(
                    "%sDecoding latents with VAE on device=%s dtype=%s (moved=%s)",
                    log_prefix,
                    vae_target_device,
                    vae_target_dtype,
                    moved_vae,
                )

                with torch.inference_mode():
                    if vae_target_device == "cpu":
                        # CPU path: latents must be CPU fp32
                        latents_cpu = latents.detach().to("cpu", dtype=torch.float32)
                        decoded = self._pipe.vae.decode(latents_cpu).sample
                    else:
                        # CUDA path: decode on GPU, keep it low-overhead
                        # (Use autocast so decode doesn't upcast unexpectedly.)
                        with torch.autocast("cuda", dtype=vae_target_dtype):
                            decoded = self._pipe.vae.decode(latents).sample

            finally:
                # Restore original VAE placement only if we changed it.
                if moved_vae:
                    self._pipe.vae.to(vae_orig_device, dtype=vae_orig_dtype)

            decode_elapsed = time.perf_counter() - decode_start

            logger.info(
                "%sDecoded: shape=%s dtype=%s device=%s (decode %.2fs)",
                log_prefix,
                tuple(decoded.shape),
                decoded.dtype,
                decoded.device,
                decode_elapsed,
            )

            frames = _decoded_to_pil_frames(decoded)
            logger.info("%sGot %d frames from decode", log_prefix, len(frames))

            elapsed = time.perf_counter() - start_time
            logger.info(
                "%sTotal in %.2fs (infer %.2fs + decode %.2fs + encode pending)",
                log_prefix,
                elapsed,
                infer_elapsed,
                decode_elapsed,
            )

            self._save_video(frames, output_path, fps, log_prefix)

            elapsed2 = time.perf_counter() - start_time
            logger.info("%sSaved video; total complete in %.2fs", log_prefix, elapsed2)

            # Cleanup intermediate tensors and CUDA cache to prevent OOM on next run
            del latents, decoded, frames
            self._cleanup_gpu_memory(log_prefix)

            return output_path, elapsed2, num_frames

        except InterruptedError:
            elapsed = time.perf_counter() - start_time
            logger.info("%sGeneration interrupted after %.2fs", log_prefix, elapsed)
            raise
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.error("%sGeneration failed after %.2fs: %s", log_prefix, elapsed, e)
            raise RuntimeError(f"Video generation failed: {e}") from e

    def _save_video(
        self, frames: list, output_path: Path, fps: int, log_prefix: str = ""
    ) -> None:
        try:
            import imageio
        except ImportError as e:
            msg = "imageio not installed. Install with: pip install imageio[ffmpeg]"
            raise RuntimeError(msg) from e

        output_path.parent.mkdir(parents=True, exist_ok=True)

        import numpy as np

        logger.info("%sConverting %d frames to numpy...", log_prefix, len(frames))
        processed_frames: list[np.ndarray] = []

        for i, frame in enumerate(frames):
            if isinstance(frame, Image.Image):
                arr = np.array(frame)
            elif isinstance(frame, np.ndarray):
                arr = frame
            else:
                arr = np.array(frame)

            if arr.dtype in (np.float32, np.float64):
                arr = (arr * 255).clip(0, 255).astype(np.uint8)

            if arr.ndim == 2:
                arr = np.stack([arr, arr, arr], axis=-1)
            elif arr.ndim == 3 and arr.shape[-1] == 1:
                arr = np.repeat(arr, 3, axis=-1)
            elif arr.ndim == 3 and arr.shape[-1] == 4:
                arr = arr[..., :3]

            processed_frames.append(arr)

            if (i + 1) % 10 == 0:
                logger.info("%sProcessed %d/%d frames", log_prefix, i + 1, len(frames))

        logger.info("%sEncoding %d frames to MP4...", log_prefix, len(processed_frames))

        writer = imageio.get_writer(
            str(output_path),
            fps=fps,
            codec="libx264",
            quality=8,
            pixelformat="yuv420p",
        )

        for frame in processed_frames:
            writer.append_data(frame)

        writer.close()

        logger.info(
            "%sSaved video to %s (%d frames)",
            log_prefix, output_path, len(processed_frames)
        )
