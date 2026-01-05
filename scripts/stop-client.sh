#!/usr/bin/env bash
# Stop the client UI server
#
# Usage:
#   bash scripts/stop-client.sh          # Graceful shutdown via API
#   bash scripts/stop-client.sh --force  # Force kill with SIGTERM/SIGKILL

SCRIPT_DIR=$(dirname "$(realpath "$0")")
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
cd "$PROJECT_ROOT"
source "$PROJECT_ROOT/.venv/bin/activate"

# Parse arguments
FORCE_KILL=false
if [ "$1" == "--force" ]; then
    FORCE_KILL=true
    echo "⚠ Force kill mode enabled"
fi

echo "Stopping client..."

# Check if client is running
if ! pgrep -f "python3 scripts/run_client.py" > /dev/null; then
    echo "Client is not running"
    exit 0
fi

if [ "$FORCE_KILL" = false ]; then
    # Try graceful shutdown via API first
    if curl -s -X POST http://localhost:8000/shutdown > /dev/null 2>&1; then
        echo "✓ Shutdown API call succeeded"
    else
        echo "⚠ Shutdown API call failed, using pkill"
    fi
fi

# Kill screen session if exists
screen -S client -X quit 2>/dev/null || true

# Kill any remaining processes
pkill -f "python3 scripts/run_client.py" || true

# Wait for process to actually die (max 5 seconds)
for i in {1..5}; do
    if ! pgrep -f "python3 scripts/run_client.py" > /dev/null; then
        echo "✓ Client stopped"
        exit 0
    fi
    echo "Waiting for client to stop... ($i/5)"
    sleep 1
done

# Force kill if still running
if pgrep -f "python3 scripts/run_client.py" > /dev/null; then
    echo "Client didn't stop gracefully, force killing..."
    pkill -9 -f "python3 scripts/run_client.py" || true
    sleep 1
fi

echo "✓ Client stopped"
