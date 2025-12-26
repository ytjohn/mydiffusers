# mydiffuser

Image and video generation server optimized for AMD GPUs (ROCm).

Currently supports **Z-Image-Turbo** for text-to-image generation, with video generation planned.

## Requirements

- Python 3.12+
- AMD GPU with ROCm support (tested on AMD Max+ 395 / gfx1201)
- PyTorch with ROCm (nightly recommended for latest GPU support)

## Quick Start

```bash
# Clone and enter project
cd mydiffuser

# Create virtual environment
uv venv
source .venv/bin/activate

# Install PyTorch with ROCm (nightly for gfx1201 support)

# This MUST be done before doing a uv sync or pip install. 

uv pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/rocm7.0

# Install the project in editable mode
uv pip install -e .

# Run the server
python scripts/run_server.py
```

The server starts at `http://localhost:8000`. Open it in a browser for the web UI.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI for interactive generation |
| `/health` | GET | Server status and configuration |
| `/generate` | POST | Generate image, return JSON metadata |
| `/generate_image` | POST | Generate image, return PNG bytes |

### Example API Call

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A photorealistic cat wearing a tiny hat",
    "preset": "draft",
    "seed": 42
  }'
```

## Configuration

### Generation Presets

Edit `src/mydiffuser/utils/presets.py` to customize presets:

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

**Parameters:**
- `height` / `width`: Output dimensions (must be multiples of 8, range 256-2048)
- `num_inference_steps`: More steps = better quality but slower (4-12 typical for turbo)
- `guidance_scale`: Classifier-free guidance (use 0.0 for Z-Image-Turbo)

### Device & Performance Settings

Edit `src/mydiffuser/config.py`:

```python
# Device settings
DEVICE = "cuda"           # ROCm uses cuda API
DTYPE = torch.bfloat16    # Options: float32 (slow/safe), bfloat16 (balanced), float16 (fast/risky)

# Warmup settings (adjust if you want faster startup at cost of first-request latency)
WARMUP_HEIGHT = 832
WARMUP_WIDTH = 832
WARMUP_STEPS = 4
```

**dtype recommendations:**
- `torch.float32`: Safest, slowest. Use if you get NaN/crashes.
- `torch.bfloat16`: Good balance of speed and stability (recommended for gfx1201)
- `torch.float16`: Fastest but may cause memory faults on some workloads

## Output Structure

Generated images are saved to `outputs/run/image/`:

```
outputs/
└── run/
    └── image/
        └── 20251225-221530-a1b2c3d4/    # Timestamp + short UUID
            ├── output.png               # Generated image
            ├── prompt.txt               # Input prompt
            ├── request.json             # Full API request
            ├── resolved.json            # Resolved parameters (preset + overrides)
            └── meta.json                # Generation metadata (time, device, etc.)
```

Run IDs are time-ordered (format: `YYYYMMDD-HHMMSS-<uuid8>`) so they sort chronologically.

## Project Structure

```
mydiffuser/
├── src/mydiffuser/
│   ├── config.py              # Device, paths, model settings
│   ├── generators/
│   │   ├── base.py            # Abstract generator class
│   │   ├── image.py           # Z-Image-Turbo text-to-image
│   │   ├── img2img.py         # (placeholder)
│   │   └── video/             # (placeholder for SVD, etc.)
│   ├── models/
│   │   ├── requests.py        # Pydantic request models
│   │   └── responses.py       # Pydantic response models
│   ├── server/
│   │   ├── app.py             # FastAPI app factory
│   │   ├── state.py           # Global state (loaded model)
│   │   ├── ui.py              # Web UI
│   │   └── routes/
│   │       ├── health.py      # /health endpoint
│   │       ├── image.py       # /generate, /generate_image
│   │       └── video.py       # (placeholder)
│   └── utils/
│       ├── paths.py           # Run directory management
│       └── presets.py         # Generation presets ← EDIT THIS
├── scripts/
│   └── run_server.py          # Entry point
├── outputs/                   # Generated images (gitignored)
└── archive/                   # Old experimental files
```

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run linter
ruff check src/

# Run type checker
mypy src/mydiffuser

# Auto-fix lint issues
ruff check src/ --fix
```

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

## License

MIT
