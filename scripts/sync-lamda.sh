#!/usr/bin/env bash

# parent directory of this script
PROJECT_DIR="$(dirname "$(dirname "$(realpath "$0")")")"
cd ${PROJECT_DIR}

TARGET_IP=$1
# default to ubuntu
TARGET_USER=${2:-ubuntu}
TARGET_HOST=${TARGET_USER}@${TARGET_IP}

echo "Syncing project to ${TARGET_HOST}..."

rsync -avh \
  --exclude=output \
  --exclude=outputs \
  --exclude=uv.lock \
  --exclude=uv.lock.* \
  --exclude=.venv/ \
  --exclude=.mypy_cache/ \
  --exclude=.ruff_cache/ \
  --exclude=__pycache__/ \
  . \
  "${TARGET_HOST}:code/"

echo "Done syncing project to ${TARGET_HOST}."
echo "If needed, run install-cuda.sh on ${TARGET_HOST}..."
echo "ssh ${TARGET_HOST} \"cd code && scripts/install-cuda.sh\""
echo "Then run the server with:"
echo "ssh ${TARGET_HOST}"
echo "cd code"
echo "source .venv/bin/activate && python scripts/run_server.py"
echo "---"
echo "Web URL: http://${TARGET_IP}:8000"