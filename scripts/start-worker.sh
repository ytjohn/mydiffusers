#!/usr/bin/env bash
# Start the worker server
#
# Usage:
#   bash scripts/start-worker.sh [--skip-gpu-check]

SCRIPT_DIR=$(dirname "$(realpath "$0")")
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
cd "$PROJECT_ROOT"
source "$PROJECT_ROOT/.venv/bin/activate"

# Parse arguments
SKIP_GPU_CHECK=false
if [ "$1" == "--skip-gpu-check" ]; then
    SKIP_GPU_CHECK=true
    echo "⚠ Skipping GPU health checks"
fi

# Check if worker is already running
if pgrep -f "python scripts/run_worker.py" > /dev/null; then
    echo "✗ Worker is already running"
    echo "  Stop it first: bash scripts/stop-worker.sh"
    exit 1
fi

if [ "$SKIP_GPU_CHECK" = false ]; then
    # Verify GPU is responsive BEFORE waiting (check for immediate hang)
    echo "Checking GPU health..."
    if ! timeout 5 rocminfo > /dev/null 2>&1; then
        echo "ERROR: GPU is not responsive (rocminfo hung)"
        echo "ROCm driver may be in D state - reboot required"
        echo "Check: ps aux | awk '\$8 ~ /D/ {print}'"
        exit 1
    fi

    # Wait for GPU memory to stabilize (ROCm cleanup)
    echo "Waiting for GPU memory to stabilize..."
    sleep 3

    # Verify GPU is still responsive after wait
    echo "Re-checking GPU health..."
    if ! timeout 5 rocminfo > /dev/null 2>&1; then
        echo "ERROR: GPU became unresponsive during wait"
        echo "ROCm driver may be in D state - reboot required"
        exit 1
    fi
fi

echo "Starting worker on port 8001 in screen session..."
# Note: Worker will detect GPU at startup. If GPU hangs during detection, reboot required.
# GPU detection happens in config.py when worker imports PyTorch modules.
screen -dmS worker bash -c "cd $PROJECT_ROOT && source .venv/bin/activate && python scripts/run_worker.py --port 8001 2>&1 | tee outputs/logs/worker.log"

sleep 3

echo "✓ Worker started in screen session 'worker'"
echo "Checking health..."
curl -s http://localhost:8001/health | python3 -m json.tool || echo "Worker not responding yet (may still be starting up)"

echo ""
tail -10 outputs/logs/worker.log

echo ""
echo "To attach to worker session: screen -r worker"
echo "To detach from session: Ctrl+A then D"
echo "Logs: tail -f outputs/logs/worker.log"
