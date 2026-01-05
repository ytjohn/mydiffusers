If you have not already, read AGENTS.md
run "bd list -s in_progress --json " to find any in progress tasks.
run "bd ready --json" to find all ready tasks

## Current Session Context (Updated: 2026-01-04 20:15)

**Session Summary - Major Accomplishments:**

### 1. Log Persistence (mydiffuser-9m8) ✅ CLOSED
- Moved all logs from /tmp to outputs/logs/ for persistence across reboots
- Updated all scripts (restart-worker, restart-client, deploy-worker)
- Updated documentation (QUICK_START, GPU_HANG_RECOVERY, CLIENT_WORKER_STATUS)
- Commit: 871ee8c

### 2. Shutdown API Documentation ✅
- Updated docs to use `/shutdown` API instead of pkill
- Emphasized graceful shutdown over force kill
- Updated QUICK_START and GPU_HANG_RECOVERY guides
- Commit: 7731012

### 3. Modular Start/Stop Scripts ✅
- Created stop-worker.sh and start-worker.sh (separate from restart)
- Created stop-client.sh and start-client.sh
- restart-*.sh now just calls stop + start
- Better composability and single responsibility
- Commit: 523e0c9

### 4. Video Generation Disabled by Default ✅
- VIDEO_ENABLED now defaults to 0 (was 1)
- Worker rejects video jobs when disabled with clear error
- UI hides video nav link and "Generate Video" button when disabled
- Browse page still shows existing videos (view only, not create)
- Documented MYDIFFUSER_VIDEO=1 flag in README
- Commits: b2b5c55, 8a56b81

**System Status:**
- ROCm 7.1: torch 2.11.0.dev20260103+rocm7.1, HIP 7.1.52802
- GPU: gfx1151 (AMD Ryzen AI Max+ 395)
- VIDEO_ENABLED: 0 (disabled by default, stable image-only mode)
- VAE_DEVICE: "cuda" (in config, but worker not running)
- Services: Not running (GPU health check issues)

**ROCm Journey:**
- ROCm 6.2 → 7.1 ✅ (stable)
- ROCm 7.11 gfx1151 nightlies ❌ (hung on restart, reverted)
- Video on GPU ❌ (unstable, disabled by default)
- Image generation ✅ (works great)

**In Progress Issues:**
- mydiffuser-8se: GPU VAE decode stability (in_progress)
  - Video generation disabled by default due to this issue
  - Can enable with MYDIFFUSER_VIDEO=1 for testing or CUDA workers

**Next Quick Wins (Priority 2):**
- mydiffuser-oig: Check why we call HuggingFace on each model startup
- mydiffuser-118: Consolidate on run_id (job_id vs run_id confusion)

**Known Issues:**
- bd database repo mismatch warning (use --no-daemon to bypass)
- GPU health checks can hang (ROCm driver state)
- Video generation unstable on gfx1151/ROCm (disabled by default)

**Scripts Ready to Use:**
```bash
# Start services
bash scripts/start-worker.sh
bash scripts/start-client.sh

# Stop services
bash scripts/stop-worker.sh [--force]
bash scripts/stop-client.sh [--force]

# Restart services
bash scripts/restart-worker.sh [--force]
bash scripts/restart-client.sh [--force]

# Enable video (if needed)
export MYDIFFUSER_VIDEO=1
bash scripts/start-worker.sh
```