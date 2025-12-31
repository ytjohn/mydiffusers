#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT=$(dirname "$(dirname "$(realpath "$0")")")
cd "$PROJECT_ROOT"

export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null 2>&1 || curl -sSL https://astral.sh/uv/install.sh | sh

[ -d .venv ] || uv venv
source .venv/bin/activate

# Install ROCm PyTorch FIRST (before any dependencies that might pull CUDA version)
uv pip install --pre torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/nightly/rocm7.1

# Then install all other dependencies (with --no-deps for torch-dependent packages to avoid conflicts)
uv sync --group dev --no-install-project

# Finally: editable install of project (rsync-friendly)
uv pip install -e . --no-deps

# Verify we got ROCm
echo ""
echo "=== Verifying ROCm installation ==="
python -c "import torch; print(f'torch: {torch.__version__}'); print(f'hip: {torch.version.hip}'); print(f'cuda: {torch.version.cuda}')"
