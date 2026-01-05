#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT=$(dirname "$(dirname "$(realpath "$0")")")
cd "$PROJECT_ROOT"

export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null 2>&1 || curl -sSL https://astral.sh/uv/install.sh | sh

[ -d .venv ] || uv venv
source .venv/bin/activate

# Install ROCm PyTorch FIRST (explicit wheel install bypasses broken triton deps)
# Using ROCm 7.1 nightly index (stable version for gfx1151)
# Note: ROCm 7.11 gfx1151-specific nightlies tested but had worker restart issues
uv pip install --pre torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/nightly/rocm7.1

# Install transformers from GitHub (required for Qwen2-VL support)
uv pip install git+https://github.com/huggingface/transformers

# Install all other dependencies manually (skipping uv sync to avoid torch replacement)
uv pip install \
  "accelerate>=1.12.0" \
  "diffusers>=0.36.0" \
  "fastapi>=0.127.0" \
  "ftfy>=6.3.0" \
  "httpx>=0.28.0" \
  "imageio[ffmpeg]>=2.34.0" \
  "jinja2>=3.1.0" \
  "numpy>=2.4.0" \
  "pillow>=12.0.0" \
  "python-multipart>=0.0.9" \
  "qwen-vl-utils>=0.0.8" \
  "uvicorn>=0.40.0"

# Dev dependencies
uv pip install \
  "pytest>=8.0.0" \
  "ruff>=0.4.0" \
  "mypy>=1.10.0" \
  "pip"

# Finally: editable install of project (rsync-friendly)
uv pip install -e . --no-deps

# Verify we got ROCm
echo ""
echo "=== Verifying ROCm installation ==="
python -c "import torch; print(f'torch: {torch.__version__}'); print(f'hip: {torch.version.hip}'); print(f'cuda: {torch.version.cuda}')"
echo ""
echo "⚠️  IMPORTANT: Do NOT use 'uv run' - it will replace ROCm torch with CUDA!"
echo "   Use './scripts/run.sh' or activate venv first: source .venv/bin/activate"
