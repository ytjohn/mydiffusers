"""Centralized configuration for mydiffuser.

Auto-detects ROCm vs CUDA and sets appropriate defaults.
Environment variables can override any setting.
"""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Try to import torch, but don't fail if it's not available
# This allows the client (UI-only) to import config without PyTorch
try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False
    # Create a dummy torch module for type hints
    torch = None  # type: ignore

# ============================================================================
# Platform Detection
# ============================================================================

def _detect_platform() -> str:
    """Detect GPU platform: 'rocm', 'cuda', or 'cpu'."""
    if not _TORCH_AVAILABLE or torch is None:
        return "cpu"

    if not torch.cuda.is_available():
        return "cpu"

    # Check if this is ROCm (AMD) vs CUDA (NVIDIA)
    # ROCm has torch.version.hip set; CUDA has torch.version.cuda
    if hasattr(torch.version, 'hip') and torch.version.hip is not None:
        return "rocm"

    # Double-check via device name (fallback)
    try:
        name = torch.cuda.get_device_name(0).lower()
        if "amd" in name or "radeon" in name or "gfx" in name:
            return "rocm"
    except Exception:
        pass

    return "cuda"


PLATFORM = _detect_platform()
IS_ROCM = PLATFORM == "rocm"
IS_CUDA = PLATFORM == "cuda"
IS_CPU = PLATFORM == "cpu"


# ============================================================================
# Device & Dtype Configuration
# ============================================================================

# Device is always "cuda" for both ROCm and CUDA (ROCm uses CUDA API)
DEVICE = "cuda" if (_TORCH_AVAILABLE and torch is not None and torch.cuda.is_available()) else "cpu"

# --- Main inference dtype ---
# Both ROCm and CUDA: bf16 is a good default (stable, fast)
# Can override with MYDIFFUSER_DTYPE=fp16|fp32|bf16
def _get_dtype_map() -> dict[str, Any]:
    """Get dtype mapping. Returns dummy values if torch not available."""
    if not _TORCH_AVAILABLE or torch is None:
        # Return dummy values for client (won't be used for inference)
        return {
            "fp32": "float32", "float32": "float32",
            "bf16": "bfloat16", "bfloat16": "bfloat16",
            "fp16": "float16", "float16": "float16",
        }
    return {
        "fp32": torch.float32, "float32": torch.float32,
        "bf16": torch.bfloat16, "bfloat16": torch.bfloat16,
        "fp16": torch.float16, "float16": torch.float16,
    }

_DTYPE_MAP = _get_dtype_map()
DTYPE_NAME = os.environ.get("MYDIFFUSER_DTYPE", "bf16").lower()
DTYPE = _DTYPE_MAP.get(DTYPE_NAME, _DTYPE_MAP["bf16"])

# --- VAE decode settings ---
# ROCm (gfx1151): VAE conv3d crashes on GPU, must use CPU + fp32
# CUDA (NVIDIA): VAE on GPU with fp16 is fast and works great
if IS_ROCM:
    _DEFAULT_VAE_DEVICE = "cpu"
    _DEFAULT_VAE_DTYPE = "fp32"
elif IS_CUDA:
    _DEFAULT_VAE_DEVICE = "cuda"
    _DEFAULT_VAE_DTYPE = "fp16"
else:
    _DEFAULT_VAE_DEVICE = "cpu"
    _DEFAULT_VAE_DTYPE = "fp32"

VAE_DEVICE = os.environ.get("MYDIFFUSER_VAE_DEVICE", _DEFAULT_VAE_DEVICE)
VAE_DTYPE_NAME = os.environ.get("MYDIFFUSER_VAE_DTYPE", _DEFAULT_VAE_DTYPE).lower()
VAE_DTYPE = _DTYPE_MAP.get(VAE_DTYPE_NAME, _DTYPE_MAP["fp32"])


# ============================================================================
# SDP Backend Configuration
# ============================================================================

# ROCm: math-only SDP is safest (flash/mem_efficient can crash)
# CUDA: all backends work, let PyTorch choose
# Can override with MYDIFFUSER_FLASH_SDP=1 to enable experimental backends
USE_FLASH_SDP = os.environ.get("MYDIFFUSER_FLASH_SDP", "0") == "1"


def configure_torch_backends():
    """Configure PyTorch backends based on platform.

    Call this early in application startup.
    """
    if not _TORCH_AVAILABLE or torch is None:
        logger.warning("PyTorch not available, skipping backend configuration")
        return

    if not torch.cuda.is_available():
        return

    if IS_ROCM and not USE_FLASH_SDP:
        # ROCm safe mode: math-only SDP
        torch.backends.cuda.enable_flash_sdp(False)
        torch.backends.cuda.enable_mem_efficient_sdp(False)
        torch.backends.cuda.enable_math_sdp(True)
    else:
        # CUDA or experimental mode: enable all backends
        torch.backends.cuda.enable_flash_sdp(True)
        torch.backends.cuda.enable_mem_efficient_sdp(True)
        torch.backends.cuda.enable_math_sdp(True)


# ============================================================================
# Loading Strategy
# ============================================================================

# Lazy loading: models load on first request and swap as needed
# Recommended for most setups (fast startup, memory efficient)
LAZY_LOADING = os.environ.get("MYDIFFUSER_LAZY", "1") == "1"


# ============================================================================
# Paths
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"
RUNS_DIR = OUTPUT_DIR / "run"
WORKER_RUNS_DIR = OUTPUT_DIR / "worker"  # Worker temporary storage (separate from client)
THUMBS_CACHE_DIR = OUTPUT_DIR / ".thumbs"

# Legacy paths (for migration compatibility)
RUNS_IMAGE_DIR = RUNS_DIR / "image"
RUNS_VIDEO_DIR = RUNS_DIR / "video"


def ensure_output_dirs() -> None:
    """Create output directories if they don't exist."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    WORKER_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    THUMBS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_VIDEO_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# Model Settings
# ============================================================================

IMAGE_MODEL_ID = "Tongyi-MAI/Z-Image-Turbo"

# Video generation: enabled by default, disable with MYDIFFUSER_VIDEO=0
VIDEO_ENABLED = os.environ.get("MYDIFFUSER_VIDEO", "1") == "1"

# Video model: 5B (fast, ~10GB) or 14B (quality, ~28GB)
VIDEO_MODEL_SIZE = os.environ.get("MYDIFFUSER_VIDEO_MODEL", "5B")
VIDEO_MODELS = {
    "14B": "Wan-AI/Wan2.2-I2V-A14B-Diffusers",
    "5B": "Wan-AI/Wan2.2-TI2V-5B-Diffusers",
}
VIDEO_MODEL_ID = VIDEO_MODELS.get(VIDEO_MODEL_SIZE, VIDEO_MODELS["5B"])

OUTPUT_TYPE = "pil"

# Warmup settings
WARMUP_HEIGHT = 832
WARMUP_WIDTH = 832
WARMUP_STEPS = 4
WARMUP_GUIDANCE = 0.0

# Thumbnail settings
THUMB_SIZE = 256


# ============================================================================
# Config Summary (for debugging)
# ============================================================================

def get_config_summary() -> dict:
    """Return a summary of current configuration for logging/debugging."""
    summary = {
        "platform": PLATFORM,
        "device": DEVICE,
        "dtype": str(DTYPE).replace("torch.", "") if _TORCH_AVAILABLE else DTYPE,
        "vae_device": VAE_DEVICE,
        "vae_dtype": str(VAE_DTYPE).replace("torch.", "") if _TORCH_AVAILABLE else VAE_DTYPE,
        "lazy_loading": LAZY_LOADING,
        "flash_sdp": USE_FLASH_SDP,
        "video_model": VIDEO_MODEL_SIZE,
        "torch_available": _TORCH_AVAILABLE,
    }

    if _TORCH_AVAILABLE and torch is not None and torch.cuda.is_available():
        try:
            summary["gpu_name"] = torch.cuda.get_device_name(0)
            mem_info = torch.cuda.mem_get_info()
            total_mem = mem_info[1] / (1024**3)
            free_mem = mem_info[0] / (1024**3)
            summary["gpu_memory"] = f"{total_mem:.1f} GiB ({free_mem:.1f} free)"
        except Exception:
            pass

    return summary


def log_config_summary():
    """Log the current configuration summary."""
    summary = get_config_summary()
    logger.info("Configuration: %s", summary)

    # Warn about potential issues
    if IS_ROCM:
        logger.info("ROCm detected: VAE will decode on CPU for stability")
    if VAE_DEVICE == "cpu" and IS_CUDA:
        logger.warning("VAE on CPU but CUDA available - this will be slow")
