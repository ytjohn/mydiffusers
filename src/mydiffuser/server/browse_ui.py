"""Browse UI endpoint for viewing past generations."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/browse", response_class=HTMLResponse)
def browse_page() -> HTMLResponse:
    """Browse page for viewing past generations."""
    html = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>mydiffuser - Browse</title>
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
      --danger: #da3633;
      --danger-hover: #f85149;
      --badge-image: #238636;
      --badge-video: #8957e5;
      --badge-img2img: #bf8700;
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

    .container {
      max-width: 1400px;
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
      margin: 0;
      letter-spacing: -0.02em;
    }

    .subtitle {
      color: var(--text-muted);
      font-size: 0.85rem;
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

    /* Filter tabs */
    .filter-tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }

    .filter-tab {
      padding: 8px 16px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 20px;
      color: var(--text-muted);
      font-family: inherit;
      font-size: 0.8rem;
      cursor: pointer;
      transition: all 0.15s;
    }

    .filter-tab:hover {
      border-color: var(--accent);
      color: var(--text);
    }

    .filter-tab.active {
      background: var(--accent);
      border-color: var(--accent);
      color: var(--bg);
    }

    .filter-tab .count {
      opacity: 0.7;
      font-size: 0.75rem;
      margin-left: 4px;
    }

    .thumb-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 16px;
    }

    .thumb-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
      cursor: pointer;
      transition: border-color 0.15s, transform 0.1s;
      position: relative;
    }

    .thumb-card:hover {
      border-color: var(--accent);
      transform: translateY(-2px);
    }

    .thumb-img {
      width: 100%;
      aspect-ratio: 1;
      object-fit: cover;
      background: var(--bg);
    }

    .thumb-badge {
      position: absolute;
      top: 8px;
      left: 8px;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 0.65rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .thumb-badge.image {
      background: var(--badge-image);
      color: white;
    }

    .thumb-badge.video {
      background: var(--badge-video);
      color: white;
    }

    .thumb-badge.img2img {
      background: var(--badge-img2img);
      color: white;
    }

    .thumb-info {
      padding: 10px;
    }

    .thumb-timestamp {
      font-size: 0.7rem;
      color: var(--text-muted);
      margin-bottom: 4px;
    }

    .thumb-prompt {
      font-size: 0.75rem;
      color: var(--text);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .thumb-lineage {
      font-size: 0.65rem;
      color: var(--text-muted);
      margin-top: 4px;
    }

    .pagination {
      display: flex;
      justify-content: center;
      gap: 12px;
      margin-top: 24px;
    }

    .pagination button {
      padding: 10px 20px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--text);
      font-family: inherit;
      font-size: 0.85rem;
      cursor: pointer;
      transition: border-color 0.15s;
    }

    .pagination button:hover:not(:disabled) {
      border-color: var(--accent);
    }

    .pagination button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .pagination .page-info {
      display: flex;
      align-items: center;
      color: var(--text-muted);
      font-size: 0.85rem;
    }

    .empty-state {
      text-align: center;
      color: var(--text-muted);
      padding: 60px 20px;
    }

    /* Modal */
    .modal-overlay {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.8);
      z-index: 1000;
      overflow: auto;
      padding: 24px;
    }

    .modal-overlay.active {
      display: flex;
      align-items: flex-start;
      justify-content: center;
    }

    .modal {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      max-width: 1000px;
      width: 100%;
      margin-top: 40px;
    }

    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 20px;
      border-bottom: 1px solid var(--border);
    }

    .modal-header-left {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .modal-title {
      font-size: 0.9rem;
      color: var(--text-muted);
    }

    .modal-type-badge {
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 0.7rem;
      font-weight: 600;
      text-transform: uppercase;
    }

    .modal-type-badge.image {
      background: var(--badge-image);
      color: white;
    }

    .modal-type-badge.video {
      background: var(--badge-video);
      color: white;
    }

    .modal-type-badge.img2img {
      background: var(--badge-img2img);
      color: white;
    }

    .modal-close {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 1.5rem;
      cursor: pointer;
      padding: 0;
      line-height: 1;
    }

    .modal-close:hover {
      color: var(--text);
    }

    .modal-body {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      padding: 20px;
    }

    @media (max-width: 768px) {
      .modal-body {
        grid-template-columns: 1fr;
      }
    }

    .modal-image {
      width: 100%;
      border-radius: 6px;
      background: var(--bg);
    }

    .modal-video {
      width: 100%;
      border-radius: 6px;
      background: var(--bg);
    }

    .modal-details {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .detail-section h3 {
      font-size: 0.75rem;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin: 0 0 8px 0;
    }

    .detail-section pre {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px;
      font-size: 0.8rem;
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 200px;
      overflow: auto;
    }

    .params-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
    }

    .param-item {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 10px;
    }

    .param-label {
      font-size: 0.65rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .param-value {
      font-size: 0.85rem;
      color: var(--text);
      margin-top: 2px;
    }

    .source-link {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
      color: var(--accent);
      text-decoration: none;
      font-size: 0.8rem;
      display: block;
    }

    .source-link:hover {
      border-color: var(--accent);
    }

    .modal-actions {
      display: flex;
      gap: 12px;
      padding-top: 8px;
      flex-wrap: wrap;
    }

    .btn {
      flex: 1;
      padding: 12px 16px;
      border: none;
      border-radius: 6px;
      font-family: inherit;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s;
      min-width: 120px;
    }

    .btn-primary {
      background: var(--accent);
      color: var(--bg);
    }

    .btn-primary:hover {
      background: var(--accent-hover);
    }

    .btn-secondary {
      background: var(--badge-video);
      color: white;
    }

    .btn-secondary:hover {
      opacity: 0.9;
    }

    .btn-danger {
      background: var(--danger);
      color: var(--text);
    }

    .btn-danger:hover {
      background: var(--danger-hover);
    }

    .loading {
      text-align: center;
      color: var(--text-muted);
      padding: 40px;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Browse History</h1>
        <p class="subtitle">View and manage past generations</p>
      </div>
      <a href="/" class="nav-link">← Back to Generator</a>
    </header>

    <div class="filter-tabs" id="filterTabs">
      <button class="filter-tab active" data-type="all">All</button>
      <button class="filter-tab" data-type="image">Images</button>
      <button class="filter-tab" data-type="video">Videos</button>
    </div>

    <div id="content">
      <div class="loading">Loading...</div>
    </div>

    <div class="pagination" id="pagination" style="display: none;">
      <button id="prevBtn">← Previous</button>
      <span class="page-info" id="pageInfo"></span>
      <button id="nextBtn">Next →</button>
    </div>
  </div>

  <div class="modal-overlay" id="modalOverlay">
    <div class="modal">
      <div class="modal-header">
        <div class="modal-header-left">
          <span class="modal-title" id="modalTitle"></span>
          <span class="modal-type-badge" id="modalTypeBadge"></span>
        </div>
        <button class="modal-close" id="modalClose">×</button>
      </div>
      <div class="modal-body">
        <div id="modalMediaContainer">
          <img class="modal-image" id="modalImage" alt="" />
        </div>
        <div class="modal-details">
          <div class="detail-section">
            <h3>Prompt</h3>
            <pre id="modalPrompt"></pre>
          </div>
          <div class="detail-section" id="sourceSection" style="display: none;">
            <h3>Source</h3>
            <a class="source-link" id="sourceLink" href="#">View source run →</a>
          </div>
          <div class="detail-section">
            <h3>Parameters</h3>
            <div class="params-grid" id="modalParams"></div>
          </div>
          <div class="modal-actions" id="modalActions">
            <button class="btn btn-primary" id="templateBtn">Use as Template</button>
            <button class="btn btn-secondary" id="videoBtn" style="display: none;">Generate Video</button>
            <button class="btn btn-danger" id="deleteBtn">Delete</button>
          </div>
        </div>
      </div>
    </div>
  </div>

<script>
const LIMIT = 24;
let currentPage = 1;
let totalRuns = 0;
let totalPages = 1;
let currentFilter = "all";
let currentRunId = null;
let currentRunData = null;

const contentEl = document.getElementById("content");
const paginationEl = document.getElementById("pagination");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const pageInfoEl = document.getElementById("pageInfo");
const filterTabs = document.querySelectorAll(".filter-tab");

const modalOverlay = document.getElementById("modalOverlay");
const modalClose = document.getElementById("modalClose");
const modalTitle = document.getElementById("modalTitle");
const modalTypeBadge = document.getElementById("modalTypeBadge");
const modalMediaContainer = document.getElementById("modalMediaContainer");
const modalImage = document.getElementById("modalImage");
const modalPrompt = document.getElementById("modalPrompt");
const modalParams = document.getElementById("modalParams");
const sourceSection = document.getElementById("sourceSection");
const sourceLink = document.getElementById("sourceLink");
const templateBtn = document.getElementById("templateBtn");
const videoBtn = document.getElementById("videoBtn");
const deleteBtn = document.getElementById("deleteBtn");

// Filter tab handlers
filterTabs.forEach(tab => {
  tab.addEventListener("click", () => {
    filterTabs.forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    currentFilter = tab.dataset.type;
    currentPage = 1;
    loadRuns();
  });
});

async function loadRuns() {
  contentEl.innerHTML = '<div class="loading">Loading...</div>';

  try {
    const resp = await fetch(`/api/runs?type=${currentFilter}&page=${currentPage}&limit=${LIMIT}`);
    if (!resp.ok) throw new Error("Failed to load runs");

    const data = await resp.json();
    totalRuns = data.total;
    totalPages = data.pages;

    if (data.runs.length === 0) {
      contentEl.innerHTML = '<div class="empty-state">No generations yet. Go create something!</div>';
      paginationEl.style.display = "none";
      return;
    }

    let html = '<div class="thumb-grid">';
    for (const run of data.runs) {
      const badgeClass = run.type || "image";
      const lineageHtml = run.source_run_id
        ? `<div class="thumb-lineage">from ${run.source_run_id.substring(0, 15)}...</div>`
        : "";

      html += `
        <div class="thumb-card" data-id="${run.id}" data-type="${run.type}">
          <span class="thumb-badge ${badgeClass}">${run.type}</span>
          <img class="thumb-img" src="/api/runs/${run.id}/thumb" alt="" loading="lazy" />
          <div class="thumb-info">
            <div class="thumb-timestamp">${run.timestamp}</div>
            <div class="thumb-prompt">${escapeHtml(run.prompt_preview) || "(no prompt)"}</div>
            ${lineageHtml}
          </div>
        </div>
      `;
    }
    html += '</div>';
    contentEl.innerHTML = html;

    // Add click handlers
    contentEl.querySelectorAll(".thumb-card").forEach(card => {
      card.addEventListener("click", () => openModal(card.dataset.id, card.dataset.type));
    });

    // Update pagination
    updatePagination();

  } catch (e) {
    contentEl.innerHTML = `<div class="empty-state">Error loading runs: ${e.message}</div>`;
  }
}

function updatePagination() {
  if (totalPages <= 1) {
    paginationEl.style.display = "none";
    return;
  }

  paginationEl.style.display = "flex";
  pageInfoEl.textContent = `Page ${currentPage} of ${totalPages} (${totalRuns} runs)`;
  prevBtn.disabled = currentPage === 1;
  nextBtn.disabled = currentPage >= totalPages;
}

prevBtn.addEventListener("click", () => {
  if (currentPage > 1) {
    currentPage--;
    loadRuns();
  }
});

nextBtn.addEventListener("click", () => {
  if (currentPage < totalPages) {
    currentPage++;
    loadRuns();
  }
});

async function openModal(runId, runType) {
  currentRunId = runId;
  modalOverlay.classList.add("active");
  modalTitle.textContent = runId;
  modalPrompt.textContent = "Loading...";
  modalParams.innerHTML = "";
  sourceSection.style.display = "none";

  // Set type badge
  modalTypeBadge.textContent = runType || "image";
  modalTypeBadge.className = `modal-type-badge ${runType || "image"}`;

  // Show appropriate media
  if (runType === "video") {
    modalMediaContainer.innerHTML = `
      <video class="modal-video" id="modalVideo" controls autoplay loop>
        <source src="/api/runs/${runId}/video" type="video/mp4">
        Your browser does not support video.
      </video>
    `;
    videoBtn.style.display = "none";
  } else {
    modalMediaContainer.innerHTML = `<img class="modal-image" id="modalImage" src="/api/runs/${runId}/image" alt="" />`;
    videoBtn.style.display = "inline-block";
  }

  try {
    const resp = await fetch(`/api/runs/${runId}`);
    if (!resp.ok) throw new Error("Failed to load run details");

    currentRunData = await resp.json();
    modalPrompt.textContent = currentRunData.prompt || "(no prompt)";

    // Show source link if applicable
    if (currentRunData.source_run_id) {
      sourceSection.style.display = "block";
      sourceLink.textContent = `View source: ${currentRunData.source_run_id}`;
      sourceLink.href = "#";
      sourceLink.onclick = (e) => {
        e.preventDefault();
        closeModal();
        openModal(currentRunData.source_run_id, "image");
      };
    }

    const params = [
      { label: "Preset", value: currentRunData.preset },
      { label: "Seed", value: currentRunData.seed },
      { label: "Size", value: `${currentRunData.width}×${currentRunData.height}` },
      { label: "Steps", value: currentRunData.num_inference_steps },
      { label: "Guidance", value: currentRunData.guidance_scale },
      { label: "Time", value: currentRunData.seconds ? `${currentRunData.seconds.toFixed(1)}s` : "—" },
    ];

    if (currentRunData.backend) {
      params.push({ label: "Backend", value: currentRunData.backend.split("/").pop() });
    }

    modalParams.innerHTML = params.map(p => `
      <div class="param-item">
        <div class="param-label">${p.label}</div>
        <div class="param-value">${p.value}</div>
      </div>
    `).join("");

  } catch (e) {
    modalPrompt.textContent = `Error: ${e.message}`;
  }
}

function closeModal() {
  modalOverlay.classList.remove("active");
  // Stop any playing video
  const video = document.getElementById("modalVideo");
  if (video) video.pause();
  currentRunId = null;
  currentRunData = null;
}

modalClose.addEventListener("click", closeModal);
modalOverlay.addEventListener("click", (e) => {
  if (e.target === modalOverlay) closeModal();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && modalOverlay.classList.contains("active")) {
    closeModal();
  }
});

templateBtn.addEventListener("click", () => {
  if (!currentRunData) return;

  const params = new URLSearchParams();
  params.set("prompt", currentRunData.prompt);
  params.set("preset", currentRunData.preset);
  params.set("seed", currentRunData.seed);
  if (currentRunData.height) params.set("height", currentRunData.height);
  if (currentRunData.width) params.set("width", currentRunData.width);
  if (currentRunData.num_inference_steps) params.set("steps", currentRunData.num_inference_steps);
  if (currentRunData.guidance_scale !== undefined) params.set("guidance", currentRunData.guidance_scale);

  window.location.href = "/?" + params.toString();
});

videoBtn.addEventListener("click", () => {
  if (!currentRunId) return;

  // Navigate to video generation UI with source run ID
  window.location.href = `/video?source=${currentRunId}`;
});

deleteBtn.addEventListener("click", async () => {
  if (!currentRunId) return;

  if (!confirm(`Delete run ${currentRunId}? This cannot be undone.`)) return;

  try {
    const resp = await fetch(`/api/runs/${currentRunId}`, { method: "DELETE" });
    if (!resp.ok) throw new Error("Failed to delete");

    closeModal();
    loadRuns();
  } catch (e) {
    alert(`Error deleting: ${e.message}`);
  }
});

function escapeHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// Initial load
loadRuns();
</script>
</body>
</html>"""
    return HTMLResponse(content=html)
