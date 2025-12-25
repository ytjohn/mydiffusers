import time
from pathlib import Path
from typing import Optional, Literal
import logging
import asyncio
import io
import json
import uuid
import shutil
import subprocess


import numpy as np
import torch
from diffusers import ZImagePipeline
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response, HTMLResponse
from pydantic import BaseModel, Field
from PIL import Image

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---- Config ----
DEVICE = "mps"

# Pick what is stable for you.
# float32 is safest but slowest; bfloat16/float16 are faster but may be less stable.
# DTYPE = torch.float32
DTYPE = torch.bfloat16
# DTYPE = torch.float16

OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Z-Image Turbo API", version="0.2")

pipe: Optional[ZImagePipeline] = None
infer_lock = asyncio.Lock()

PresetName = Literal["draft", "final", "custom"]


PRESETS = {
    # Fast iteration preset
    "draft": {
        "height": 832,
        "width": 832,
        "num_inference_steps": 6,
        "guidance_scale": 0.0,
    },
    # Higher quality preset
    "final": {
        "height": 1024,
        "width": 1024,
        "num_inference_steps": 9,
        "guidance_scale": 0.0,
    },
}

RUNS_DIR = OUTPUT_DIR / "run"
RUNS_IMAGE_DIR = RUNS_DIR / "image"
RUNS_VIDEO_DIR = RUNS_DIR / "video"
RUNS_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
RUNS_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

# Point this at a script/command you control.
# You can start with a placeholder and wire it later.
TUNEAVIDEO_CMD = None
# Example (you’ll set this once you have a runner):
# TUNEAVIDEO_CMD = ["python", "/path/to/tuneavideo_runner.py"]

def new_run_id() -> str:
    return str(uuid.uuid4())

def run_dir(kind: str, run_id: str) -> Path:
    if kind == "image":
        d = RUNS_IMAGE_DIR / run_id
    elif kind == "video":
        d = RUNS_VIDEO_DIR / run_id
    else:
        raise ValueError("kind must be image|video")
    d.mkdir(parents=True, exist_ok=True)
    return d

def write_text(p: Path, s: str):
    p.write_text(s, encoding="utf-8")

def write_json(p: Path, obj: dict):
    p.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")

def safe_under_outputs(path_str: str) -> Path:
    """
    Allow referencing an existing file only if it's under OUTPUT_DIR.
    """
    p = (Path(__file__).parent / path_str).resolve()
    if OUTPUT_DIR.resolve() not in p.parents and p != OUTPUT_DIR.resolve():
        raise ValueError("path must be under outputs/")
    return p

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)

    preset: PresetName = Field("final", description="draft|final|custom")

    # If preset is draft/final, these can be omitted and defaults come from the preset.
    # If preset is custom, these are used (or their defaults below).
    height: Optional[int] = Field(None, ge=256, le=2048, multiple_of=8)
    width: Optional[int] = Field(None, ge=256, le=2048, multiple_of=8)

    num_inference_steps: Optional[int] = Field(None, ge=1, le=50)
    guidance_scale: Optional[float] = Field(None, ge=0.0, le=20.0)

    seed: int = Field(42, ge=0, le=2**31 - 1)


class GenerateResponse(BaseModel):
    saved_to: Optional[str] = None
    seconds: float
    seed: int
    height: int
    width: int
    num_inference_steps: int
    guidance_scale: float
    preset: str
    run_id: str
    run_dir: str
    

def safe_output_path(rel_path: str) -> Path:
    """
    Prevent path traversal. We only allow writes under OUTPUT_DIR.
    """
    rel = Path(rel_path)

    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("save_path must be a relative path under outputs/")

    if rel.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        if rel.suffix == "":
            rel = rel.with_suffix(".png")
        else:
            raise ValueError("Unsupported file extension. Use png/jpg/jpeg/webp.")

    out = (OUTPUT_DIR / rel).resolve()
    if OUTPUT_DIR.resolve() not in out.parents and out != OUTPUT_DIR.resolve():
        raise ValueError("save_path must stay under outputs/")

    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def apply_preset(req: GenerateRequest) -> dict:
    """
    Returns a dict of effective params (height, width, steps, guidance_scale).
    Request fields override preset values when explicitly provided.
    """
    if req.preset in ("draft", "final"):
        base = dict(PRESETS[req.preset])
    else:
        base = {
            "height": 1024,
            "width": 1024,
            "num_inference_steps": 9,
            "guidance_scale": 0.0,
        }

    # Override with request values if provided
    if req.height is not None:
        base["height"] = req.height
    if req.width is not None:
        base["width"] = req.width
    if req.num_inference_steps is not None:
        base["num_inference_steps"] = req.num_inference_steps
    if req.guidance_scale is not None:
        base["guidance_scale"] = req.guidance_scale

    # Final sanity checks (Pydantic already checks if fields are present, but preset values bypass that)
    h, w = base["height"], base["width"]
    if h % 8 != 0 or w % 8 != 0:
        raise ValueError("height and width must be multiples of 8")
    if not (256 <= h <= 2048 and 256 <= w <= 2048):
        raise ValueError("height/width must be within 256..2048")

    return base


def run_inference(prompt: str, height: int, width: int, steps: int, guidance: float, seed: int) -> tuple[np.ndarray, float]:
    """
    Runs the pipeline and returns (img_np, seconds).
    img_np is float32/float16 etc in [0,1] ideally with shape (H, W, 3).
    """
    assert pipe is not None

    t0 = time.time()
    gen = torch.Generator(DEVICE).manual_seed(seed)

    out = pipe(
        prompt=prompt,
        height=height,
        width=width,
        num_inference_steps=steps,
        guidance_scale=guidance,
        generator=gen,
        output_type="np",
    )
    img = out.images[0]
    dt = time.time() - t0

    # Fail loudly if NaN/Inf
    if not np.isfinite(img).all():
        raise HTTPException(
            status_code=500,
            detail="Non-finite values (NaN/Inf) in output; try float32, different seed, or smaller resolution.",
        )

    # Clamp just in case there are minor out-of-range values
    img = np.clip(img, 0.0, 1.0)

    return img, dt


def np_to_png_bytes(img: np.ndarray) -> bytes:
    pil = Image.fromarray((img * 255).round().astype("uint8"))
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


@app.on_event("startup")
def startup():
    global pipe
    start_time = time.time()
    logger.info("Loading Z-Image-Turbo model... dtype=%s device=%s", DTYPE, DEVICE)

    pipe = ZImagePipeline.from_pretrained(
        "Tongyi-MAI/Z-Image-Turbo",
        torch_dtype=DTYPE,
        low_cpu_mem_usage=False,
    ).to(DEVICE)

    logger.info("Model loaded in %.2fs", time.time() - start_time)

    # Warmup (keeps first real request snappy)
    warm0 = time.time()
    _ = pipe(
        prompt="warmup",
        height=512,
        width=512,
        num_inference_steps=2,
        guidance_scale=0.0,
        generator=torch.Generator(DEVICE).manual_seed(0),
        output_type="np",
    )
    logger.info("Pipeline warmup completed in %.2fs", time.time() - warm0)


@app.get("/health")
def health():
    return {
        "ok": True,
        "device": DEVICE,
        "dtype": str(DTYPE),
        "model_loaded": pipe is not None,
        "presets": PRESETS,
    }


def generate_and_save(req: GenerateRequest) -> tuple[np.ndarray, dict, str, Path, Path]:
    """
    Shared logic: applies preset, runs inference, saves all files.
    Returns: (img_array, metadata_dict, run_id, run_dir_path, output_png_path)
    """
    try:
        params = apply_preset(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Create run ID and directory
    rid = new_run_id()
    rd = run_dir("image", rid)

    # Save inputs
    write_json(rd / "request.json", req.model_dump())
    write_json(rd / "resolved.json", {**params, "seed": req.seed, "preset": req.preset})
    write_text(rd / "prompt.txt", req.prompt)

    logger.info(
        "Generate preset=%s h=%d w=%d steps=%d guidance=%.2f seed=%d",
        req.preset,
        params["height"],
        params["width"],
        params["num_inference_steps"],
        params["guidance_scale"],
        req.seed,
    )

    img, dt = run_inference(
        prompt=req.prompt,
        height=params["height"],
        width=params["width"],
        steps=params["num_inference_steps"],
        guidance=params["guidance_scale"],
        seed=req.seed,
    )

    out_path = rd / "output.png"
    Image.fromarray((img * 255).round().astype("uint8")).save(out_path)

    saved_rel = str(out_path.relative_to(Path(__file__).parent))
    logger.info("Saved %s in %.2fs", saved_rel, dt)

    meta = {
        "seconds": dt,
        "seed": req.seed,
        "preset": req.preset,
        "height": params["height"],
        "width": params["width"],
        "num_inference_steps": params["num_inference_steps"],
        "guidance_scale": params["guidance_scale"],
        "device": DEVICE,
        "dtype": str(DTYPE),
    }
    write_json(rd / "meta.json", meta)

    return img, meta, rid, rd, out_path


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    """
    JSON in -> save file -> JSON out.
    """
    if pipe is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    async with infer_lock:
        img, meta, rid, rd, out_path = generate_and_save(req)

    return GenerateResponse(
        run_id=rid,
        run_dir=str(rd.relative_to(Path(__file__).parent)),
        saved_to=str(out_path.relative_to(Path(__file__).parent)),
        seconds=meta["seconds"],
        seed=meta["seed"],
        height=meta["height"],
        width=meta["width"],
        num_inference_steps=meta["num_inference_steps"],
        guidance_scale=meta["guidance_scale"],
        preset=meta["preset"],
    )


@app.post("/generate_image")
async def generate_image(req: GenerateRequest):
    """
    JSON in -> returns PNG bytes + saves files.
    Response headers include X-Gen-Meta with a small JSON string.
    """
    if pipe is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    async with infer_lock:
        img, meta, rid, rd, out_path = generate_and_save(req)

    png = np_to_png_bytes(img)

    return Response(
        content=png,
        media_type="image/png",
        headers={"X-Gen-Meta": json.dumps(meta)},
    )


@app.get("/")
def index():
    """
    Minimal single-page UI.
    """
    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Z-Image Turbo</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; margin: 20px; }}
    textarea {{ width: 100%; height: 120px; }}
    .row {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 10px; }}
    .row > div {{ min-width: 180px; }}
    label {{ display:block; font-weight: 600; margin-bottom: 6px; }}
    input, select {{ width: 100%; padding: 8px; }}
    button {{ padding: 10px 14px; font-weight: 700; }}
    pre {{ background: #f4f4f4; padding: 12px; overflow:auto; }}
    img {{ max-width: 100%; border: 1px solid #ddd; margin-top: 12px; }}
    .status {{ margin-top: 10px; }}
  </style>
</head>
<body>
  <h2>Z-Image Turbo</h2>
  <p>Preset controls most settings; you can override height/width/steps/guidance if you want.</p>

  <label>Prompt</label>
  <textarea id="prompt">A photorealistic squishy-faced dog wearing a tiny santa hat, studio lighting</textarea>

  <div class="row">
    <div>
      <label>Preset</label>
      <select id="preset">
        <option value="draft">draft</option>
        <option value="final" selected>final</option>
        <option value="custom">custom</option>
      </select>
    </div>
    <div>
      <label>Seed</label>
      <input id="seed" type="number" value="42" min="0" />
    </div>
    <div>
      <label>Height</label>
      <input id="height" type="number" placeholder="(from preset)" />
    </div>
    <div>
      <label>Width</label>
      <input id="width" type="number" placeholder="(from preset)" />
    </div>
    <div>
      <label>Steps</label>
      <input id="steps" type="number" placeholder="(from preset)" />
    </div>
    <div>
      <label>Guidance</label>
      <input id="guidance" type="number" step="0.1" placeholder="(from preset)" />
    </div>
  </div>

  <div class="row">
    <button id="btn">Generate</button>
    <div class="status" id="status"></div>
  </div>

  <img id="img" alt="result will appear here" />
  <h3>Response</h3>
  <pre id="meta"></pre>

<script>
const statusEl = document.getElementById("status");
const metaEl = document.getElementById("meta");
const imgEl = document.getElementById("img");

function numOrNull(v) {{
  if (v === "" || v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}}

document.getElementById("btn").addEventListener("click", async () => {{
  statusEl.textContent = "Generating...";
  metaEl.textContent = "";
  imgEl.removeAttribute("src");

  const req = {{
    prompt: document.getElementById("prompt").value,
    preset: document.getElementById("preset").value,
    seed: Number(document.getElementById("seed").value) || 0,
    height: numOrNull(document.getElementById("height").value),
    width: numOrNull(document.getElementById("width").value),
    num_inference_steps: numOrNull(document.getElementById("steps").value),
    guidance_scale: numOrNull(document.getElementById("guidance").value),
  }};

  try {{
    const resp = await fetch("/generate_image", {{
      method: "POST",
      headers: {{
        "Content-Type": "application/json"
      }},
      body: JSON.stringify(req)
    }});

    if (!resp.ok) {{
      const errText = await resp.text();
      statusEl.textContent = "Error";
      metaEl.textContent = errText;
      return;
    }}

    const metaHeader = resp.headers.get("X-Gen-Meta");
    if (metaHeader) {{
      try {{
        metaEl.textContent = JSON.stringify(JSON.parse(metaHeader), null, 2);
      }} catch {{
        metaEl.textContent = metaHeader;
      }}
    }}

    const blob = await resp.blob();
    imgEl.src = URL.createObjectURL(blob);
    statusEl.textContent = "Done";
  }} catch (e) {{
    statusEl.textContent = "Error";
    metaEl.textContent = String(e);
  }}
}});
</script>
</body>
</html>"""
    return HTMLResponse(content=html)
