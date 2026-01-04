#!/usr/bin/env bash
# Wrapper script to run Python with ROCm torch preserved
# DO NOT use 'uv run' as it replaces ROCm torch with CUDA version

set -euo pipefail
PROJECT_ROOT=$(dirname "$(dirname "$(realpath "$0")")")
cd "$PROJECT_ROOT"

# Ensure venv exists and has ROCm torch installed
if [ ! -d .venv ]; then
    echo "Error: .venv not found. Run ./scripts/install-rocm.sh first"
    exit 1
fi

# Activate venv
source .venv/bin/activate

# Check if ROCm torch is installed
if ! python -c "import torch; assert 'rocm' in torch.__version__" 2>/dev/null; then
    echo "Warning: ROCm torch not detected. Run ./scripts/install-rocm.sh"
    exit 1
fi

# Run the command
exec python "$@"
