"""Health check and system management endpoints."""

import torch
from fastapi import APIRouter

from mydiffuser.config import (
    DEVICE,
    DTYPE,
    LAZY_LOADING,
    VIDEO_ENABLED,
    get_config_summary,
)
from mydiffuser.server import state
from mydiffuser.utils.presets import PRESETS, VIDEO_PRESETS

router = APIRouter()


@router.post("/unload")
def unload_models():
    """Unload all models and free GPU memory.

    Useful before running large jobs or to recover from OOM situations.
    Models will be reloaded lazily on next generation request.
    """
    return state.unload_all_models()


@router.get("/gpu")
def gpu_status():
    """Return current GPU memory status."""
    if not torch.cuda.is_available():
        return {"available": False}

    free_mem = torch.cuda.mem_get_info()[0] / (1024**3)
    total_mem = torch.cuda.mem_get_info()[1] / (1024**3)
    used_mem = total_mem - free_mem

    return {
        "available": True,
        "device_name": torch.cuda.get_device_name(0),
        "memory": {
            "free_gib": round(free_mem, 1),
            "used_gib": round(used_mem, 1),
            "total_gib": round(total_mem, 1),
            "used_percent": round(used_mem / total_mem * 100, 1),
        },
        "active_model": state.get_active_model(),
    }


@router.get("/gpu/test")
def gpu_test():
    """Run a quick GPU compute test (matrix multiplication).

    This exercises the GPU to verify it's working properly.
    Useful for detecting driver issues, lockups, or ROCm/MIOpen problems.
    Returns timing info and a sample result for verification.
    """
    import time

    if not torch.cuda.is_available():
        return {"ok": False, "error": "No GPU available"}

    try:
        device_name = torch.cuda.get_device_name(0)

        # Small warmup
        warmup = torch.randn(256, 256, device="cuda", dtype=torch.float16)
        _ = warmup @ warmup
        torch.cuda.synchronize()
        del warmup

        # Timed test: 4096x4096 matmul, 10 iterations
        size = 4096
        iterations = 10

        x = torch.randn(size, size, device="cuda", dtype=torch.float16)
        y = torch.randn(size, size, device="cuda", dtype=torch.float16)
        torch.cuda.synchronize()

        t0 = time.perf_counter()
        for _ in range(iterations):
            z = x @ y
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - t0

        # Get a sample value for verification
        sample_value = float(z[0, 0].item())

        # Calculate TFLOPS (2 * N^3 ops per matmul)
        flops_per_matmul = 2 * (size ** 3)
        total_flops = flops_per_matmul * iterations
        tflops = (total_flops / elapsed) / 1e12

        # Cleanup
        del x, y, z
        torch.cuda.empty_cache()

        return {
            "ok": True,
            "device": device_name,
            "test": {
                "size": size,
                "iterations": iterations,
                "elapsed_sec": round(elapsed, 3),
                "tflops": round(tflops, 2),
                "sample_value": round(sample_value, 4),
            },
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }


@router.get("/health")
def health():
    """Return server health status and configuration.

    Includes model loading state for UI to show appropriate loading indicators.
    """
    # Check image generator state
    image_loaded = False
    if state.image_generator is not None:
        image_loaded = state.image_generator.is_loaded

    # Check video generator state
    video_loaded = False
    if state.video_generator is not None:
        video_loaded = state.video_generator.is_loaded

    # Determine active model (which one is currently in GPU memory)
    active_model = state.get_active_model()

    return {
        "ok": True,
        # Full config summary (platform, dtypes, devices, etc.)
        "config": get_config_summary(),
        # Legacy fields for backwards compatibility
        "device": DEVICE,
        "dtype": str(DTYPE),
        "model_loaded": image_loaded,
        # Detailed model state
        "models": {
            "image": {
                "loaded": image_loaded,
                "available": True,
            },
            "video": {
                "loaded": video_loaded,
                "available": VIDEO_ENABLED,
            },
        },
        "active_model": active_model,
        "lazy_loading": LAZY_LOADING,
        "presets": {
            "image": PRESETS,
            "video": VIDEO_PRESETS if VIDEO_ENABLED else {},
        },
    }
