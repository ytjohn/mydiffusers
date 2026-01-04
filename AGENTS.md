# MyDiffuser - Project Context for AI Agents

> **Note:** [CLAUDE.md](./CLAUDE.md) points here for the comprehensive agent guide.

## Project Overview

MyDiffuser is a FastAPI-based image and video generation server optimized for **AMD ROCm** on the **Framework Desktop with AMD Max+ 395** (128GB unified memory). It provides a web UI and REST API for AI-powered content generation.

## Issue Tracking

We use bd (beads) for issue tracking instead of Markdown TODOs or external tools.

### Quick Reference

```bash
# Find ready work (no blockers)
bd ready --json

# Find ready work including future deferred issues
bd ready --include-deferred --json

# Create new issue
bd create "Issue title" -t bug|feature|task -p 0-4 -d "Description" --json

# Create issue with due date and defer (GH#820)
bd create "Task" --due=+6h              # Due in 6 hours
bd create "Task" --defer=tomorrow       # Hidden from bd ready until tomorrow
bd create "Task" --due="next monday" --defer=+1h  # Both

# Update issue status
bd update <id> --status in_progress --json

# Update issue with due/defer dates
bd update <id> --due=+2d                # Set due date
bd update <id> --defer=""               # Clear defer (show immediately)

# Link discovered work
bd dep add <discovered-id> <parent-id> --type discovered-from

# Complete work
bd close <id> --reason "Done" --json

# Show dependency tree
bd dep tree <id>

# Get issue details
bd show <id> --json

# Query issues by time-based scheduling (GH#820)
bd list --deferred              # Show issues with defer_until set
bd list --defer-before=tomorrow # Deferred before tomorrow
bd list --defer-after=+1w       # Deferred after one week from now
bd list --due-before=+2d        # Due within 2 days
bd list --due-after="next monday" # Due after next Monday
bd list --overdue               # Due date in past (not closed)
```

### Workflow

1. **Check for ready work**: Run `bd ready` to see what's unblocked
2. **Claim your task**: `bd update <id> --status in_progress`
3. **Work on it**: Implement, test, document
4. **Discover new work**: If you find bugs or TODOs, create issues:
   - `bd create "Found bug in auth" -t bug -p 1 --json`
   - Link it: `bd dep add <new-id> <current-id> --type discovered-from`
5. **Complete**: `bd close <id> --reason "Implemented"`
6. **Export**: Run `bd export -o .beads/issues.jsonl` before committing

### Issue Types

- `bug` - Something broken that needs fixing
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature composed of multiple issues
- `chore` - Maintenance work (dependencies, tooling)

### Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (nice-to-have features, minor bugs)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

### Dependency Types

- `blocks` - Hard dependency (issue X blocks issue Y)
- `related` - Soft relationship (issues are connected)
- `parent-child` - Epic/subtask relationship
- `discovered-from` - Track issues discovered during work

Only `blocks` dependencies affect the ready work queue.

## Development Guidelines

### Code Standards

- **Python version**: 3.10+
- **Linting**: `ruff check src/` (20 acceptable warnings documented below)
- **Type checking**: `mypy src/mydiffuser` (optional, not strict)
- **Testing**: Test manually via web UI or benchmark scripts
- **Documentation**: Update relevant .md files (especially this file for architecture changes)


## Hardware Context

- **GPU**: AMD Max+ 395 (Strix Point APU, gfx1151)
- **Memory**: 128GB unified memory (96GB allocated to GPU via BIOS, 32GB to CPU)
- **OS**: Ubuntu 24.04.3 LTS, kernel 6.14
- **Platform**: ROCm 7.1 (stable production) with PyTorch 2.11.0.dev20260102 nightly wheels
  - Note: ROCm 7.1 (production) and 7.9+/7.11 (preview) are parallel streams, not sequential
  - Using stable ROCm 7.1 + latest PyTorch nightlies is recommended for gfx1151
- **PyTorch**: Configured for `bfloat16` with math-only SDP backend for AMD stability

### ROCm/gfx1151 Known Issues

The gfx1151 GPU architecture is very new and has limited MIOpen kernel support:

**MIOpen Kernel Compilation:**
- **No pre-built kernel database** - MIOpen must JIT-compile kernels on first use
- **First video generation**: 20-30 minute delay during VAE decode (kernel compilation)
- **Subsequent generations**: Kernels cached in `~/.cache/miopen/`, no recompilation needed
- **Cache persistence**: Survives reboots, only cleared on PyTorch/ROCm upgrades

**VAE Decode Performance:**
- **GPU with bf16**: ✅ **WORKS** - 31s decode after initial kernel compilation (4x faster than CPU)
  - Requires proper GPU cleanup between jobs (implemented 2026-01-04)
  - Without cleanup: Progressive slowdown and eventual GPU hang after 4-5 videos
- **CPU with fp32**: ✅ Stable fallback - 127s decode, no compilation delay
  - Use `MYDIFFUSER_VAE_DEVICE=cpu` for maximum stability
- **Recommendation**: Use GPU (default) with proper cleanup for 4x speedup

See `vae-issues.md` for historical debugging and alternative configurations.

### GTT Memory Allocation

The GPU's usable memory is controlled by GTT (Graphics Translation Table), NOT the small dedicated VRAM. Default is often 64GB. Currently configured to 96GB via BIOS.

Check with:
```bash
sudo dmesg | grep -i "GTT memory"
```

To increase (e.g., 96GB for both models):
```bash
# Add kernel parameter: amdgpu.gttsize=98304
# For GRUB: edit /etc/default/grub, run grub-mkconfig
```

## Architecture

MyDiffuser uses a **client/worker architecture** to separate UI concerns from GPU-intensive inference:

```
┌─────────────────────────────────────────────────────────┐
│  CLIENT (port 8000) - GPU-free UI server                │
│  - Web UI for image/video generation, browsing          │
│  - Job submission and progress tracking                 │
│  - Prompt assistant UI                                  │
│  - SQLite database (job persistence, conversations)     │
│  - NO PyTorch/GPU dependencies                          │
└─────────────────────────────────────────────────────────┘
                          │
                          │ HTTP
                          ↓
┌─────────────────────────────────────────────────────────┐
│  WORKER(S) (port 8001+) - GPU inference servers         │
│  - Load and manage diffusion models                     │
│  - Image generation (Z-Image Turbo)                     │
│  - Video generation (Wan2.2 I2V)                        │
│  - Prompt assistant (Qwen2-VL-2B)                       │
│  - Lazy loading and model swapping                      │
└─────────────────────────────────────────────────────────┘
```

**Project Structure:**
```
src/mydiffuser/
├── config.py           # Central config: device, dtype, paths, models
├── utils/
│   ├── paths.py        # Run ID generation, file I/O, thumbnails
│   └── presets.py      # Image and video generation presets
├── models/
│   ├── requests.py     # Pydantic request models
│   └── responses.py    # Pydantic response models
├── inference/          # Worker-side model management
│   ├── state.py        # Global state (generators, locks)
│   ├── assistant.py    # Qwen2-VL prompt assistant
│   ├── image.py        # Z-Image Turbo generator
│   └── video/
│       ├── base.py     # Abstract BaseVideoGenerator
│       └── wan.py      # Wan2.2 I2V generator
├── client/             # Client-side (GPU-free)
│   ├── app.py          # FastAPI app factory
│   ├── database.py     # SQLite CRUD operations
│   ├── worker_client.py # HTTP client for workers
│   ├── routes.py       # Job submission endpoints
│   ├── assist_routes.py # Prompt assistant API
│   ├── admin_routes.py # Admin endpoints (backfill)
│   ├── ui.py           # Image generation web UI
│   ├── assist_ui.py    # Prompt assistant UI
│   ├── browse_ui.py    # Run history browser
│   ├── health_ui.py    # Worker health dashboard
│   ├── templates/      # Jinja2 HTML templates
│   └── static/         # CSS, JavaScript
└── worker/             # Worker-side (GPU inference)
    ├── app.py          # FastAPI app factory
    └── routes/
        ├── health.py   # Health check endpoint
        ├── image.py    # /generate_image
        ├── video.py    # /generate_video
        └── assist.py   # /assist/analyze
```

## Key Models Used

### Image Generation
- **Model**: `Tongyi-MAI/Z-Image-Turbo` (ZImagePipeline)
- **Strengths**: Fast, high-quality, great for iterative prompting
- **Presets**: `draft` (15 steps), `final` (40 steps)

### Z-Image Prompt Formula

Use the 6-part structure for consistent results:
```
Subject + Scene + Composition + Lighting + Style + Constraints
```

Reference: [Z-Image Prompt Formula Guide](https://dev.to/killer_scofield_d2f41df11/z-image-prompt-formula-a-60-second-guide-5202)

**Quick tips:**
- Change only one block at a time when iterating
- Use fixed seeds to reproduce and refine
- Add explicit constraints: "5 fingers", "no extra limbs", "no watermark"
- Character interactions work better with shared objects/activities
- Complex limb poses often fail → pivot to embraces, side-by-side, or hide problem areas

### Video Generation (I2V)
- **Model**: `Wan-AI/Wan2.2-TI2V-5B-Diffusers` (default) or `Wan-AI/Wan2.2-I2V-A14B-Diffusers`
- **Pipeline**: `WanImageToVideoPipeline` from diffusers
- **Requires**: Environment variable `MYDIFFUSER_VIDEO=1` to enable
- **VAE Decode**: Runs on CPU (GPU conv3d is unstable on gfx1151)
- **Presets**: `draft` (15 steps, 3s), `final` (30 steps, 5s), `hq` (50 steps, 7s)

**Performance** (5B model, 15 steps, 37 frames):
- Inference: ~150s (GPU, ~7s/step)
- VAE decode: ~127s (CPU)
- Total: ~4.5 minutes

**Known Limitations:**
- **No native video extension**: Models generate all frames in one pass; can't "continue" a video
- **Longer = slower**: 30s video requires generating all 30s worth of frames upfront
- **Extension workarounds**: Extract last frame → generate new clip → concatenate (has visible seams)
- **Motion prompts**: Describe action/movement, not content (image already has content)
- **gfx1151 VAE issue**: GPU VAE decode crashes; using CPU decode as workaround

### Why This Architecture
- **Z-Image for T2I**: Excellent quality, fast iteration
- **Wan2.2 I2V for animation**: Dedicated I2V model is better than hybrid TI2V
- **Workflow**: Generate images → Browse → Pick best → Animate to video

## Output Structure

All runs (image and video) are stored in a unified structure:

```
outputs/run/{run_id}/
├── image.png       # Generated image (or source image for video)
├── video.mp4       # Generated video (video runs only)
├── thumb.jpg       # 256px thumbnail for browsing
├── meta.json       # Full metadata including type, params, outputs
└── prompt.txt      # Text prompt used
```

Run IDs are timestamp-based: `YYYYMMDD-HHMMSS_{short-uuid}` for chronological sorting.

## API Endpoints

### Client Endpoints (port 8000)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Image generation UI |
| `/generate/video` | GET | Video generation UI |
| `/browse` | GET | Run history browser |
| `/assist` | GET | Prompt assistant UI |
| `/health-dashboard` | GET | Worker health monitoring UI |
| `/health` | GET | Client health check |
| `/api/jobs/image` | POST | Submit image generation job |
| `/api/jobs/video` | POST | Submit video generation job |
| `/api/jobs` | GET | List all jobs |
| `/api/jobs/{id}` | GET | Get job status |
| `/api/jobs/{id}/cancel` | POST | Cancel a running job |
| `/api/estimate` | POST | Estimate VRAM and time for generation |
| `/api/workers` | GET | List available workers |
| `/api/workers/{id}/health` | GET | Get worker health (proxied) |
| `/api/workers/{id}/unload/{model_type}` | POST | Unload model (image/video/assistant) |
| `/api/assist/analyze` | POST | Analyze image and suggest prompts |
| `/api/assist/sessions` | GET | List prompt assistant sessions |
| `/api/assist/sessions/{id}` | GET | Get session conversation |
| `/api/assist/sessions/{id}/resolve` | POST | Mark session as resolved |
| `/api/admin/backfill` | POST | Trigger database backfill |
| `/api/admin/backfill/status` | GET | Check backfill status |

### Worker Endpoints (port 8001+)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Worker health and GPU status |
| `/capabilities` | GET | Get worker capabilities |
| `/generate_image` | POST | Generate image (direct) |
| `/generate_video` | POST | Generate video (direct) |
| `/assist/analyze` | POST | Prompt analysis (direct) |
| `/jobs` | GET | List worker jobs |
| `/jobs/{id}` | GET | Get job status |
| `/jobs/{id}/cancel` | POST | Cancel job |
| `/unload/{model_type}` | POST | Unload model (image/video/assistant) |

## Running the Server

```bash
# Image generation only
python scripts/run_server.py

# With video generation enabled (requires ~60GB GTT for both models)
MYDIFFUSER_VIDEO=1 python scripts/run_server.py

# Lazy loading mode (swaps models on demand, only ~30GB needed)
MYDIFFUSER_LAZY=1 MYDIFFUSER_VIDEO=1 python scripts/run_server.py
```

### Loading Strategies

| Mode | Memory | Behavior |
|------|--------|----------|
| Eager (default) | ~60GB | Both models load at startup, fast switching |
| Lazy (`MYDIFFUSER_LAZY=1`) | ~30GB | Models swap on demand, first request has loading latency |

Lazy loading is useful when GTT is limited (e.g., default 64GB). The first image/video request loads that model; switching types unloads the current model first.

## Development

### Code Quality

**Always run linting after making significant changes:**

```bash
# Check for errors
ruff check src/

# Auto-fix what's possible
ruff check src/ --fix

# Type checking (optional)
mypy src/mydiffuser
```

**Current status (as of 2026-01-03):**
- ✅ **20 total warnings** (down from 41 after recent cleanup)
- ✅ All structural/functional errors fixed
- ✅ All exception handling cleaned up (B904)
- ✅ VRAM tracking and estimation code cleaned up and validated

**Acceptable warnings (should be ignored):**
- **7 × E501**: Lines 1-20 chars over 100-char limit
  - Complex type hints, long config lines
  - In: admin_routes, config, assistant, models, worker files
  - Not worth refactoring
- **3 × B008**: `File()` in FastAPI endpoint defaults
  - Standard FastAPI pattern: `image: UploadFile = File(...)`
  - Works correctly, just flagged by linter
- **4 × RUF006**: `asyncio.create_task()` without storing reference
  - Fire-and-forget background tasks in jobs.py
  - Intentional pattern for polling tasks
- **6 × RUF001/RUF002**: Unicode character warnings
  - Emoji characters in strings (✓, ✗, ⚠, etc.)
  - Intentional for UI feedback

**What should be fixed:**
- ❌ Structural errors (E111, E117, indentation)
- ❌ Undefined names (F821)
- ❌ Bad exception handling (B904 - missing `from e`)
- ❌ Import sorting (I001)
- ❌ Unused variables (F841)
- ❌ Lines >120 chars (excessive)

**Linting configuration:**
- File: `pyproject.toml`
- Line length: 100 chars (modern standard)
- Per-file ignores: UI files (HTML/CSS strings), database.py (SQL queries)

## Configuration Files

- `pyproject.toml` - Dependencies, build config, ruff/mypy settings
- `scripts/install-rocm.sh` - Installs nightly torch with rocm support
- `src/mydiffuser/config.py` - Runtime configuration
- `src/mydiffuser/utils/presets.py` - Generation presets

## Important Considerations

1. **ROCm Compatibility**: Not all diffusers models work on AMD. Wan2.2 has official ROCm support.
2. **Memory**: The 14B video model needs significant VRAM. Framework's unified memory helps.
3. **Torch Backends**: Specific SDP backends are disabled for AMD compatibility (see `configure_torch_backends()`).
4. **Circular Imports**: Use `inference/state.py` and `worker/state.py` for shared state to avoid import cycles.
5. **gfx1151 Workarounds**: Video VAE decode on GPU requires proper cleanup between jobs. CPU fallback available via `MYDIFFUSER_VAE_DEVICE=cpu`. See `vae-issues.md`.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MYDIFFUSER_VIDEO` | `0` | Set to `1` to enable video generation |
| `MYDIFFUSER_LAZY` | `0` | Set to `1` for lazy model loading (swap on demand) |
| `MYDIFFUSER_VIDEO_MODEL` | `5B` | Video model size: `5B` or `14B` |
| `MYDIFFUSER_DTYPE` | `bf16` | Main dtype: `fp32`, `bf16`, `fp16` |
| `MYDIFFUSER_VAE_DTYPE` | `fp32` | VAE dtype (usually fp32 for stability) |
| `MYDIFFUSER_VAE_DEVICE` | `cuda` | VAE device (`cpu` for gfx1151 workaround) |
| `MYDIFFUSER_FLASH_SDP` | `0` | Set to `1` to test flash attention (experimental) |

## Prompt Assistant (Implemented ✓)

**Status**: Fully functional as of 2025-12-31 (commit `bf933a2`)

An AI-powered prompt improvement tool that helps users craft better image generation prompts through iterative analysis and suggestions.

### Features

- **Model**: Qwen2-VL-2B-Instruct (2B params, ~4GB VRAM)
- **UI**: Standalone `/assist` page with chat-style interface
- **Multi-turn conversations**: Persistent sessions with full history
- **Image analysis**: Upload images and get AI-powered feedback
- **Prompt suggestions**: 2-3 specific improvements with rationales
- **Quick actions**: Copy to clipboard or use directly in image generator

### Architecture

**Client/Worker Split**:
- Client: GPU-free UI server, handles routing and session persistence
- Worker: GPU-based inference server, loads Qwen2-VL on-demand
- Communication: Client forwards requests to worker via HTTP

**Memory Management**:
- Loads on first `/assist` request (~15s delay)
- Coexists with image generator (~34GB total: 30GB + 4GB)
- Unloaded when video generation is requested
- Worker health dashboard shows which models are in memory

**Database**:
- SQLite at `outputs/runs.db`
- Tables: `assist_sessions`, `assist_turns`
- Full conversation history with timestamps
- Session status tracking (active, resolved, abandoned)

### Usage Flow

1. Navigate to `/assist` from any page
2. Create new session with a goal (e.g., "improve character interactions")
3. Upload image and enter current prompt
4. Optionally describe specific issue
5. Get AI analysis and 2-3 prompt suggestions
6. Copy suggestion or use directly in `/generate/image`
7. Continue conversation by uploading next iteration
8. Mark session as resolved when satisfied

### API Endpoints

- `POST /api/assist/analyze` - Analyze image and suggest improvements
- `GET /api/assist/sessions` - List recent sessions
- `GET /api/assist/sessions/{id}` - Get full conversation history
- `POST /api/assist/sessions/{id}/resolve` - Mark session as resolved

### SQLite Database

**Status**: Fully implemented (schema v4)

- **Location**: `outputs/runs.db`
- **Tables**:
  - `runs` - All generation metadata with FTS5 full-text search
  - `client_jobs` - Job tracking across client restarts
  - `assist_sessions` - Conversation sessions
  - `assist_turns` - Individual analysis turns with suggestions
- **Features**:
  - Full-text search (FTS5) for prompt search
  - Automatic triggers to keep FTS in sync
  - Job persistence across restarts
  - Conversation history storage
- **Backfill**: Admin UI to populate missing params from meta.json files

## Health Dashboard (Implemented ✓)

**Status**: Fully functional as of 2025-12-31 (commit `fd34423`)

Real-time worker monitoring and GPU resource management interface at `/health-dashboard`.

### Features

- **Real-time monitoring**: Auto-refresh every 3 seconds
- **Worker status**: Online/offline indicators with connection status
- **GPU memory**: Visual progress bars showing used/free memory in GiB
- **Queue status**: See queued and running jobs per worker
- **Active model tracking**: Shows which model was most recently used (single value)
- **Models in memory**: Displays ALL loaded models (can be multiple simultaneously)
- **Model unloading**: Interactive buttons to free GPU memory without restarting
- **Database backfill**: Admin UI to populate missing run parameters

### Model Management

**Unload Buttons**:
- Each loaded model (image, video, assistant) has an "Unload" button
- Click to free GPU memory without restarting the worker
- Models reload automatically on next request (lazy loading)
- Buttons are disabled while a job is running (models locked)
- Shows warning: "⚠ Models locked while job is running"

**Tooltips**:
- **Active Model**: "The model that was most recently used or loaded. Only one model can be active at a time."
- **Models in Memory**: "All models currently loaded in GPU memory. Multiple models can coexist (e.g., image + assistant = 34GB). Use 'Unload' to free GPU memory."

### Architecture

**Client-side**:
- JavaScript auto-refresh every 3 seconds
- Proxies health requests through client API (avoids CORS)
- Displays GPU memory, queue status, model state
- Interactive model unloading with confirmation dialog

**Backend**:
- `GET /api/workers/{id}/health` - Proxy to worker health endpoint
- `POST /api/workers/{id}/unload/{model_type}` - Unload image/video/assistant model
- `POST /api/admin/backfill` - Trigger database backfill
- `GET /api/admin/backfill/status` - Check backfill progress

**Worker endpoints**:
- `GET /health` - Returns GPU status, queue depth, loaded models
- `POST /unload/{model_type}` - Unload specific model (409 if job running)

### Use Cases

1. **Free memory for model swap**: Unload image model before loading video model
2. **Idle model cleanup**: Free GPU memory when models aren't being used
3. **Debugging**: See exactly which models are loaded and active
4. **Multi-worker monitoring**: Monitor multiple workers from one dashboard

## Resource Estimation and VRAM Tracking (Implemented ✓)

**Status**: Fully functional as of 2026-01-03

Real-time VRAM and time estimation for both image and video generation, with actual measurement tracking for performance tuning.

### Features

**Pre-generation Estimation**:
- **Real-time UI updates**: Form fields trigger estimation as user adjusts parameters
- **VRAM prediction**: Shows expected GPU memory usage based on model, resolution, frames
- **Time estimation**: Predicts generation time based on historical performance data
- **Worker availability**: Warns if worker may not have enough VRAM
- **Both forms**: Image generation (`/`) and video generation (`/generate/video`)

**Actual VRAM Tracking**:
- **Generator instrumentation**: Image and video generators capture peak VRAM usage
- **Metadata storage**: Actual VRAM measurements saved to `meta.json` in run directories
- **Performance database**: `data/performance.db` tracks predicted vs actual for model tuning
- **PyTorch integration**: Uses `torch.cuda.reset_peak_memory_stats()` and `torch.cuda.max_memory_allocated()`

### Implementation Details

**Estimation API**:
- `POST /api/estimate` - Predict VRAM and time requirements
- Request: `{ type, model_id, parameters: {width, height, steps, ...}, worker_id }`
- Response: `{ vram_total_needed, time_estimate_seconds, worker_available }`

**VRAM Measurement Flow**:
1. Worker resets CUDA memory stats before generation
2. Generator runs inference
3. Worker captures peak memory allocated/reserved
4. Metadata includes `vram_used` and `vram_reserved` fields
5. Client stores actual VRAM in performance database
6. Estimation engine learns from historical data

**JavaScript Implementation**:
- `image_form.js`: `updateEstimates()` function with event listeners
- `video_form.js`: `updateVideoEstimates()` function with event listeners
- Resolution mapping for video: 480p (832×480), 720p (1280×704), 1080p (1920×1088)
- Frame calculation: `num_frames = duration × fps`

**Files Modified**:
- `src/mydiffuser/client/estimate.py` - Estimation logic
- `src/mydiffuser/generators/image.py` - Returns VRAM data tuple
- `src/mydiffuser/generators/video/wan.py` - Returns VRAM data tuple
- `src/mydiffuser/worker/jobs.py` - Captures and stores VRAM measurements
- `src/mydiffuser/client/static/js/image_form.js` - Real-time estimation UI
- `src/mydiffuser/client/static/js/video_form.js` - Real-time estimation UI

### Use Cases

1. **Prevent OOM failures**: See if worker has enough VRAM before submitting job
2. **Time planning**: Know how long generation will take (important for videos)
3. **Parameter tuning**: Understand VRAM/time tradeoffs for different settings
4. **Performance analysis**: Compare predicted vs actual to improve estimation models

## Common Pitfalls for AI Agents

### 1. Getting "Lost" in Large Files

**Symptom:** Duplicate code, code after return statements, wrong indentation

**Prevention:**
- Read the full method/function before editing
- Use Edit tool with sufficient context
- Verify no return statement exists before adding code

**Example of what NOT to do:**
```python
def my_function():
    result = calculate()
    return result  # ← First return

    # ❌ UNREACHABLE CODE BELOW (agent got lost)
    result = calculate()  # Duplicate
    return result  # Duplicate return
```

### 2. Wrong File Paths

**Symptom:** Edits fail, paths in config don't match actual structure

**Prevention:**
- Use Glob/Find to verify paths exist
- Check `src/mydiffuser/client/` vs `src/mydiffuser/worker/`
- Project uses `worker/` not `server/`

### 3. Breaking ROCm Compatibility

**Symptom:** Code works on CUDA but fails on AMD

**Prevention:**
- Check this file for known ROCm issues
- Don't use `torch.compile()` without testing
- Video VAE decode has gfx1151 stability issues
- Avoid flash-attention or untested SDP backends

### 4. uv sync / pip install torch might replace rocm wheels

**Status:** ⚠️ **PARTIALLY FIXED** - pytorch-rocm nightly index has broken triton dependencies (as of 2026-01-04)

**Symptom:** Python / Torch unable to detect ROCm GPU, or `uv sync` fails with missing triton-rocm dependencies

**Issue Evolution:**
1. **Initial problem (pre-2026-01-04):** `uv sync` would replace ROCm wheels with CUDA versions
2. **First fix:** Added `[tool.uv.sources]` to pin torch to pytorch-rocm index
3. **New problem (2026-01-04 post-reboot):** pytorch-rocm nightly index has missing triton-rocm dependencies
   - torch depends on specific triton-rocm versions (3.5.1+gitbfeb0668, 3.6.0+git8fedd49b, etc.)
   - These triton wheels don't exist in the index
   - `uv sync` fails with "No solution found when resolving dependencies"

**Current Solution (2026-01-04):**

Bypass uv's dependency resolver entirely by installing torch explicitly and removing it from managed dependencies:

1. **scripts/install-rocm.sh** - Explicitly installs torch ROCm first, then manually installs each dependency
   - `uv pip install --pre torch==2.11.0.dev20260102` from ROCm index
   - Manual `uv pip install` for each dependency (accelerate, diffusers, etc.)
   - Avoids `uv sync` which would replace torch

2. **pyproject.toml** - torch removed from `[dependencies]` section
   - Torch is only installed by install-rocm.sh
   - No `[tool.uv.sources]` for torch (not needed with explicit install)
   - Transformers still from GitHub main (for Qwen2-VL)

This works because:
- torch is installed first from the ROCm index wheel (which bundles triton or doesn't need it)
- Other dependencies see torch is already satisfied and don't try to reinstall it
- No dependency resolution that would discover the missing triton packages

**Detection:**

```shell
python -c "import torch; print(f'torch: {torch.__version__}'); print(f'hip: {torch.version.hip}'); print(f'cuda: {torch.version.cuda}')"
torch: 2.11.0.dev20260102+rocm7.1
hip: 7.1.52802
cuda: None
```

If torch doesn't show "+rocm" then hip will be empty and "cuda" should be "None".

**Critical: Do NOT use `uv run`**

`uv run` will ALWAYS replace ROCm torch with CUDA version, even with the explicit install approach. This is because `uv run` does dependency resolution for packages like accelerate/diffusers which depend on torch, and it installs the stable CUDA version from PyPI.

**Correct usage:**
```shell
# ✅ Use the wrapper script (activates venv automatically)
./scripts/run.sh script.py
./scripts/run.sh -c "import torch; print(torch.__version__)"

# ✅ Or activate venv first
source .venv/bin/activate
python script.py

# ❌ NEVER use uv run (will break torch)
uv run python script.py  # Will replace ROCm with CUDA!
```

**If Broken After New Package Install:**

Always use `./scripts/install-rocm.sh` instead of `uv sync` or `uv pip install`:

```shell
uv pip uninstall torch torchvision torchaudio
./scripts/install-rocm.sh
```

## Git Workflow

### When Committing

- Fix ruff errors first (except the 20 acceptable ones)
- Test basic functionality
- Write clear commit messages
- Follow existing style
- Run `bd export -o .beads/issues.jsonl` before committing

### Commit Message Style

```
type: brief description

Problem:
- Issue point 1
- Issue point 2

Solution:
- Fix point 1
- Fix point 2

Result:
- Outcome point 1

Testing:
- Test status

Fixes <issue-id>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

**Types:** `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

## Summary Checklist

Before finishing work:
- [ ] Read relevant sections of AGENTS.md
- [ ] Run `ruff check src/` (20 warnings are acceptable)
- [ ] Test the change locally if possible
- [ ] Update AGENTS.md if architecture changed
- [ ] No duplicate code or unreachable code
- [ ] Client/worker separation maintained
- [ ] Exception handling uses `from e` or `from None`
- [ ] Run `bd export -o .beads/issues.jsonl` if issues were updated

## Future Plans

### Other Future Work
- img2img generation
- Additional video models as ROCm support improves
- Batch generation
- Queue system for long-running jobs


