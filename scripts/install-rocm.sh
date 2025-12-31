#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT=$(dirname "$(dirname "$(realpath "$0")")")
cd "$PROJECT_ROOT"

export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null 2>&1 || curl -sSL https://astral.sh/uv/install.sh | sh

[ -d .venv ] || uv venv
source .venv/bin/activate

# First: install everything from pyproject.toml (will install CUDA torch)
uv sync --group dev

# Then: OVERWRITE with ROCm nightly torch (must be AFTER uv sync)
uv pip install -U --pre torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/nightly/rocm7.1

# Editable install so rsync updates work
uv pip install -e .

# Verify we got ROCm
echo ""
echo "=== Verifying ROCm installation ==="
python -c "import torch; print(f'torch: {torch.__version__}'); print(f'hip: {torch.version.hip}'); print(f'cuda: {torch.version.cuda}')"
