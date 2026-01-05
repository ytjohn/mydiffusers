#!/usr/bin/env bash
set -e

# Deploy worker to a remote GPU machine (e.g., Lambda Labs)
# This script syncs code, sets up dependencies, and starts the worker

PROJECT_DIR="$(dirname "$(dirname "$(realpath "$0")")")"
cd "${PROJECT_DIR}"

TARGET_IP=$1
TARGET_USER=${2:-ubuntu}
TARGET_HOST=${TARGET_USER}@${TARGET_IP}
REMOTE_PORT=${3:-8001}
LOCAL_TUNNEL_PORT=${4:-8002}

if [ -z "$TARGET_IP" ]; then
    echo "Usage: $0 <target_ip> [target_user=ubuntu] [remote_port=8001] [local_tunnel_port=8002]"
    echo ""
    echo "Example: $0 123.45.67.89 ubuntu 8001 8002"
    echo ""
    echo "This will:"
    echo "  1. Sync code to ${TARGET_USER}@123.45.67.89:code/"
    echo "  2. Setup Python environment and dependencies"
    echo "  3. Start worker on port 8001"
    echo "  4. Provide SSH tunnel instructions"
    exit 1
fi

echo "==== Deploying Worker to ${TARGET_HOST} ===="
echo ""

# 1. Sync code to remote
echo "📦 Step 1/4: Syncing code to ${TARGET_HOST}..."
rsync -avh \
  -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
  --exclude=outputs/ \
  --exclude=output/ \
  --exclude=uv.lock \
  --exclude=uv.lock.* \
  --exclude=.venv/ \
  --exclude=.mypy_cache/ \
  --exclude=.ruff_cache/ \
  --exclude=__pycache__/ \
  --exclude=.git/ \
  . \
  "${TARGET_HOST}:code/"

echo "✓ Code synced"
echo ""

# 2. Setup environment and dependencies with CUDA support
echo "🔧 Step 2/4: Setting up Python environment with CUDA..."
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "${TARGET_HOST}" bash <<'REMOTE_SETUP'
set -e
cd code
export PATH="$HOME/.local/bin:$PATH"

# Run the install-cuda.sh script which handles everything:
# - uv installation
# - venv creation
# - dependency installation with uv sync
# - PyTorch with CUDA wheels
echo "Running install-cuda.sh..."
bash scripts/install-cuda.sh

echo "✓ Environment ready with CUDA support"
REMOTE_SETUP

echo "✓ Environment setup complete"
echo ""

# 3. Start worker
echo "🚀 Step 3/4: Starting worker on port ${REMOTE_PORT}..."
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "${TARGET_HOST}" bash -s "${REMOTE_PORT}" <<'REMOTE_START'
set -e
REMOTE_PORT=$1
cd ~/code
export PATH="$HOME/.local/bin:$PATH"

# Kill any existing screen session named "worker"
echo "Stopping any existing worker screen session..."
screen -S worker -X quit 2>/dev/null || true
sleep 1

# Also kill any stray worker processes
pkill -f "python scripts/run_worker.py" || true
sleep 1

# Get absolute path to code directory
CODE_DIR="$HOME/code"

# Start worker in a detached screen session
echo "Starting worker in screen session 'worker' on port $REMOTE_PORT..."
mkdir -p $CODE_DIR/outputs/logs
screen -dmS worker bash -c "cd $CODE_DIR && source .venv/bin/activate && python scripts/run_worker.py --port $REMOTE_PORT 2>&1 | tee outputs/logs/worker.log"

# Give it a moment to start
sleep 3

# Wait for worker to start
echo "Waiting for worker to start..."
for i in {1..10}; do
    if curl -s http://localhost:$REMOTE_PORT/health > /dev/null 2>&1; then
        echo "✓ Worker started successfully!"
        echo "✓ Worker running in screen session 'worker'"
        echo ""
        echo "To view worker logs:"
        echo "  ssh -t ${TARGET_HOST} 'screen -r worker'"
        echo "  (Press Ctrl+A then D to detach without stopping)"
        echo ""
        echo "Or view log file:"
        echo "  ssh ${TARGET_HOST} 'tail -f $CODE_DIR/outputs/logs/worker.log'"
        exit 0
    fi
    sleep 1
done

echo "⚠️  Worker may still be starting. Check logs with: tail -f $CODE_DIR/outputs/logs/worker.log"
echo "Last 20 lines of log:"
tail -20 $CODE_DIR/outputs/logs/worker.log 2>/dev/null || echo "Log file not created yet"
REMOTE_START

echo "✓ Worker started"
echo ""

# 4. Setup SSH tunnel instructions
echo "🔗 Step 4/4: SSH Tunnel Setup"
echo ""
echo "To use this worker from your local client, set up an SSH tunnel:"
echo ""
echo "  ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -N -L ${LOCAL_TUNNEL_PORT}:localhost:${REMOTE_PORT} ${TARGET_HOST}"
echo ""
echo "This creates a tunnel:"
echo "  localhost:${LOCAL_TUNNEL_PORT} → ${TARGET_HOST}:${REMOTE_PORT}"
echo ""
echo "Then update your client config:"
echo "  src/mydiffuser/client/config.py"
echo ""
echo "Add a remote worker:"
echo "  WORKERS = {"
echo "      \"local\": {\"endpoint\": \"http://localhost:8001\"},"
echo "      \"remote\": {\"endpoint\": \"http://localhost:${LOCAL_TUNNEL_PORT}\"},"
echo "  }"
echo ""
echo "==== Deployment Complete! ===="
echo ""
echo "Next steps:"
echo "  1. Open a new terminal and run the SSH tunnel command above"
echo "  2. Test worker health: curl http://localhost:${LOCAL_TUNNEL_PORT}/health"
echo "  3. Start your client: bash scripts/restart-client.sh"
echo "  4. Submit a job via the UI and select 'remote' worker"
echo ""
echo "To check worker logs:"
echo "  ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -t ${TARGET_HOST} 'screen -r worker'  # Live view (Ctrl+A D to detach)"
echo "  ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ${TARGET_HOST} 'tail -f $CODE_DIR/outputs/logs/worker.log'  # Log file"
echo ""
echo "To stop the remote worker:"
echo "  ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ${TARGET_HOST} 'screen -S worker -X quit'"
