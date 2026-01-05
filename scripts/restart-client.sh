#!/usr/bin/env bash
# Restart the client UI server
SCRIPT_DIR=$(dirname "$(realpath "$0")")
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
cd "$PROJECT_ROOT"
source "$PROJECT_ROOT/.venv/bin/activate"

echo "Stopping client..."
# Kill screen session if exists
screen -S client -X quit 2>/dev/null || true
# Kill any remaining processes
pkill -f "python3 scripts/run_client.py" || true

# Wait for process to actually die (max 5 seconds)
for i in {1..5}; do
    if ! pgrep -f "python3 scripts/run_client.py" > /dev/null; then
        break
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

echo "Starting client on port 8000 in screen session..."
# Set flag to skip GPU detection (prevents hangs on broken GPU drivers)

export MYDIFFUSER_SKIP_GPU_DETECT=1
screen -dmS client bash -c "export MYDIFFUSER_SKIP_GPU_DETECT=1; python3 scripts/run_client.py --host 0.0.0.0 --port 8000 2>&1 | tee outputs/logs/client.log"

sleep 2

echo "Client started in screen session 'client'"
echo "Checking health..."
curl -s http://localhost:8000/health | python3 -m json.tool || echo "Client not responding yet"
tail -10 outputs/logs/client.log
echo ""
echo "Client UI: http://localhost:8000/"
echo "Local Network http://$(hostname -I | awk '{print $1}'):8000/ (if running on local network)"
echo "Or http://$(hostname).local:8000/ (if using local DNS); http://$(hostname | awk '{print $1}'):8000/ (if using mDNS)"
echo "To attach to client session: "
echo  "screen -r client"
echo "To detach from session: Ctrl+A then D"
echo "Logs: "
echo "tail -f outputs/logs/client.log"

