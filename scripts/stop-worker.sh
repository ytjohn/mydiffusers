#!/usr/bin/env bash
# Stop the worker server
#
# Usage:
#   bash scripts/stop-worker.sh          # Graceful shutdown via API
#   bash scripts/stop-worker.sh --force  # Force kill with SIGTERM/SIGKILL

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

echo "Stopping worker..."

# Check if worker is running
if ! pgrep -f "python scripts/run_worker.py" > /dev/null; then
    echo "Worker is not running"
    exit 0
fi

if [ "$FORCE_KILL" = true ]; then
    # Force mode: immediate SIGTERM -> SIGKILL
    echo "Force killing worker..."

    # Kill screen session
    screen -S worker -X quit 2>/dev/null || true

    # SIGTERM
    pkill -15 -f "python scripts/run_worker.py" 2>/dev/null || true

    # Wait briefly
    for i in {1..5}; do
        if ! pgrep -f "python scripts/run_worker.py" > /dev/null; then
            echo "✓ Worker stopped (SIGTERM)"
            exit 0
        fi
        sleep 1
    done

    # SIGKILL if still running
    if pgrep -f "python scripts/run_worker.py" > /dev/null; then
        echo "Force killing with SIGKILL..."
        pkill -9 -f "python scripts/run_worker.py" 2>/dev/null || true
        sleep 3
    fi
else
    # Graceful mode: API shutdown, wait for natural exit
    echo "Requesting graceful shutdown via API..."

    # Call shutdown endpoint with timeout (model unload can take 10-15s)
    if SHUTDOWN_RESPONSE=$(timeout 20 curl -s -X POST http://localhost:8001/shutdown 2>/dev/null); then
        echo "✓ Shutdown API call succeeded"
        echo "$SHUTDOWN_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$SHUTDOWN_RESPONSE"
    else
        echo "⚠ Shutdown API call failed or timed out"
        echo "   Try: bash scripts/stop-worker.sh --force"
        exit 1
    fi

    # Kill screen session (allows worker to exit cleanly)
    screen -S worker -X quit 2>/dev/null || true

    # Wait for worker to exit naturally (30-60 seconds)
    echo "Waiting for worker to exit naturally (max 60s)..."
    for i in {1..60}; do
        if ! pgrep -f "python scripts/run_worker.py" > /dev/null; then
            echo "✓ Worker exited gracefully after ${i}s"
            exit 0
        fi

        # Progress indicators
        if [ $i -eq 15 ]; then
            echo "  Still waiting... (${i}s elapsed)"
        elif [ $i -eq 30 ]; then
            echo "  Still waiting... (${i}s elapsed)"
        elif [ $i -eq 45 ]; then
            echo "  Still waiting... (${i}s elapsed, consider --force if hung)"
        fi

        sleep 1
    done

    # Check if worker exited
    if pgrep -f "python scripts/run_worker.py" > /dev/null; then
        echo "✗ Worker did not exit after 60s"
        echo "  The GPU may be hung. Try:"
        echo "  1. bash scripts/stop-worker.sh --force"
        echo "  2. Check GPU status: timeout 5 rocminfo"
        echo "  3. Reboot if GPU is in D-state"
        exit 1
    fi
fi

echo "✓ Worker stopped"
