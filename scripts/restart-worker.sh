#!/usr/bin/env bash
# Restart the worker server

SCRIPT_DIR=$(dirname "$(realpath "$0")")
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
echo "PROJECT_ROOT=$PROJECT_ROOT"
cd "$PROJECT_ROOT"
source "$PROJECT_ROOT/.venv/bin/activate"
    
echo "Stopping worker..."
# Kill screen session if exists
screen -S worker -X quit 2>/dev/null || true
# Kill any remaining processes
pkill -f "python scripts/run_worker.py" || true

# Wait for process to actually die (max 10 seconds)
for i in {1..10}; do
    if ! pgrep -f "python scripts/run_worker.py" > /dev/null; then
        break
    fi
    echo "Waiting for worker to stop... ($i/10)"
    sleep 1
done

# Force kill if still running
if pgrep -f "python scripts/run_worker.py" > /dev/null; then
    echo "Worker didn't stop gracefully, force killing..."
    pkill -9 -f "python scripts/run_worker.py" || true
    sleep 2
fi

echo "Starting worker on port 8001 in screen session..."
screen -dmS worker bash -c "python scripts/run_worker.py --port 8001 2>&1 | tee /tmp/worker.log"

sleep 3

echo "Worker started in screen session 'worker'"
echo "Checking health..."
curl -s http://localhost:8001/health | python3 -m json.tool || echo "Worker not responding yet (may still be starting up)"

tail -10 /tmp/worker.log


echo ""
echo "To attach to worker session: screen -r worker"
echo "To detach from session: Ctrl+A then D"
echo "Logs: tail -f /tmp/worker.log"

