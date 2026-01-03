# Client/Worker Architecture - Status & TODO

**Last Updated:** 2025-12-29 (Evening - Template Migration & Browse Module Complete)
**Status:** ✅ All systems operational! Template architecture migrated, browse module fully independent, direct linking implemented.

---

## Architecture Overview

Successfully split the monolithic server into:
- **Client (port 8000)**: Lightweight UI server (no PyTorch/GPU dependencies)
- **Worker (port 8001)**: Headless GPU inference server

**Key Features:**
- Non-blocking job submission and progress tracking
- Server-side FIFO job queue (one job at a time per worker)
- Automatic result fetching from worker to client
- Directory separation: `outputs/worker/` (temp) vs `outputs/run/` (permanent)
- JavaScript progress polling (2-second intervals)
- Worker selection (local/remote) via dropdown

---

## ✅ Completed Tasks

### Core Infrastructure
1. ✅ Fix config.py PyTorch dependency (lazy import)
2. ✅ Create worker server structure (worker/app.py, worker/jobs.py, worker/state.py)
3. ✅ Create worker entrypoint (scripts/run_worker.py)
4. ✅ Implement worker job submission endpoint (POST /jobs)
5. ✅ Implement worker status endpoint (GET /jobs/{job_id}/status)
6. ✅ Add PyTorch callback integration for progress updates
7. ✅ Implement worker file serving (GET /jobs/{job_id}/files)
8. ✅ Test local worker with direct HTTP calls

### Client Implementation
9. ✅ Create client server structure (client/app.py, client/worker_client.py)
10. ✅ Create client entrypoint (scripts/run_client.py)
11. ✅ Add worker configuration support (client/config.py)
12. ✅ Implement client job submission (POST to worker + local tracking)
13. ✅ Implement client result fetching and extraction
14. ✅ Test full local workflow (client + worker on same machine)

### UI Implementation
15. ✅ Create UI forms with worker selection
16. ✅ Add JavaScript progress polling to UI
17. ✅ Image generation form with live progress
18. ✅ Video generation form with image upload
19. ✅ Fix client home page CSS issue

### Lazy Model Loading (✅ TESTED & WORKING)
20. ✅ Implement lazy model loading in worker
    - Models load on first request (not at startup)
    - Automatic model swapping (image ↔ video)
    - Uses existing `ensure_image_generator()` and `ensure_video_generator()` from server.state
    - **Status:** ✅ Tested successfully after reboot (image → video swap works perfectly)

### Utilities
21. ✅ Create restart scripts (restart-worker.sh, restart-client.sh)
22. ✅ Fix worker shutdown NameError bug (worker/app.py)
23. ✅ Improve restart scripts with process checking and force-kill fallback
24. ✅ Create deploy-worker.sh script for remote GPU deployment

### Job Queue System (✅ TESTED & WORKING)
25. ✅ Implement server-side FIFO job queue (worker/queue.py)
    - Jobs automatically queue when submitted
    - Background processor executes one job at a time
    - "queued" status added to job lifecycle
    - Health endpoint reports queue size and running job
    - **Status:** ✅ Tested successfully on 2025-12-29 (sequential processing confirmed)

---

## ✅ UI Improvements (Completed 2025-12-28 Evening)

### 1. Browse Integration
- ✅ "Use as Template" button → navigates to `/generate/image` with all params pre-filled
- ✅ "Generate Video" button → navigates to `/generate/video?source=runid`
- ✅ Buttons work correctly with client URLs (port 8000 detection)

### 2. All Tunable Parameters Exposed
**Image Form:**
- ✅ Aspect ratio selector (landscape/portrait/square)
- ✅ Height/width fields (editable, updated by aspect ratio)
- ✅ Steps field (required, no placeholders)
- ✅ Guidance scale field (required, no placeholders)
- ✅ Seed field
- ✅ Query param support for "use as template" flow

**Video Form:**
- ✅ Source run ID input (alternative to file upload)
- ✅ Image preview from run ID (loads via browse API)
- ✅ Duration (seconds) field
- ✅ FPS field
- ✅ Steps field
- ✅ Guidance scale field
- ✅ Seed field
- ✅ Query param support for "generate video" flow

### 3. Preset System Refactored
- ✅ Presets are now UI-only (not sent to worker)
- ✅ Preset buttons populate form fields with specific values
- ✅ User sees exactly what will be sent (no hidden logic)
- ✅ All parameters required with visible defaults
- ✅ Worker receives only raw parameters (height, width, steps, guidance, fps, duration)
- ✅ Removed `preset` and `aspect_ratio` from worker API

**Image Presets:** Draft (480p, 4 steps), Fast (480p, 6 steps), Balanced (720p, 8 steps), Quality (720p, 12 steps)
**Video Presets:** Draft (3s, 12fps, 15 steps), Final (5s, 16fps, 30 steps), HQ (7s, 24fps, 50 steps)

---

## ✅ Recent Completions (2025-12-29)

### Script Improvements
28. ✅ **Switch from nohup to screen for better process management** - COMPLETED
   - ✅ Updated restart-worker.sh to use screen sessions
   - ✅ Updated restart-client.sh to use screen sessions
   - ✅ Updated deploy-worker.sh to use screen and fix `screen -r` instructions
   - ✅ Can now attach to running processes with `screen -r client` or `screen -r worker`

### Client UI Enhancements
29. ✅ **Job queue visibility UI** - COMPLETED
   - ✅ Added `/jobs` page showing all submitted jobs across all workers
   - ✅ Displays job status, progress bars, and worker assignment
   - ✅ Gracefully handles offline workers (10s timeout with clear error messages)
   - ✅ Auto-refresh every 5 seconds for live monitoring
   - ✅ "View" links for completed jobs with direct browse linking

30. ✅ **Compact form layouts (match old server UI)** - COMPLETED
   - ✅ Image form: Two-column layout (form left, output right)
   - ✅ Video form: Two-column layout (source left, parameters right)
   - ✅ Responsive design (stacks on mobile <768px)
   - ✅ All functionality preserved with improved density

31. ✅ **Template Migration & Browse Module Independence** - COMPLETED
   - ✅ Extracted all HTML to templates/ directory
   - ✅ Extracted all JavaScript to static/js/ directory
   - ✅ Migrated browse module from server to client (~1,165 lines)
   - ✅ Implemented direct browse linking with URL parameters

---

## 🚧 Future Enhancements

### Potential Improvements
- [ ] Add batch job submission
- [ ] Implement job cancellation from UI
- [ ] Add worker health monitoring dashboard
- [ ] Persist job history to SQLite
- [ ] Add API key authentication for remote workers
- [ ] Implement result caching/CDN for faster preview loads

---

## ⏸️ Completed Deployment

### Deployment (✅ TESTED & WORKING)
26. ✅ **Create deploy-worker.sh script**
   - Syncs code to Lambda Labs
   - Sets up Python environment with uv
   - Starts worker with proper process checking
   - Provides SSH tunnel instructions

27. ✅ **Test remote worker deployment**
   - Deploy to Lambda Labs GH200 (successful)
   - SSH tunnel (localhost:8002) working
   - Client successfully submits to remote worker
   - Model loading and generation on remote GPU verified
   - Job queuing behavior confirmed in logs

---

## ✅ Previous Issue: GPU Hang (RESOLVED)

**Problem:** During lazy loading testing, multiple worker processes got stuck in 'D' (uninterruptible sleep) state.

**Root Cause:** Likely ROCm issue + multiple worker instances starting before old ones died

**Resolution:**
1. ✅ Rebooted to clear GPU hang
2. ✅ Tested lazy loading successfully (image job → video job with model swap)
3. ✅ Fixed worker shutdown bug (NameError on cleanup)
4. ✅ Improved restart scripts with process verification before starting new instances

**Test Results (2025-12-28):**
- Image model: Loaded in 8.78s on first request
- Image generation: Completed in 8.01s (4 steps, draft preset)
- Model swap: Image → Video succeeded, GPU memory freed (95.3 GiB / 96.0 GiB)
- Video model: Loaded in 6s
- Video generation: Completed in 330.06s (15 steps, draft preset, 3s @ 12fps)
- No hangs or errors during execution

---

## File Structure

### New Files Created
```
src/mydiffuser/
├── client/
│   ├── __init__.py
│   ├── app.py              # Client FastAPI app (no PyTorch)
│   ├── config.py           # Worker endpoint configuration
│   ├── jobs.py             # Client-side job tracking
│   ├── routes.py           # API routes (job submission, status)
│   ├── ui.py               # UI routes (renders templates)
│   ├── worker_client.py    # HTTP client for talking to workers
│   ├── browse_routes.py    # Browse API routes (migrated from server)
│   ├── browse_ui.py        # Browse UI route (renders template)
│   ├── templates/          # Jinja2 templates (NEW)
│   │   ├── base.html       # Base template with shared styles
│   │   ├── home.html       # Home page
│   │   ├── browse.html     # Browse UI (migrated from server)
│   │   ├── generate_image.html  # Image generation form
│   │   ├── generate_video.html  # Video generation form
│   │   └── jobs.html       # Job queue page
│   └── static/             # Static assets (NEW)
│       └── js/
│           ├── browse.js   # Browse logic (migrated from server)
│           ├── image_form.js  # Image form logic
│           ├── video_form.js  # Video form logic
│           └── jobs.js     # Job queue logic
├── worker/
│   ├── __init__.py
│   ├── app.py              # Worker FastAPI app (with PyTorch)
│   ├── jobs.py             # Job execution logic
│   ├── queue.py            # Job queue management (FIFO)
│   └── state.py            # Job progress tracking
└── config.py               # Modified for lazy PyTorch import

scripts/
├── run_client.py           # Client entrypoint
├── run_worker.py           # Worker entrypoint
├── restart-client.sh       # Restart client utility
├── restart-worker.sh       # Restart worker utility
└── deploy-worker.sh        # Deploy worker to remote GPU
```

### Modified Files
```
src/mydiffuser/
├── config.py               # Lazy PyTorch import, WORKER_RUNS_DIR
├── server/state.py         # Imports from shutdown module
├── shutdown.py             # New module (broke circular imports)
├── generators/image.py     # Added callback_on_step_end parameter
├── generators/video/wan.py # Added callback_on_step_end parameter
├── utils/paths.py          # Added worker_run_dir()
├── worker/app.py           # Added queue integration, health endpoint shows queue status
└── worker/state.py         # Added "queued" status to JobProgress

pyproject.toml              # Added httpx, python-multipart
```

---

## Usage After Reboot

### Option 1: Old Server (Recommended for now)
```bash
python scripts/run_server.py
# Access at http://localhost:8000
```

### Option 2: Client + Worker (New Architecture)
```bash
# Terminal 1: Worker
bash scripts/restart-worker.sh
# or: python scripts/run_worker.py --port 8001

# Terminal 2: Client
bash scripts/restart-client.sh
# or: python scripts/run_client.py --port 8000

# Access client at http://localhost:8000
```

### Testing Lazy Loading
```bash
# After reboot, test carefully:
1. Start worker: bash scripts/restart-worker.sh
2. Check logs: tail -f /tmp/worker.log
3. Wait for "Worker startup complete" (should be instant now)
4. Submit ONE image job via client UI
5. Watch logs for lazy model load
6. Verify job completes
7. Submit ONE video job
8. Watch for model swap in logs
9. Verify both work without hanging
```

### Testing Job Queue
```bash
# After worker is running successfully:
1. Check worker health: curl http://localhost:8001/health | python -m json.tool
   - Should show "queued_jobs": 0, "running_job": null

2. Submit two image jobs quickly via client UI (within 1 second)

3. Check status immediately:
   curl http://localhost:8001/health | python -m json.tool
   - Should show "queued_jobs": 1 (one queued, one running)
   - Should show "running_job": "<job-id>"

4. Watch worker logs for queue behavior:
   tail -f /tmp/worker.log
   - Should see: "[job1] Starting image job (queue size: 1)"
   - After job1 completes: "[job2] Starting image job (queue size: 0)"

5. Verify both jobs complete successfully via client UI browse page
```

---

## Key Endpoints

### Client (port 8000)
- `GET /` - Home page with navigation
- `GET /generate/image` - Image generation form
- `GET /generate/video` - Video generation form
- `GET /browse` - Browse all results
- `POST /api/jobs/image` - Submit image job
- `POST /api/jobs/video` - Submit video job
- `GET /api/jobs` - List all jobs
- `GET /api/jobs/{id}` - Get job status
- `GET /api/workers` - List configured workers

### Worker (port 8001)
- `POST /jobs` - Accept new job (queued automatically)
- `GET /jobs/{id}/status` - Job status with progress
- `GET /jobs/{id}/files` - Download results (tar.gz)
- `DELETE /jobs/{id}` - Cleanup job
- `GET /health` - Worker health, GPU info, queue status (queued_jobs, running_job)
- `GET /gpu/test` - GPU compute validation

---

## Configuration

### Worker Endpoints (client/config.py)
```python
WORKERS = {
    "local": {
        "endpoint": "http://localhost:8001",
        "capabilities": ["image", "video"],
    },
    "remote": {
        "endpoint": "http://localhost:8002",  # Via SSH tunnel
        "capabilities": ["image", "video"],
    },
}
```

### Environment Variables
```bash
# Override worker endpoints
export MYDIFFUSER_LOCAL_WORKER="http://localhost:8001"
export MYDIFFUSER_REMOTE_WORKER="http://localhost:8002"

# Enable/disable lazy loading (default: enabled)
export MYDIFFUSER_LAZY=1
```

---

## Known Issues

1. **ROCm GPU Hang (Ongoing)**
   - ROCm driver occasionally gets into D state (uninterruptible sleep) during worker startup
   - Affects both worker processes and ROCm tools (rocminfo)
   - Resolution: System reboot required to clear GPU state
   - Mitigation: Restart scripts now verify old process death before starting new instances

---

## Notes for Continuation

1. **Lazy Loading Implementation:**
   - Uses existing `server.state.ensure_image_generator()`
   - Uses existing `server.state.ensure_video_generator()`
   - Config flag: `LAZY_LOADING = True` (default)
   - Models swap automatically via `_unload_all_models()`

2. **User Preferences:**
   - Prefers lazy loading due to VRAM constraints (70-80GB for 14B model)
   - Can't have multiple models loaded simultaneously
   - Has been extensively tuning parameters in old UI
   - Wants full parameter control, not just presets

3. **Testing Strategy:**
   - Test with single worker first
   - Monitor for concurrent load issues
   - Check ROCm-specific problems
   - May need startup synchronization lock

---

## References

- Original plan: `~/.claude/plans/cheerful-dancing-cherny.md`
- Worker logs: `/tmp/worker.log`
- Client logs: `/tmp/client.log`
- Old server: `scripts/run_server.py` (still works)

---

## Latest Session Notes

### 2025-12-29 Morning - Full System Validation ✅
**Testing Complete:**
- System rebooted and all services started successfully
- Image generation jobs: Working
- Video generation jobs: Working
- Remote worker deployment: Successful (Lambda Labs GH200)
- Job queue behavior: Confirmed sequential processing in logs
- Lazy model loading: Continues to work (image ↔ video swaps)

**Next Priorities:**
1. ~~Switch restart scripts to use `screen` instead of `nohup` for better observability~~ ✅ COMPLETED
2. ~~Add job queue UI to client for visibility across workers~~ ✅ COMPLETED
3. ~~Compact form layouts to match old server UI density~~ ✅ COMPLETED

### 2025-12-29 Late Evening - Inference Module Refactor 🚧 IN PROGRESS

**Goal:** Move shared model management from `server.state` to `inference.state` to enable server package deprecation.

**Status:** Code changes complete, testing interrupted by system load.

**Changes Made:**
1. ✅ Created new `inference` package:
   - `src/mydiffuser/inference/__init__.py` - Package exports
   - `src/mydiffuser/inference/state.py` - Copied from server.state with updated docstring

2. ✅ Updated all imports:
   - `worker/app.py` - All 4 imports updated (ensure_image_generator, ensure_video_generator, get_active_model, _unload_all_models)
   - `server/app.py` - Updated to use inference.state
   - `server/routes/health.py` - Updated to use inference.state
   - `server/routes/image.py` - Updated (via sed)
   - `server/routes/video.py` - Updated (via sed)

**What to Test After Reboot:**
```bash
# 1. Start worker
bash scripts/restart-worker.sh

# 2. Check logs for inference.state (not server.state)
tail -f /tmp/worker.log | grep -E "inference\.|Loading"

# 3. Test image generation via client UI
# 4. Test video generation via client UI
# 5. Verify model swapping works (image → video)

# Expected: Everything works exactly as before, but logs show "mydiffuser.inference.state" instead of "mydiffuser.server.state"
```

**Files Changed:**
- NEW: `src/mydiffuser/inference/__init__.py`
- NEW: `src/mydiffuser/inference/state.py` (copied from server.state)
- MODIFIED: `src/mydiffuser/worker/app.py` (4 import statements)
- MODIFIED: `src/mydiffuser/server/app.py` (import statements)
- MODIFIED: `src/mydiffuser/server/routes/health.py` (import statement)
- MODIFIED: `src/mydiffuser/server/routes/image.py` (imports)
- MODIFIED: `src/mydiffuser/server/routes/video.py` (imports)

**Next Steps After Testing:**
- If working: Can safely deprecate/remove server package
- Worker and client will be fully independent packages
- Server package only needed for legacy compatibility

**Current Dependencies:**
- Client: ✅ Zero server dependencies
- Worker: ✅ Zero server dependencies (now uses inference.state)
- Legacy server: Still uses inference.state (but will be deprecated)

### 2025-12-29 Evening - Template Migration & Browse Module Independence ✅

**Major Architectural Improvements:**

1. **Template System Migration Complete**
   - ✅ Fixed duplicate inline JavaScript in image/video templates (was causing cache issues)
   - ✅ All HTML now properly extracted to `templates/` directory
   - ✅ All JavaScript properly extracted to `static/js/` directory
   - ✅ Can now edit UI without server restarts (just refresh browser)
   - ✅ Image inline display working correctly
   - ✅ Video preview moved to left panel (better UX)

2. **Browse Module Fully Migrated (Server → Client)**
   - ✅ Created `client/browse_routes.py` - API endpoints (354 lines)
   - ✅ Created `client/browse_ui.py` - Template rendering (17 lines, slim!)
   - ✅ Extracted `templates/browse.html` - UI structure (531 lines)
   - ✅ Extracted `static/js/browse.js` - Browse logic (263 lines)
   - ✅ **Total migration: ~1,165 lines properly structured**
   - ✅ Client no longer depends on server browse package
   - ✅ Browse UI ready for future enhancements without server code coupling

3. **Direct Browse Linking Implemented**
   - ✅ Browse page accepts `?run=<run_id>` URL parameter
   - ✅ Automatically opens modal for specified run on page load
   - ✅ URL cleaned up after opening (better UX)
   - ✅ Updated all "View in Browse" links to use direct linking:
     - Image generation complete → `/browse?run={run_id}`
     - Video generation complete → `/browse?run={run_id}`
     - Jobs page "View" links → `/browse?run={run_id}`
   - ✅ No more "find your run" navigation - one click to details!

4. **Video Form Enhancements**
   - ✅ Fixed uploaded image submission (FormData with explicit filename for FastAPI)
   - ✅ Video preview now appears in left panel under source image
   - ✅ Added "Generate Video" link from image generation results
   - ✅ All generation → browse → video flows working seamlessly

5. **Process Management Improvements**
   - ✅ Switched restart scripts to use `screen` sessions (better observability)
   - ✅ Can now attach to running processes: `screen -r client` or `screen -r worker`
   - ✅ Fixed SSH instructions in deploy-worker.sh to use `ssh -t` for TTY allocation
   - ✅ Job queue UI page with auto-refresh showing all workers

**File Structure Changes:**
```
src/mydiffuser/client/
├── browse_routes.py          # NEW: Browse API routes (migrated from server)
├── browse_ui.py               # NEW: Browse UI rendering (slim!)
├── templates/
│   ├── base.html              # Shared template base
│   ├── home.html
│   ├── browse.html            # NEW: Browse UI (extracted)
│   ├── generate_image.html
│   ├── generate_video.html
│   └── jobs.html
└── static/
    └── js/
        ├── browse.js          # NEW: Browse logic (extracted)
        ├── image_form.js
        ├── video_form.js
        └── jobs.js
```

**Testing Results:**
- ✅ All template pages render correctly
- ✅ All JavaScript loads without errors
- ✅ Image generation with inline preview working
- ✅ Video generation with left-panel preview working
- ✅ Uploaded image video generation working (FormData fix)
- ✅ Direct browse linking working from all entry points
- ✅ Browse module fully independent from server package

**Benefits Achieved:**
1. **Better Developer Experience**: Edit HTML/CSS/JS without server restarts
2. **Better Code Organization**: Clear separation of concerns (templates, logic, routes)
3. **Better Maintainability**: Standard FastAPI + Jinja2 patterns
4. **Better User Experience**: Direct linking eliminates navigation steps
5. **Architectural Independence**: Client can evolve without server dependencies

### 2025-12-28 Late Evening - Job Queue Implementation
**Job Queue Implementation Complete:**
- Created `worker/queue.py` with JobQueue class using asyncio.Queue
- Modified `worker/app.py` to integrate queue (import, startup, job submission)
- Updated `worker/state.py` to add "queued" status
- Health endpoint now reports `queued_jobs` and `running_job`
- Tested successfully after reboot (see above)

---

## Latest Session: 2025-12-30

### 1. Video Resolution Implementation ✅ COMPLETED

**Problem:** WAN2.2 I2V pipeline was defaulting to 480p output because `size` parameter was missing from pipeline call.

**Solution:** Added configurable video output resolution (480p or 720p) with automatic aspect ratio detection.

**Changes:**
- ✅ Added `resolution` field to `GenerateVideoRequest` model (requests.py)
- ✅ Updated video presets with resolution defaults (presets.py):
  - draft: 480p (fast)
  - final/hq: 720p (quality)
- ✅ Added `_calculate_output_size()` helper function (wan.py)
- ✅ Updated generator to accept resolution parameter and pass size to pipeline (wan.py)
- ✅ Updated API route to pass resolution to generator and save in metadata (video.py)
- ✅ Added resolution selector dropdown to video generation UI (generate_video.html)
- ✅ Updated JavaScript to handle resolution in presets (video_form.js)

**Resolution Mapping:**
| Resolution | Landscape | Portrait | Use Case |
|------------|-----------|----------|----------|
| 480p | 832×480 | 480×832 | Fast iteration |
| 720p | 1280×704 | 704×1280 | Production quality (WAN2.2 native) |

**Documentation:** [VIDEO_RESOLUTION_CHANGES.md](VIDEO_RESOLUTION_CHANGES.md)

**Files Changed (7 total):**
- `src/mydiffuser/models/requests.py` - Added resolution field
- `src/mydiffuser/utils/presets.py` - Resolution in presets + apply logic
- `src/mydiffuser/generators/video/wan.py` - Size calculation + pipeline parameter
- `src/mydiffuser/server/routes/video.py` - Pass resolution + metadata
- `src/mydiffuser/client/templates/generate_video.html` - UI selector
- `src/mydiffuser/client/static/js/video_form.js` - Preset handling

### 2. Tag Filtering Improvements ✅ COMPLETED

**Changes:**
- ✅ Changed tag filtering from "exclude" to "include" logic (OR logic for multiple tags)
- ✅ Added NSFW toggle: OFF = exclude nsfw, ON = include nsfw (additive, not override)
- ✅ Updated database queries in `client/database.py`
- ✅ Updated browse API in `client/browse_routes.py`
- ✅ Updated browse UI JavaScript in `static/js/browse.js`
- ✅ Added NSFW toggle styling in `templates/browse.html`

**Behavior:**
- No tags selected + NSFW OFF: Show all runs except nsfw
- Tags selected + NSFW OFF: Show only runs with selected tags, excluding nsfw
- Tags selected + NSFW ON: Show runs with selected tags, including nsfw

### 3. Navigation Updates ✅ COMPLETED

**Changes:**
- ✅ Made `/` route directly to generate_image (no separate home page)
- ✅ Added "Health Check" link to all navigation menus
- ✅ Updated navigation across all pages (generate_image, generate_video, browse, jobs)

### 4. Video Model Selection ✅ COMPLETED

**Status:** ✅ COMPLETED - 2025-12-31

**Goal:** Allow users to select between 5B and 14B video models with worker capability reporting

**Implementation:**
1. ✅ Worker advertises available models via `/capabilities` endpoint
2. ✅ Auto-exclude 14B on ROCm (insufficient VRAM)
3. ✅ Client queries worker capabilities and populates model dropdown
4. ✅ Worker validates requested model before execution
5. ✅ Dynamic model loading (5B ↔ 14B swapping)
