#!/usr/bin/env bash

# parent directory of this script
PROJECT_DIR="$(dirname "$(dirname "$(realpath "$0")")")"
cd ${PROJECT_DIR}

TARGET_IP=$1
# default to ubuntu
TARGET_USER=${2:-ubuntu}
TARGET_HOST=${TARGET_USER}@${TARGET_IP}
echo "Syncing project to ${TARGET_HOST}..."

# pull code/outputs down to $PROJECT_DIR/
rsync -avh \
  "${TARGET_HOST}:code/outputs/" \
  "${PROJECT_DIR}/outputs/"
