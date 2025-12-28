"""Video generation UI endpoint."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/video", response_class=HTMLResponse)
def video_page() -> HTMLResponse:
    """Video generation page with source image selection."""
    html = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>mydiffuser - Video</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {
      --bg: #0d1117;
      --surface: #161b22;
      --border: #30363d;
      --text: #e6edf3;
      --text-muted: #8b949e;
      --accent: #8957e5;
      --accent-hover: #a371f7;
      --success: #3fb950;
      --error: #f85149;
    }

    * {
      box-sizing: border-box;
    }

    body {
      font-family: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
      margin: 0;
      padding: 24px;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      background-image:
        radial-gradient(ellipse at 20% 0%, rgba(137, 87, 229, 0.08) 0%, transparent 50%),
        radial-gradient(ellipse at 80% 100%, rgba(63, 185, 80, 0.06) 0%, transparent 50%);
    }

    .container {
      max-width: 900px;
      margin: 0 auto;
    }

    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
    }

    h1 {
      font-size: 1.5rem;
      font-weight: 600;
      margin: 0 0 8px 0;
      letter-spacing: -0.02em;
    }

    .subtitle {
      color: var(--text-muted);
      font-size: 0.85rem;
    }

    .nav-links {
      display: flex;
      gap: 16px;
    }

    .nav-link {
      color: var(--accent);
      text-decoration: none;
      font-size: 0.9rem;
    }

    .nav-link:hover {
      color: var(--accent-hover);
      text-decoration: underline;
    }

    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;
    }

    @media (max-width: 768px) {
      .grid {
        grid-template-columns: 1fr;
      }
    }

    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
    }

    .panel h2 {
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--text-muted);
      margin: 0 0 16px 0;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .source-preview {
      width: 100%;
      aspect-ratio: 1;
      background: var(--bg);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      margin-bottom: 16px;
    }

    .source-preview img {
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
    }

    .source-placeholder {
      color: var(--text-muted);
      font-size: 0.85rem;
      text-align: center;
    }

    label {
      display: block;
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    textarea, input, select {
      width: 100%;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--text);
      font-family: inherit;
      font-size: 0.9rem;
      padding: 12px;
      margin-bottom: 16px;
      transition: border-color 0.15s;
    }

    textarea:focus, input:focus, select:focus {
      outline: none;
      border-color: var(--accent);
    }

    textarea {
      resize: vertical;
      min-height: 100px;
    }

    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }

    .btn {
      width: 100%;
      padding: 14px 20px;
      border: none;
      border-radius: 8px;
      font-family: inherit;
      font-size: 0.95rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s, transform 0.1s;
    }

    .btn:active {
      transform: scale(0.98);
    }

    .btn-primary {
      background: var(--accent);
      color: white;
    }

    .btn-primary:hover:not(:disabled) {
      background: var(--accent-hover);
    }

    .btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .status {
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-top: 16px;
      text-align: center;
    }

    .status.error {
      color: var(--error);
    }

    .status.success {
      color: var(--success);
    }

    .result-section {
      margin-top: 24px;
      display: none;
    }

    .result-section.visible {
      display: block;
    }

    .result-video {
      width: 100%;
      border-radius: 8px;
      background: var(--bg);
    }

    .result-meta {
      margin-top: 12px;
      font-size: 0.8rem;
      color: var(--text-muted);
    }

    .disabled-notice {
      background: rgba(248, 81, 73, 0.1);
      border: 1px solid var(--error);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
      color: var(--error);
      font-size: 0.85rem;
    }

    .loading-banner {
      background: linear-gradient(90deg, rgba(137, 87, 229, 0.15), rgba(63, 185, 80, 0.1));
      border: 1px solid var(--accent);
      border-radius: 8px;
      padding: 12px 16px;
      margin-bottom: 16px;
      display: none;
    }

    .loading-banner.visible {
      display: block;
    }

    .loading-banner .title {
      font-weight: 600;
      margin-bottom: 4px;
    }

    .loading-banner .desc {
      color: var(--text-muted);
      font-size: 0.85rem;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Video Generation</h1>
        <p class="subtitle">Wan I2V • AMD ROCm</p>
      </div>
      <div class="nav-links">
        <a href="/" class="nav-link">← Images</a>
        <a href="/browse" class="nav-link">Browse →</a>
      </div>
    </header>

    <div id="disabledNotice" class="disabled-notice" style="display: none;">
      Video generation is disabled. Set <code>MYDIFFUSER_VIDEO=1</code> to enable.
    </div>

    <div id="loadingBanner" class="loading-banner">
      <div class="title">⏳ Video model not loaded</div>
      <div class="desc">First generation will load the model (5B: ~15s, 14B: ~30s).</div>
    </div>

    <div class="grid">
      <div class="panel">
        <h2>Source Image</h2>
        <div class="source-preview" id="sourcePreview">
          <span class="source-placeholder" id="sourcePlaceholder">
            Paste a run ID or select from Browse
          </span>
          <img id="sourceImage" style="display: none;" alt="Source" />
        </div>
        <label for="sourceRunId">Source Run ID</label>
        <input type="text" id="sourceRunId" placeholder="20251226-123456-abcd1234" />
      </div>

      <div class="panel">
        <h2>Motion Prompt</h2>
        <textarea id="prompt" placeholder="subtle head turn and blink, gentle breathing, soft camera push-in"></textarea>

        <div class="row">
          <div>
            <label for="preset">Preset</label>
            <select id="preset">
              <option value="draft">Draft (fast)</option>
              <option value="final">Final (quality)</option>
              <option value="hq">HQ (slow)</option>
            </select>
          </div>
          <div>
            <label for="modelSize">Model</label>
            <select id="modelSize">
              <option value="5B">5B (~10GB, 720p fast)</option>
              <option value="14B">14B (~28GB, best)</option>
            </select>
          </div>
        </div>

        <div class="row">
          <div>
            <label for="seed">Seed</label>
            <input type="number" id="seed" value="42" min="0" />
          </div>
          <div></div>
        </div>

        <div class="row">
          <div>
            <label for="duration">Duration (sec)</label>
            <input type="number" id="duration" placeholder="5" min="1" max="30" step="1" />
          </div>
          <div>
            <label for="fps">FPS</label>
            <input type="number" id="fps" placeholder="12" min="8" max="30" />
          </div>
        </div>

        <div class="row">
          <div>
            <label for="steps">Steps</label>
            <input type="number" id="steps" placeholder="15" min="1" max="100" />
          </div>
          <div>
            <label for="guidance">Guidance</label>
            <input type="number" id="guidance" placeholder="3.0" min="0" max="20" step="0.1" />
          </div>
        </div>

        <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
          <button class="btn btn-primary" id="generateBtn">Generate Video</button>
          <button class="btn" id="unloadBtn" style="background: var(--border);">⏏ Unload Models</button>
          <span id="gpuStatus" style="font-size: 0.8rem; color: var(--text-muted);"></span>
        </div>
        <div id="status" class="status"></div>
      </div>
    </div>
    <div class="grid">
      <div class="panel">
        <h2>Example Prompts</h2>
        <ul>
          <li>Gentle breathing, subtle head turn, soft camera push-in</li>
          <li>Subtle head turn and blink, gentle breathing, soft camera push-in</li>
          <li>Soft camera push-in, subtle head turn and blink, gentle breathing</li>
        </ul>
      </div>
    </div>
    <div class="result-section" id="resultSection">
      <div class="panel">
        <h2>Result</h2>
        <video class="result-video" id="resultVideo" controls loop></video>
        <div class="result-meta" id="resultMeta"></div>
      </div>
    </div>
  </div>

<script>
const sourceRunIdEl = document.getElementById("sourceRunId");
const sourcePreview = document.getElementById("sourcePreview");
const sourceImage = document.getElementById("sourceImage");
const sourcePlaceholder = document.getElementById("sourcePlaceholder");
const promptEl = document.getElementById("prompt");
const presetEl = document.getElementById("preset");
const modelSizeEl = document.getElementById("modelSize");
const seedEl = document.getElementById("seed");
const durationEl = document.getElementById("duration");
const fpsEl = document.getElementById("fps");
const stepsEl = document.getElementById("steps");
const guidanceEl = document.getElementById("guidance");
const generateBtn = document.getElementById("generateBtn");
const unloadBtn = document.getElementById("unloadBtn");
const gpuStatusEl = document.getElementById("gpuStatus");
const statusEl = document.getElementById("status");
const resultSection = document.getElementById("resultSection");
const resultVideo = document.getElementById("resultVideo");
const resultMeta = document.getElementById("resultMeta");
const disabledNotice = document.getElementById("disabledNotice");
const loadingBanner = document.getElementById("loadingBanner");

// Update GPU status display
async function updateGpuStatus() {
  try {
    const resp = await fetch("/gpu");
    const data = await resp.json();
    if (data.available && data.memory) {
      const m = data.memory;
      gpuStatusEl.textContent = `GPU: ${m.used_gib}/${m.total_gib} GiB (${m.used_percent}%)`;
      if (data.active_model) {
        gpuStatusEl.textContent += ` [${data.active_model}]`;
      }
    }
  } catch (e) {
    console.warn("Failed to get GPU status:", e);
  }
}

// Unload models button
unloadBtn.addEventListener("click", async () => {
  unloadBtn.disabled = true;
  unloadBtn.textContent = "Unloading...";
  try {
    const resp = await fetch("/unload", { method: "POST" });
    const data = await resp.json();
    if (data.gpu_memory) {
      statusEl.textContent = `Models unloaded. GPU: ${data.gpu_memory.free_gib}/${data.gpu_memory.total_gib} GiB free`;
      statusEl.className = "status success";
    } else {
      statusEl.textContent = "Models unloaded.";
      statusEl.className = "status success";
    }
    loadingBanner.classList.add("visible");
    await updateGpuStatus();
  } catch (e) {
    statusEl.textContent = "Failed to unload: " + e.message;
    statusEl.className = "status error";
  } finally {
    unloadBtn.disabled = false;
    unloadBtn.textContent = "⏏ Unload Models";
  }
});

// Check model loading status on page load
async function checkModelStatus() {
  try {
    const resp = await fetch("/health");
    const data = await resp.json();

    // Show disabled notice if video not available at all
    if (!data.models?.video?.available) {
      disabledNotice.style.display = "block";
      return;
    }

    // Show loading banner if lazy loading and video model not loaded
    if (data.lazy_loading && !data.models?.video?.loaded) {
      loadingBanner.classList.add("visible");
    }
  } catch (e) {
    console.warn("Failed to check model status:", e);
  }
}

checkModelStatus();
updateGpuStatus();
setInterval(updateGpuStatus, 10000); // Update every 10 seconds

// Load source from query params
const params = new URLSearchParams(window.location.search);
if (params.has("source")) {
  sourceRunIdEl.value = params.get("source");
  loadSourcePreview(params.get("source"));
}

// Load source preview when run ID changes
sourceRunIdEl.addEventListener("change", () => {
  loadSourcePreview(sourceRunIdEl.value);
});

sourceRunIdEl.addEventListener("blur", () => {
  if (sourceRunIdEl.value) {
    loadSourcePreview(sourceRunIdEl.value);
  }
});

async function loadSourcePreview(runId) {
  if (!runId) return;

  try {
    const resp = await fetch(`/api/runs/${runId}/thumb`);
    if (resp.ok) {
      sourceImage.src = `/api/runs/${runId}/image`;
      sourceImage.style.display = "block";
      sourcePlaceholder.style.display = "none";
    } else {
      sourceImage.style.display = "none";
      sourcePlaceholder.style.display = "block";
      sourcePlaceholder.textContent = "Run not found";
    }
  } catch (e) {
    sourcePlaceholder.textContent = "Error loading preview";
  }
}

function numOrNull(v) {
  if (v === "" || v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

generateBtn.addEventListener("click", async () => {
  const sourceRunId = sourceRunIdEl.value.trim();
  const prompt = promptEl.value.trim();

  if (!sourceRunId) {
    statusEl.textContent = "Please enter a source run ID";
    statusEl.className = "status error";
    return;
  }

  if (!prompt) {
    statusEl.textContent = "Please enter a motion prompt";
    statusEl.className = "status error";
    return;
  }

  const body = {
    source_run_id: sourceRunId,
    prompt: prompt,
    preset: presetEl.value,
    model_size: modelSizeEl.value,
    seed: parseInt(seedEl.value) || 42,
  };

  const duration = numOrNull(durationEl.value);
  const fps = numOrNull(fpsEl.value);
  const steps = numOrNull(stepsEl.value);
  const guidance = numOrNull(guidanceEl.value);

  if (duration !== null) body.duration_seconds = duration;
  if (fps !== null) body.fps = fps;
  if (steps !== null) body.num_inference_steps = steps;
  if (guidance !== null) body.guidance_scale = guidance;

  generateBtn.disabled = true;
  statusEl.textContent = "Generating video... (this may take a while)";
  statusEl.className = "status";
  resultSection.classList.remove("visible");
  loadingBanner.classList.remove("visible");  // Hide banner once generating

  try {
    const resp = await fetch("/generate_video", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await resp.json();

    if (!resp.ok) {
      if (resp.status === 503) {
        disabledNotice.style.display = "block";
      }
      throw new Error(data.detail || "Generation failed");
    }

    statusEl.textContent = `Done in ${data.seconds_elapsed.toFixed(1)}s`;
    statusEl.className = "status success";

    resultVideo.src = `/api/runs/${data.run_id}/video`;
    resultMeta.textContent = `Run: ${data.run_id} | ${data.num_frames} frames @ ${data.fps} fps | ${data.duration_seconds}s`;
    resultSection.classList.add("visible");

  } catch (e) {
    statusEl.textContent = `Error: ${e.message}`;
    statusEl.className = "status error";
  } finally {
    generateBtn.disabled = false;
  }
});
</script>
</body>
</html>"""
    return HTMLResponse(content=html)

