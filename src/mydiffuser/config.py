"""Centralized configuration for mydiffuser.

AMD Max+ 395 (gfx1201) specific settings and global paths.
"""

import os
from pathlib import Path

import torch

# ---- AMD ROCm Workarounds ----
# "Mem Efficient attention on Current AMD GPU is still experimental…"
# Must be set before numpy/torch imports in entry points
os.environ.setdefault("PYTORCH_SDP_BACKEND", "math")


# ---- Device & Dtype ----
DEVICE = "cuda"  # ROCm uses cuda API

# Pick what is stable for your GPU:
# - float32: safest but slowest
# - bfloat16: faster, good stability on gfx1201
# - float16: fastest but can cause memory faults on some workloads
DTYPE = torch.bfloat16


def configure_torch_backends():
    """Configure PyTorch backends for AMD stability.

    Call this early in application startup.
    """
    # Disable experimental SDP backends, use math instead
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(True)


# ---- Paths ----
# config.py -> mydiffuser/ -> src/ -> PROJECT_ROOT
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"
RUNS_DIR = OUTPUT_DIR / "run"
RUNS_IMAGE_DIR = RUNS_DIR / "image"
RUNS_VIDEO_DIR = RUNS_DIR / "video"


def ensure_output_dirs():
    """Create output directories if they don't exist."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_VIDEO_DIR.mkdir(parents=True, exist_ok=True)


# ---- Model Settings ----
IMAGE_MODEL_ID = "Tongyi-MAI/Z-Image-Turbo"
OUTPUT_TYPE = "pil"  # Return PIL images from pipeline

# Warmup settings
WARMUP_HEIGHT = 832
WARMUP_WIDTH = 832
WARMUP_STEPS = 4
WARMUP_GUIDANCE = 0.0

