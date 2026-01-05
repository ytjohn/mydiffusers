#!/usr/bin/env bash
# Restart the client UI server
#
# Usage:
#   bash scripts/restart-client.sh          # Graceful shutdown via API
#   bash scripts/restart-client.sh --force  # Force kill

SCRIPT_DIR=$(dirname "$(realpath "$0")")
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
cd "$PROJECT_ROOT"

# Parse arguments - pass to stop script
STOP_ARGS=""
if [ "$1" == "--force" ]; then
    STOP_ARGS="--force"
fi

# Stop client
bash "$SCRIPT_DIR/stop-client.sh" $STOP_ARGS
if [ $? -ne 0 ]; then
    echo "✗ Failed to stop client"
    exit 1
fi

# Start client
bash "$SCRIPT_DIR/start-client.sh"
if [ $? -ne 0 ]; then
    echo "✗ Failed to start client"
    exit 1
fi

echo ""
echo "✓ Client restarted successfully"
