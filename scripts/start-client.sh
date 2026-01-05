#!/usr/bin/env bash
# Start the client UI server
#
# Usage:
#   bash scripts/start-client.sh

SCRIPT_DIR=$(dirname "$(realpath "$0")")
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
cd "$PROJECT_ROOT"
source "$PROJECT_ROOT/.venv/bin/activate"

# Check if client is already running
if pgrep -f "python3 scripts/run_client.py" > /dev/null; then
    echo "✗ Client is already running"
    echo "  Stop it first: bash scripts/stop-client.sh"
    exit 1
fi

echo "Starting client on port 8000 in screen session..."
# Set flag to skip GPU detection (prevents hangs on broken GPU drivers)
export MYDIFFUSER_SKIP_GPU_DETECT=1
screen -dmS client bash -c "cd $PROJECT_ROOT && source .venv/bin/activate && export MYDIFFUSER_SKIP_GPU_DETECT=1; python3 scripts/run_client.py --host 0.0.0.0 --port 8000 2>&1 | tee outputs/logs/client.log"

sleep 2

echo "✓ Client started in screen session 'client'"
echo "Checking health..."
curl -s http://localhost:8000/health | python3 -m json.tool || echo "Client not responding yet"

echo ""
tail -10 outputs/logs/client.log

echo ""
echo "Client UI: http://localhost:8000/"
echo "Local Network: http://$(hostname -I | awk '{print $1}'):8000/"
echo "Or: http://$(hostname).local:8000/ (if using mDNS)"
echo ""
echo "To attach to client session: screen -r client"
echo "To detach from session: Ctrl+A then D"
echo "Logs: tail -f outputs/logs/client.log"
