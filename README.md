# mydiffuser

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Experimental playground for image and video generation on AMD Framework Desktop (ROCm/gfx1151)**

Image and video generation server optimized for AMD GPUs (ROCm).

> ⚠️ **Experimental Project**: This is a personal playground for experimenting with diffusion models on AMD ROCm, specifically tested on Framework Desktop with AMD Max+ 395 (gfx1151). Expect rough edges, hardware-specific quirks, and frequent changes.

Supports:
- **Z-Image-Turbo** for text-to-image generation
- **Wan2.2** for image-to-video generation (optional)
- **Qwen2-VL-2B** for AI-powered prompt improvement (optional)

## Requirements

- Python 3.12+
- AMD GPU with ROCm support (tested on AMD Max+ 395 / gfx1201)
- PyTorch with ROCm (nightly recommended for latest GPU support)

### GPU Memory (GTT) Configuration

On AMD APUs with unified memory (like the Max+ 395), you may need to increase the GPU's GTT (Graphics Translation Table) allocation to run large models.

**Check current allocation:**
```bash
sudo dmesg | grep -i "GTT memory"
# Example: [drm] amdgpu: 64042M of GTT memory ready.
```

**To increase GTT (e.g., to 96GB):**

For **systemd-boot** (Arch Linux):
```bash
# Edit your boot entry
sudo nano /boot/loader/entries/arch.conf
# Add to options line: amdgpu.gttsize=98304
```

For **GRUB**:
```bash
sudo nano /etc/default/grub
# Add to GRUB_CMDLINE_LINUX_DEFAULT: amdgpu.gttsize=98304
sudo grub-mkconfig -o /boot/grub/grub.cfg
```

Reboot and verify with `dmesg | grep -i "GTT memory"`.

**Memory requirements:**
- Image model (Z-Image-Turbo): ~30GB
- Video model (Wan2.2-I2V-A14B): ~30GB
- Both models simultaneously: ~60GB (or use lazy loading)

## Quick Start

```bash
# Clone and enter project
cd mydiffuser

# Install dependencies and ROCm PyTorch
./scripts/install-rocm.sh

# Run client (web UI) and worker (GPU inference) separately

# Terminal 1: Start worker (GPU inference server)
./scripts/run.sh scripts/run_worker.py

# Terminal 2: Start client (web UI)
./scripts/run.sh scripts/run_client.py

# Or run both in one terminal (for development)
./scripts/run.sh scripts/run_client.py &
./scripts/run.sh scripts/run_worker.py
```

The **client** (web UI) starts at `http://localhost:8000`
The **worker** (GPU inference) runs at `http://localhost:8001`

> ⚠️ **Important**: Always use `./scripts/run.sh` instead of `uv run` or direct `python` commands. `uv run` will replace ROCm torch with CUDA version!

### Configuration

**Environment Variables:**

- `MYDIFFUSER_VIDEO=1` - Enable video generation (disabled by default due to GPU stability issues on gfx1151)
- `MYDIFFUSER_VAE_DEVICE=cpu` - Use CPU for VAE decode (slower but more stable on some hardware)
- `MYDIFFUSER_VIDEO_MODEL=5B` - Video model size: 5B (fast) or 14B (quality, requires more VRAM)

**Example:**
```bash
# Enable video generation
export MYDIFFUSER_VIDEO=1
./scripts/start-worker.sh
```

## Architecture

MyDiffuser uses a **client/worker split**:

- **Client (port 8000)**: GPU-free web UI server
  - Lightweight FastAPI server for web interface
  - SQLite database for job tracking and history
  - No PyTorch/GPU dependencies
  - Safe to run on any machine

- **Worker (port 8001+)**: GPU inference server
  - Loads diffusion models and runs inference
  - Can run on same machine or remote GPU server
  - Handles model loading, generation, and unloading
  - One or more workers can serve multiple clients

## Web UI (Client - port 8000)

| Page | URL | Description |
|------|-----|-------------|
| Image Generator | `/` | Text-to-image generation |
| Video Generator | `/generate/video` | Image-to-video generation |
| Browse History | `/browse` | View, filter, and remix past generations |
| Prompt Assistant | `/assist` | AI-powered prompt improvement with Qwen2-VL |
| Health Dashboard | `/health-dashboard` | Monitor worker status and GPU usage |

## API Endpoints

### Client Endpoints (port 8000)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI for image generation |
| `/generate/video` | GET | Web UI for video generation |
| `/browse` | GET | Browse past generations |
| `/assist` | GET | Prompt assistant UI |
| `/health-dashboard` | GET | Worker monitoring UI |
| `/health` | GET | Client health check |
| `/api/jobs/image` | POST | Submit image generation job |
| `/api/jobs/video` | POST | Submit video generation job |
| `/api/jobs` | GET | List all jobs |
| `/api/jobs/{id}` | GET | Get job status |
| `/api/jobs/{id}/cancel` | POST | Cancel running job |
| `/api/estimate` | POST | Estimate VRAM and time for generation |
| `/api/workers` | GET | List available workers |
| `/api/workers/{id}/health` | GET | Get worker health (proxied) |
| `/api/workers/{id}/unload/{model_type}` | POST | Unload model |
| `/api/assist/analyze` | POST | Analyze image and get prompt suggestions |
| `/api/assist/sessions` | GET | List prompt assistant sessions |
| `/api/assist/sessions/{id}` | GET | Get session conversation history |
| `/api/assist/sessions/{id}/resolve` | POST | Mark session as resolved |

### Worker Endpoints (port 8001+)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Worker health and GPU status |
| `/capabilities` | GET | Get worker capabilities |
| `/generate_image` | POST | Generate image (direct) |
| `/generate_video` | POST | Generate video (direct) |
| `/assist/analyze` | POST | Prompt analysis (direct) |
| `/jobs/{id}` | GET | Get job status |
| `/jobs/{id}/cancel` | POST | Cancel job |
| `/unload/{model_type}` | POST | Unload model |

### Example API Calls

**Submit an image generation job:**
```bash
curl -X POST http://localhost:8000/api/jobs/image \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A photorealistic cat wearing a tiny hat",
    "preset": "draft",
    "seed": 42
  }'
```

**Submit a video generation job:**
```bash
curl -X POST http://localhost:8000/api/jobs/video \
  -F "image=@path/to/image.png" \
  -F 'request={"prompt": "subtle head turn, gentle breathing", "preset": "draft", "seed": 42}'
```

**Check job status:**
```bash
curl http://localhost:8000/api/jobs/{job_id}
```

## Prompt Assistant

The Prompt Assistant uses Qwen2-VL-2B vision-language model to help you improve your image generation prompts through iterative analysis.

### Features

- **Multi-turn conversations**: Debug prompts over multiple iterations
- **Image analysis**: Upload generated images to get AI-powered feedback
- **Specific suggestions**: Get 2-3 concrete prompt improvements with rationales
- **Session persistence**: Full conversation history saved in SQLite
- **Quick actions**: Copy suggestions to clipboard or use directly in generator

### Usage

1. Navigate to `/assist` from any page
2. Start a new session with your goal (e.g., "improve character interactions")
3. Upload an image and enter the prompt that generated it
4. Optionally describe what's wrong (e.g., "the arms look floating")
5. Get AI analysis and 2-3 improved prompt suggestions
6. Click "Copy" to copy a suggestion, or "Use" to try it in the generator
7. Upload your next iteration to continue the conversation
8. Mark the session as resolved when you're satisfied

### How It Works

The Qwen2-VL-2B model (~4GB VRAM) runs on the worker and loads on-demand when you visit `/assist`. It can coexist with the image generator (~34GB total: 30GB + 4GB). The worker will automatically unload models when switching between types to manage memory.

### Memory Requirements

- Image model: ~30GB
- Video model: ~30GB
- Assistant model: ~4GB
- Image + Assistant together: ~34GB (fits in 96GB allocation)

## Health Dashboard

The Health Dashboard (`/health-dashboard`) provides real-time monitoring and control of worker GPU resources.

### Features

- **Real-time worker status**: See which workers are online/offline with auto-refresh every 3 seconds
- **GPU memory monitoring**: Track GPU usage with visual memory bars showing used/free memory
- **Queue status**: Monitor queued and running jobs per worker
- **Active model tracking**: See which model was most recently used or loaded
- **Models in memory**: View ALL models currently loaded in GPU memory (can be multiple)
- **Model unloading**: Free GPU memory by unloading individual models (image, video, or assistant)
- **Database backfill**: Populate missing parameters from meta.json files in run directories

### Model Management

Each loaded model in the "Models in Memory" section has an **Unload** button:

- Click to free GPU memory without restarting the worker
- Buttons are disabled while a job is running (models are locked)
- After unloading, the model will be lazily reloaded on the next request
- Useful for freeing memory when switching between model types or when models are idle

**Tooltips explain the difference:**
- **Active Model**: Which model was most recently used (single value, tracks lazy loading state)
- **Models in Memory**: All models currently loaded in GPU (can be multiple, e.g., image + assistant = 34GB)

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/workers` | GET | List available workers |
| `/api/workers/{id}/health` | GET | Get worker health (proxied to avoid CORS) |
| `/api/workers/{id}/unload/{model_type}` | POST | Unload specific model (image/video/assistant) |
| `/api/admin/backfill` | POST | Trigger database backfill |
| `/api/admin/backfill/status` | GET | Check backfill status |

## Configuration

### Image Presets

Edit `src/mydiffuser/utils/presets.py` to customize image presets:

```python
PRESETS = {
    "draft": {
        "height": 832,          # Smaller for faster iteration
        "width": 832,
        "num_inference_steps": 4,
        "guidance_scale": 0.0,  # 0.0 for turbo models
    },
    "final": {
        "height": 1024,         # Higher resolution
        "width": 1024,
        "num_inference_steps": 8,
        "guidance_scale": 0.0,
    },
}
```

### Video Presets

See [Wan-AI on Hugging Face](https://huggingface.co/Wan-AI) for available models.

```python
VIDEO_PRESETS = {
    "draft": {
        "model": "Wan-AI/Wan2.2-I2V-A14B-Diffusers",
        "fps": 12,
        "duration_seconds": 3,
        "num_inference_steps": 15,
        "guidance_scale": 3.0,
    },
    "final": {
        "model": "Wan-AI/Wan2.2-I2V-A14B-Diffusers",
        "fps": 16,
        "duration_seconds": 5,
        "num_inference_steps": 30,
        "guidance_scale": 3.5,
    },
    "hq": {
        "model": "Wan-AI/Wan2.2-I2V-A14B-Diffusers",
        "fps": 24,
        "duration_seconds": 7,
        "num_inference_steps": 50,
        "guidance_scale": 4.0,
    },
}
```

### Device & Performance Settings

Edit `src/mydiffuser/config.py`:

```python
DEVICE = "cuda"           # ROCm uses cuda API
DTYPE = torch.bfloat16    # Options: float32 (slow/safe), bfloat16 (balanced), float16 (fast/risky)
```

**dtype recommendations:**
- `torch.float32`: Safest, slowest. Use if you get NaN/crashes.
- `torch.bfloat16`: Good balance of speed and stability (recommended)
- `torch.float16`: Fastest but may cause memory faults on some workloads

### Configuration

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `MYDIFFUSER_VIDEO` | `0` | Set to `1` to enable video generation in worker |
| `MYDIFFUSER_LAZY` | `0` | Set to `1` to enable lazy loading (model swapping) |
| `MYDIFFUSER_VAE_DEVICE` | `cuda` | VAE device (`cpu` for gfx1151 workaround) |
| `MYDIFFUSER_DTYPE` | `bf16` | Main dtype: `fp32`, `bf16`, `fp16` |

**Loading strategies:**
- **Eager** (default): Both models load at startup (~60GB needed)
- **Lazy**: Models swap on demand (~30GB needed, adds loading latency)

## Output Structure

All runs are saved to `outputs/run/` with a unified structure:

```
outputs/
└── run/
    └── 20251225-221530-a1b2c3d4/    # Timestamp + short UUID
        ├── meta.json               # Type, parameters, timing
        ├── thumb.jpg               # Thumbnail (256px)
        ├── prompt.txt              # Input prompt
        ├── request.json            # Full API request
        │
        │ # For image runs:
        ├── output.png              # Generated image
        │
        │ # For video runs:
        ├── input.png               # Source image
        └── output.mp4              # Generated video
```

Run IDs are time-ordered (format: `YYYYMMDD-HHMMSS-<uuid8>`) so they sort chronologically.

### meta.json Structure

```json
{
  "type": "image",
  "run_id": "20251226-123456-abcd1234",
  "timestamp": "2025-12-26T12:34:56Z",
  "prompt": "A cyberpunk cityscape",
  "source_run_id": null,
  "backend": "Tongyi-MAI/Z-Image-Turbo",
  "params": {
    "preset": "draft",
    "seed": 42,
    "height": 832,
    "width": 832
  },
  "outputs": {
    "image": "output.png",
    "thumb": "thumb.jpg"
  },
  "seconds_elapsed": 2.3
}
```

## Project Structure

```
mydiffuser/
├── src/mydiffuser/
│   ├── config.py              # Device, paths, model settings
│   ├── generators/
│   │   ├── base.py            # Abstract generator class
│   │   ├── image.py           # Z-Image-Turbo text-to-image
│   │   └── video/
│   │       ├── base.py        # Abstract video generator
│   │       └── wan.py         # Wan2.2 image-to-video
│   ├── models/
│   │   ├── requests.py        # Pydantic request models
│   │   └── responses.py       # Pydantic response models
│   ├── inference/             # Worker-side model management
│   │   ├── state.py           # Global state (generators, locks)
│   │   ├── assistant.py       # Qwen2-VL prompt assistant
│   │   ├── image.py           # Z-Image Turbo generator
│   │   └── video/
│   │       └── wan.py         # Wan2.2 I2V generator
│   ├── client/                # Client-side (GPU-free)
│   │   ├── app.py             # FastAPI app factory
│   │   ├── database.py        # SQLite CRUD operations
│   │   ├── worker_client.py   # HTTP client for workers
│   │   ├── routes.py          # Job submission endpoints
│   │   ├── ui.py              # Image generation web UI
│   │   ├── assist_ui.py       # Prompt assistant UI
│   │   ├── browse_ui.py       # Run history browser
│   │   ├── health_ui.py       # Worker health dashboard
│   │   └── templates/         # Jinja2 HTML templates
│   ├── worker/                # Worker-side (GPU inference)
│   │   ├── app.py             # FastAPI app factory
│   │   └── routes/
│   │       ├── health.py      # Health check endpoint
│   │       ├── image.py       # /generate_image
│   │       ├── video.py       # /generate_video
│   │       └── assist.py      # /assist/analyze
│   └── utils/
│       ├── paths.py           # Run directory management
│       └── presets.py         # Generation presets
├── scripts/
│   ├── install-rocm.sh        # Install ROCm PyTorch
│   ├── run.sh                 # Wrapper to run with ROCm preserved
│   ├── run_client.py          # Start client server
│   └── run_worker.py          # Start worker server
├── outputs/                   # Generated content (gitignored)
└── docs/                      # Documentation
```

## Development

```bash
# Run linter (20 acceptable warnings documented in AGENTS.md)
ruff check src/

# Auto-fix lint issues
ruff check src/ --fix

# Run type checker (optional)
mypy src/mydiffuser
```

**Note**: See `AGENTS.md` for comprehensive development guidelines including:
- Issue tracking with bd (beads)
- Code quality standards
- ROCm/gfx1151 specific considerations
- Client/worker architecture details
- Common pitfalls for AI agents

## Troubleshooting

### "Memory access fault by GPU"
- Try changing `DTYPE` to `torch.float32` in `config.py`
- Reduce image dimensions in presets

### First request is slow
- This is normal - the model warms up on first inference
- Subsequent requests will be much faster

### Module not found errors
- Make sure you've installed the package: `uv pip install -e .`
- Or run via script: `python scripts/run_server.py`

### Video generation not available
- Set environment variable: `MYDIFFUSER_VIDEO=1`
- Ensure you have enough VRAM (8GB+ for 1.3B model, 24GB+ for 14B)
- The Wan2.1 model downloads on first use



## On Lambda

```
# clean venv
uv pip uninstall -y torch torchvision torchaudio || true

# pick one CUDA channel (example: cu124)
uv pip install torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/cu124

# install your project editable
uv pip install -e .

# optional: dev tools
uv sync --group dev
```


