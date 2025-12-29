#!/usr/bin/env bash
# Restart the client UI server

echo "Stopping client..."
# Kill screen session if exists
screen -S client -X quit 2>/dev/null || true
# Kill any remaining processes
pkill -f "python scripts/run_client.py" || true

# Wait for process to actually die (max 5 seconds)
for i in {1..5}; do
    if ! pgrep -f "python scripts/run_client.py" > /dev/null; then
        break
    fi
    echo "Waiting for client to stop... ($i/5)"
    sleep 1
done

# Force kill if still running
if pgrep -f "python scripts/run_client.py" > /dev/null; then
    echo "Client didn't stop gracefully, force killing..."
    pkill -9 -f "python scripts/run_client.py" || true
    sleep 1
fi

echo "Starting client on port 8000 in screen session..."
screen -dmS client bash -c "python scripts/run_client.py --host 0.0.0.0 --port 8000 2>&1 | tee /tmp/client.log"

sleep 2

echo "Client started in screen session 'client'"
echo "Checking health..."
curl -s http://localhost:8000/health | python -m json.tool || echo "Client not responding yet"
echo ""
echo "Client UI: http://localhost:8000/"
echo "To attach to client session: screen -r client"
echo "To detach from session: Ctrl+A then D"
echo "Logs: tail -f /tmp/client.log"
