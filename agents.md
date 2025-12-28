# MyDiffuser - Project Context for AI Agents

## Project Overview

MyDiffuser is a FastAPI-based image and video generation server optimized for **AMD ROCm** on the **Framework Desktop with AMD Max+ 395** (128GB unified memory). It provides a web UI and REST API for AI-powered content generation.

## Hardware Context

- **GPU**: AMD Max+ 395 (Strix Point APU, gfx1151)
- **Memory**: 128GB unified memory (96GB allocated to GPU via BIOS, 32GB to CPU)
- **OS**: Ubuntu 24.04.3 LTS, kernel 6.14
- **Platform**: ROCm 7.0 (nightly PyTorch wheels) - some models/features may have compatibility differences
- **PyTorch**: Configured for `bfloat16` with math-only SDP backend for AMD stability

### ROCm/gfx1151 Known Issues

The gfx1151 GPU architecture is very new and has limited MIOpen kernel support:
- **No pre-built kernel database** - MIOpen must JIT-compile kernels
- **conv3d instability** - Video VAE decode fails on GPU with HIP launch errors
- **Workaround**: VAE decode runs on CPU (slower but stable)

See `vae-issues.md` for debugging history and workarounds.

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

```
src/mydiffuser/
├── config.py           # Central config: device, dtype, paths, models
├── utils/
│   ├── paths.py        # Run ID generation, file I/O, thumbnails
│   └── presets.py      # Image and video generation presets
├── models/
│   ├── requests.py     # Pydantic request models
│   └── responses.py    # Pydantic response models
├── generators/
│   ├── base.py         # Abstract BaseGenerator
│   ├── image.py        # Z-Image Turbo generator
│   └── video/
│       ├── base.py     # Abstract BaseVideoGenerator
│       └── wan.py      # Wan2.2 I2V generator
└── server/
    ├── app.py          # FastAPI app factory, startup logic
    ├── state.py        # Global state (generators, locks)
    ├── ui.py           # Image generation web UI
    ├── video_ui.py     # Video generation web UI
    ├── browse_ui.py    # Run history browser
    └── routes/
        ├── health.py   # Health check endpoint
        ├── image.py    # /generate, /generate_image
        └── video.py    # /generate_video
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

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Image generation UI |
| `/video` | GET | Video generation UI |
| `/browse` | GET | Run history browser |
| `/health` | GET | Health check |
| `/generate` | POST | Generate image (legacy) |
| `/generate_image` | POST | Generate image |
| `/generate_video` | POST | Generate video from image |

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

```bash
# Linting
ruff check src/

# Type checking
mypy src/mydiffuser

# Auto-fix lint issues
ruff check src/ --fix
```

## Configuration Files

- `pyproject.toml` - Dependencies, build config, ruff/mypy settings
- `src/mydiffuser/config.py` - Runtime configuration
- `src/mydiffuser/utils/presets.py` - Generation presets

## Important Considerations

1. **ROCm Compatibility**: Not all diffusers models work on AMD. Wan2.2 has official ROCm support.
2. **Memory**: The 14B video model needs significant VRAM. Framework's unified memory helps.
3. **Torch Backends**: Specific SDP backends are disabled for AMD compatibility (see `configure_torch_backends()`).
4. **Circular Imports**: Use `server/state.py` for shared state to avoid import cycles.
5. **gfx1151 Workarounds**: Video VAE must run on CPU due to MIOpen conv3d issues. See `vae-issues.md`.

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

## Future Plans

### Prompt Assistant (Planned)
See `plan-for-prompt-assist.md` for full details.

- **Goal**: AI-powered help for crafting better image prompts
- **Model**: Qwen2-VL-2B (2B params, supports image AND video understanding)
- **Approach**: On-demand loading to avoid GPU memory conflicts
- **Alternative**: CPU-only mode (slower but zero GPU impact)
- **Use case**: "My characters aren't interacting" → get improved prompt suggestions
- **Multi-turn**: Chat-style debugging sessions (30+ iterations is common)

### SQLite Database (Planned)
Part of the prompt assistant plan - see `plan-for-prompt-assist.md`.

- **Location**: `outputs/mydiffuser.db`
- **Library**: `aiosqlite` for async FastAPI compatibility
- **Purpose**: 
  - Conversation session persistence
  - Prompt search (full-text search with FTS5)
  - Pattern knowledge base ("what worked before")
  - Run metadata (faster than scanning JSON files)
- **Hybrid approach**: DB for metadata/search, filesystem for binary assets

### Other Future Work
- img2img generation
- Additional video models as ROCm support improves
- Batch generation
- Queue system for long-running jobs

