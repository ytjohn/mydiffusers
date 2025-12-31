#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(dirname "$(realpath "$0")")")"

export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null 2>&1 || curl -sSL https://astral.sh/uv/install.sh | sh

[ -d .venv ] || uv venv
source .venv/bin/activate

# Install CUDA PyTorch FIRST (before any dependencies that might pull wrong version)
: "${TORCH_CUDA_INDEX_URL:=https://download.pytorch.org/whl/cu124}"
uv pip install torch torchvision torchaudio --index-url "$TORCH_CUDA_INDEX_URL"

# Then install all other dependencies (with --no-deps for torch-dependent packages to avoid conflicts)
uv sync --group dev --no-install-project

# Finally: editable install of project (rsync-friendly)
uv pip install -e . --no-deps

# Verify
echo ""
echo "=== Verifying CUDA installation ==="
python -c "import torch; print(f'torch: {torch.__version__}'); print(f'cuda: {torch.version.cuda}'); print(f'gpu: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"none\"}')"
