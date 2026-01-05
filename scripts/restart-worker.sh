#!/usr/bin/env bash
# Restart the worker server
#
# Usage:
#   bash scripts/restart-worker.sh          # Graceful shutdown via API
#   bash scripts/restart-worker.sh --force  # Force kill with SIGTERM/SIGKILL

SCRIPT_DIR=$(dirname "$(realpath "$0")")
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
echo "PROJECT_ROOT=$PROJECT_ROOT"
cd "$PROJECT_ROOT"

# Parse arguments - pass to stop script
STOP_ARGS=""
if [ "$1" == "--force" ]; then
    STOP_ARGS="--force"
fi

# Stop worker
bash "$SCRIPT_DIR/stop-worker.sh" $STOP_ARGS
if [ $? -ne 0 ]; then
    echo "✗ Failed to stop worker"
    exit 1
fi

# Start worker
bash "$SCRIPT_DIR/start-worker.sh"
if [ $? -ne 0 ]; then
    echo "✗ Failed to start worker"
    exit 1
fi

echo ""
echo "✓ Worker restarted successfully"
