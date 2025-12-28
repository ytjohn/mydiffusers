"""Web UI endpoint."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index():
    """Minimal single-page UI for image generation."""
    html = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>mydiffuser</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {
      --bg: #0d1117;
      --surface: #161b22;
      --border: #30363d;
      --text: #e6edf3;
      --text-muted: #8b949e;
      --accent: #58a6ff;
      --accent-hover: #79b8ff;
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
        radial-gradient(ellipse at 20% 0%, rgba(88, 166, 255, 0.08) 0%, transparent 50%),
        radial-gradient(ellipse at 80% 100%, rgba(63, 185, 80, 0.06) 0%, transparent 50%);
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

    .container {
      max-width: 1200px;
      margin: 0 auto;
    }

    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;
    }

    @media (max-width: 900px) {
      .grid {
        grid-template-columns: 1fr;
      }
    }

    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
    }

    label {
      display: block;
      font-size: 0.75rem;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 6px;
    }

    textarea {
      width: 100%;
      height: 140px;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px;
      color: var(--text);
      font-family: inherit;
      font-size: 0.9rem;
      resize: vertical;
      transition: border-color 0.15s;
    }

    textarea:focus {
      outline: none;
      border-color: var(--accent);
    }

    .params {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 12px;
      margin-top: 16px;
    }

    input, select {
      width: 100%;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px 12px;
      color: var(--text);
      font-family: inherit;
      font-size: 0.85rem;
      transition: border-color 0.15s;
    }

    input:focus, select:focus {
      outline: none;
      border-color: var(--accent);
    }

    input::placeholder {
      color: var(--text-muted);
    }

    button {
      width: 100%;
      margin-top: 20px;
      padding: 14px 24px;
      background: var(--accent);
      color: var(--bg);
      border: none;
      border-radius: 6px;
      font-family: inherit;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s, transform 0.1s;
    }

    button:hover:not(:disabled) {
      background: var(--accent-hover);
    }

    button:active:not(:disabled) {
      transform: scale(0.98);
    }

    button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .status {
      margin-top: 12px;
      font-size: 0.85rem;
      min-height: 1.5em;
    }

    .status.generating {
      color: var(--accent);
    }

    .status.done {
      color: var(--success);
    }

    .status.error {
      color: var(--error);
    }

    .output-panel {
      display: flex;
      flex-direction: column;
    }

    .image-container {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      background: var(--bg);
      border: 1px dashed var(--border);
      border-radius: 6px;
      min-height: 400px;
      position: relative;
      overflow: hidden;
    }

    .image-container.has-image {
      border-style: solid;
    }

    .placeholder {
      color: var(--text-muted);
      font-size: 0.85rem;
    }

    #img {
      max-width: 100%;
      max-height: 600px;
      border-radius: 4px;
    }

    .meta-container {
      margin-top: 16px;
    }

    pre {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px;
      font-size: 0.75rem;
      overflow: auto;
      max-height: 200px;
      margin: 0;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }

    .generating .placeholder {
      animation: pulse 1.5s ease-in-out infinite;
    }

    .loading-banner {
      background: linear-gradient(90deg, rgba(88, 166, 255, 0.15), rgba(63, 185, 80, 0.1));
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
        <h1>mydiffuser</h1>
        <p class="subtitle">Z-Image Turbo • AMD ROCm</p>
      </div>
      <div class="nav-links">
        <a href="/video" class="nav-link">Video →</a>
        <a href="/browse" class="nav-link">Browse →</a>
      </div>
    </header>

    <div id="loadingBanner" class="loading-banner">
      <div class="title">⏳ Model not loaded</div>
      <div class="desc">First generation will take 30-60s to load the model.</div>
    </div>

    <div class="grid">
      <div class="panel">
        <label>Prompt</label>
        <textarea id="prompt">A photorealistic squishy-faced dog wearing a tiny santa hat, studio lighting</textarea>

        <div class="params">
          <div>
            <label>Preset</label>
            <select id="preset">
              <option value="draft">draft (480p)</option>
              <option value="final" selected>final (720p)</option>
              <option value="custom">custom</option>
            </select>
          </div>
          <div>
            <label>Aspect</label>
            <select id="aspect">
              <option value="landscape" selected>Landscape 16:9</option>
              <option value="portrait">Portrait 9:16</option>
              <option value="square">Square 1:1</option>
            </select>
          </div>
          <div>
            <label>Seed</label>
            <input id="seed" type="number" value="42" min="0" />
          </div>
          <div>
            <label>Steps</label>
            <input id="steps" type="number" placeholder="preset" />
          </div>
          <div>
            <label>Guidance</label>
            <input id="guidance" type="number" step="0.1" placeholder="preset" />
          </div>
        </div>

        <button id="btn">Generate</button>
        <div class="status" id="status"></div>
      </div>

      <div class="panel output-panel">
        <label>Output</label>
        <div class="image-container" id="imageContainer">
          <span class="placeholder">Generated image will appear here</span>
          <img id="img" alt="" style="display: none;" />
        </div>

        <div class="meta-container">
          <label>Metadata</label>
          <pre id="meta">—</pre>
        </div>
      </div>
    </div>
  </div>

<script>
const statusEl = document.getElementById("status");
const metaEl = document.getElementById("meta");
const imgEl = document.getElementById("img");
const imgContainer = document.getElementById("imageContainer");
const btn = document.getElementById("btn");
const placeholder = imgContainer.querySelector(".placeholder");

function numOrNull(v) {
  if (v === "" || v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

// Parse query params and pre-fill form (for "Use as Template" flow)
function loadFromQueryParams() {
  const params = new URLSearchParams(window.location.search);

  if (params.has("prompt")) {
    document.getElementById("prompt").value = params.get("prompt");
  }
  if (params.has("preset")) {
    document.getElementById("preset").value = params.get("preset");
  }
  if (params.has("aspect")) {
    document.getElementById("aspect").value = params.get("aspect");
  }
  if (params.has("seed")) {
    document.getElementById("seed").value = params.get("seed");
  }
  if (params.has("steps")) {
    document.getElementById("steps").value = params.get("steps");
  }
  if (params.has("guidance")) {
    document.getElementById("guidance").value = params.get("guidance");
  }

  // Clear the query string from URL without reload (cleaner UX)
  if (params.toString()) {
    window.history.replaceState({}, "", "/");
  }
}

loadFromQueryParams();

// Check model loading status on page load
async function checkModelStatus() {
  try {
    const resp = await fetch("/health");
    const data = await resp.json();
    const banner = document.getElementById("loadingBanner");

    // Show banner if lazy loading is enabled and image model not loaded
    if (data.lazy_loading && !data.models?.image?.loaded) {
      banner.classList.add("visible");
    }
  } catch (e) {
    console.warn("Failed to check model status:", e);
  }
}

checkModelStatus();

btn.addEventListener("click", async () => {
  // Hide the loading banner once user starts generating
  document.getElementById("loadingBanner").classList.remove("visible");
  statusEl.textContent = "Generating...";
  statusEl.className = "status generating";
  metaEl.textContent = "—";
  imgEl.style.display = "none";
  placeholder.style.display = "block";
  imgContainer.classList.remove("has-image");
  imgContainer.classList.add("generating");
  btn.disabled = true;

  const req = {
    prompt: document.getElementById("prompt").value,
    preset: document.getElementById("preset").value,
    aspect_ratio: document.getElementById("aspect").value,
    seed: Number(document.getElementById("seed").value) || 0,
    num_inference_steps: numOrNull(document.getElementById("steps").value),
    guidance_scale: numOrNull(document.getElementById("guidance").value),
  };

  try {
    const resp = await fetch("/generate_image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req)
    });

    imgContainer.classList.remove("generating");

    if (!resp.ok) {
      const errText = await resp.text();
      statusEl.textContent = "Error";
      statusEl.className = "status error";
      metaEl.textContent = errText;
      btn.disabled = false;
      return;
    }

    const metaHeader = resp.headers.get("X-Gen-Meta");
    if (metaHeader) {
      try {
        metaEl.textContent = JSON.stringify(JSON.parse(metaHeader), null, 2);
      } catch {
        metaEl.textContent = metaHeader;
      }
    }

    const blob = await resp.blob();
    placeholder.style.display = "none";
    imgEl.src = URL.createObjectURL(blob);
    imgEl.style.display = "block";
    imgContainer.classList.add("has-image");
    statusEl.textContent = "Done";
    statusEl.className = "status done";
  } catch (e) {
    imgContainer.classList.remove("generating");
    statusEl.textContent = "Error";
    statusEl.className = "status error";
    metaEl.textContent = String(e);
  }

  btn.disabled = false;
});
</script>
</body>
</html>"""
    return HTMLResponse(content=html)

