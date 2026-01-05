If you have not already, read AGENTS.md
run "bd list -s in_progress --json " to find any in progress tasks.
run "bd ready --json" to find all ready tasks

## Current Session Context (Updated: 2026-01-04 19:45)

**Just completed:** Moved logs from /tmp to outputs/logs (mydiffuser-9m8)
- ✅ All scripts updated (restart-worker, restart-client, deploy-worker)
- ✅ All documentation updated
- ✅ Logs now persist across reboots in outputs/logs/
- Commit: 871ee8c

**System Status:**
- ROCm 7.1: torch 2.11.0.dev20260103+rocm7.1, HIP 7.1.52802
- GPU: gfx1151 (AMD Ryzen AI Max+ 395)
- Config: VAE_DEVICE = "cuda" (testing mode - may be unstable)
- Client running on port 8000
- Worker: Not currently running (restart script hung on GPU check)

**ROCm 7.11 Testing Results:**
- Upgraded to gfx1151-specific nightlies - First run worked, then hung on restart
- Reverted to stable ROCm 7.1 (install-rocm.sh now correct)

**In Progress Issues:**
- mydiffuser-8se: GPU VAE decode stability testing (needs video generation test)

**Next Quick Wins (Priority 2):**
- mydiffuser-oig: Check why we call HuggingFace on each model startup
- mydiffuser-118: Consolidate on run_id (job_id vs run_id confusion)

**Known issues:**
- bd database repo mismatch warning (use --no-daemon to bypass)
- GPU health checks can hang (ROCm driver state)