# GPU Hang Recovery Guide

## Symptom
Worker startup hangs at "Waiting for GPU memory to stabilize..." or during GPU detection.

## Root Cause
AMD gfx1151 GPU can enter D-state (uninterruptible sleep) due to:
- ROCm driver issues with conv3d operations
- MIOpen kernel compilation failures
- GPU memory not properly released between worker restarts
- **Cancelled jobs**: Interrupting diffusion inference mid-generation can leave GPU kernels in incomplete state
- GPU detection code calling torch.cuda functions when GPU is already hung

## Immediate Recovery

### 1. Check if GPU is hung
```bash
timeout 5 rocminfo
```

If this hangs (times out), GPU is in D-state.

### 2. Check for D-state processes
```bash
ps aux | awk '$8 ~ /D/ {print}'
```

Look for Python processes or kworker threads stuck in D-state.

### 3. Reboot (only solution for D-state)
```bash
sudo reboot
```

⚠️ **There is NO way to recover from D-state without rebooting** on this GPU/driver combination.

## Prevention

### Safety Features (As of 2026-01-03)

**1. Graceful Shutdown Endpoint** ⭐ NEW
- `/shutdown` API endpoint cancels jobs and unloads models before process exit
- `restart-worker.sh` calls this endpoint BEFORE killing the process
- Reduces GPU hangs by ensuring clean GPU resource cleanup
- Falls back to SIGTERM → SIGKILL if API call fails
- Includes explicit GPU synchronization and 2s delay for ROCm driver cleanup

**1a. Job Cancellation GPU Synchronization** ⭐ NEW (2026-01-03)
- When job is cancelled mid-generation, explicitly calls `torch.cuda.synchronize()`
- Ensures all GPU kernels complete before unloading models
- Prevents GPU from entering bad state due to incomplete operations
- Applied to both image and video generation cancellations

**2. config.py GPU Detection**
- Checks `MYDIFFUSER_SKIP_GPU_DETECT=1` environment variable
- Wrapped in try/except with fallback to "Unknown GPU"
- Only runs when worker actually starts (not in client)

**3. restart-worker.sh Improvements**
- Step 1: Call `/shutdown` endpoint to gracefully cleanup (20s timeout)
- Step 2: Send SIGTERM if process still running
- Step 3: Force kill with SIGKILL if needed (last resort)
- Step 4: Check GPU health with `rocminfo` before restarting
- Re-checks GPU health AFTER memory stabilization wait
- Exits immediately if GPU is unresponsive

**4. Known Workarounds**
- Video VAE decode runs on CPU (not GPU) to avoid conv3d crashes
- See `vae-issues.md` for details

## If Worker Keeps Hanging on Startup

### Option 1: Skip GPU Detection Temporarily
```bash
# Start worker without GPU detection
MYDIFFUSER_SKIP_GPU_DETECT=1 python scripts/run_worker.py --port 8001
```

This will:
- Set GPU_NAME = "Unknown GPU"
- Set GPU_ARCH = "unknown"
- Still allows inference to work
- Metadata won't have accurate GPU info

### Option 2: Wait Longer
Sometimes the GPU takes >15 seconds to fully release memory. Try:
```bash
# Manual restart with longer wait
pkill -9 -f run_worker
sleep 15
timeout 5 rocminfo  # Verify GPU is responsive
python scripts/run_worker.py --port 8001
```

### Option 3: Check for Memory Leaks
```bash
# Before stopping worker
rocm-smi --showmeminfo

# Stop worker
pkill -9 -f run_worker

# Wait and check again
sleep 10
rocm-smi --showmeminfo

# Memory should be cleared
```

## Long-term Solutions

### 1. ROCm Driver Updates
- Currently on ROCm 7.0 nightly
- Future stable releases may improve gfx1151 support
- Watch for kernel updates that improve D-state handling

### 2. Kernel Parameter Tuning
May help prevent D-state:
```bash
# Add to /etc/default/grub
GRUB_CMDLINE_LINUX="... amdgpu.gpu_recovery=1"
```

### 3. Lazy Model Loading
Use `MYDIFFUSER_LAZY=1` to reduce memory pressure:
```bash
MYDIFFUSER_LAZY=1 MYDIFFUSER_VIDEO=1 python scripts/run_worker.py --port 8001
```

## Testing Graceful Shutdown

### Manual Shutdown Test
```bash
# With worker running, call shutdown endpoint
curl -X POST http://localhost:8001/shutdown | python3 -m json.tool

# Expected response:
# {
#   "status": "ok",
#   "message": "Worker shutting down gracefully",
#   "cancelled_job": null,  # or job_id if one was running
#   "models_unloaded": true,
#   "gpu_memory": {
#     "free_gib": 95.5,
#     "total_gib": 96.0
#   }
# }

# Worker should remain responsive briefly, then exit
```

### Automated Restart Test
```bash
# Use the updated restart script
bash scripts/restart-worker.sh

# Look for these messages:
# "Requesting graceful shutdown via API..."
# "✓ Graceful shutdown completed"
# "GPU responsive, starting worker..."
```

## Verified Test Cases

### ✅ Video Generation Cancellation (2026-01-03)

**Test:** Cancelled Wan 5B video job mid-generation at step 2/30

**Results:**
- GPU synchronization completed successfully after cancellation
- Log confirmation: `Synchronizing GPU after cancellation... GPU synchronized successfully`
- Models unloaded cleanly (95.1 GiB → 95.8 GiB free)
- Worker restarted without hang
- No D-state processes detected
- Full GPU memory recovery verified

**Key logs:**
```
INFO:mydiffuser.worker.jobs:[job_id] Cancellation detected at step 2/30
INFO:mydiffuser.worker.jobs:[job_id] Synchronizing GPU after cancellation...
INFO:mydiffuser.worker.jobs:[job_id] GPU synchronized successfully
INFO:mydiffuser.inference.state:GPU memory after cleanup: 95.1 GiB free / 96.0 GiB total
INFO:mydiffuser.worker.app:All models unloaded successfully
```

**Conclusion:** The `torch.cuda.synchronize()` fix successfully prevents GPU hangs during job cancellation. The GPU remained responsive and worker restarted cleanly without requiring a reboot.

## Monitoring

### Check GPU Health
```bash
# Quick check (should return in <1 second)
timeout 5 rocminfo > /dev/null && echo "OK" || echo "HUNG"

# Monitor memory
watch -n 1 rocm-smi --showmeminfo

# Check for D-state processes
watch -n 2 "ps aux | awk '\$8 ~ /D/ {print}'"
```

### Worker Logs
```bash
# Check for GPU detection failures
grep -i "gpu.*fail" /tmp/worker.log

# Check for hung operations
tail -f /tmp/worker.log
```

## When to Reboot

Reboot immediately if:
- `rocminfo` hangs (even with timeout)
- Processes stuck in D-state that won't die with kill -9
- GPU memory not clearing after killing worker
- Multiple consecutive worker startup failures

**Do NOT waste time trying other solutions** - D-state requires reboot on this hardware.

## Related Documents
- `vae-issues.md` - Video VAE conv3d crashes and workarounds
- `AGENTS.md` - Project context including ROCm issues
- `scripts/restart-worker.sh` - Improved restart script with health checks
