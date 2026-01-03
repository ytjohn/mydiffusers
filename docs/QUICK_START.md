# Quick Start After Reboot

## Option 1: Old Server (Safe, Working)
```bash
python scripts/run_server.py
# Access at http://localhost:8000
```

## Option 2: New Client/Worker Architecture

### Start Both Services
```bash
# Worker (GPU inference)
bash scripts/restart-worker.sh

# Client (UI)
bash scripts/restart-client.sh

# Access client at http://localhost:8000
```

### Test Lazy Loading Carefully
```bash
# 1. Check worker started cleanly
tail -f /tmp/worker.log
# Should show: "Worker startup complete" and "Models will load lazily on first request"

# 2. Submit ONE image job via http://localhost:8000/generate/image
# Watch logs for model loading on first request

# 3. Wait for completion, then submit ONE video job
# Watch for model swap in logs

# If GPU hangs again:
# - Note what was happening in logs
# - Reboot required to clear
# - We'll need to debug the lazy loading implementation
```

## Logs
```bash
# Worker logs
tail -f /tmp/worker.log

# Client logs
tail -f /tmp/client.log
```

## Stop Services
```bash
pkill -f "run_worker.py"
pkill -f "run_client.py"
```

## Full Status
See `CLIENT_WORKER_STATUS.md` for complete details, pending tasks, and architecture overview.
