const LIMIT = 24;
let currentPage = 1;
let totalRuns = 0;
let totalPages = 1;
let currentFilter = "all";
let currentRunId = null;
let currentRunData = null;
let availableTags = [];
let selectedTags = new Set();  // Tags to INCLUDE (show ONLY these)
let showNsfw = false;           // NSFW toggle state

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

// Tag filter functions
async function loadTagFilters() {
  try {
    const resp = await fetch('/api/runs/tags');
    const data = await resp.json();
    availableTags = data.tags;

    // Restore state from localStorage
    const savedTags = localStorage.getItem('selectedTags');
    const savedNsfw = localStorage.getItem('showNsfw');

    selectedTags = savedTags ? new Set(JSON.parse(savedTags)) : new Set();
    showNsfw = savedNsfw === 'true';

    renderTagFilters();
  } catch (error) {
    console.error('Failed to load tags:', error);
  }
}

function renderTagFilters() {
  const container = document.getElementById('tagFilters');
  const label = container.querySelector('span');
  container.innerHTML = '';
  container.appendChild(label);

  // Render regular tags (excluding nsfw)
  const regularTags = availableTags.filter(t => t !== 'nsfw');
  regularTags.forEach(tag => {
    const isSelected = selectedTags.has(tag);
    const toggle = document.createElement('div');
    toggle.className = `tag-filter-toggle ${isSelected ? 'active' : ''}`;
    toggle.innerHTML = `
      <input type="checkbox" ${isSelected ? 'checked' : ''}
             style="margin-right: 4px;" id="tag_${tag}">
      <span>${tag}</span>
    `;

    toggle.addEventListener('click', () => {
      if (selectedTags.has(tag)) {
        selectedTags.delete(tag);
      } else {
        selectedTags.add(tag);
      }
      localStorage.setItem('selectedTags', JSON.stringify([...selectedTags]));
      renderTagFilters();
      currentPage = 1;
      loadRuns();
    });

    container.appendChild(toggle);
  });

  // Render NSFW toggle (special styling)
  if (availableTags.includes('nsfw')) {
    const nsfwToggle = document.createElement('div');
    nsfwToggle.className = `tag-filter-toggle nsfw-toggle ${showNsfw ? 'active' : ''}`;
    nsfwToggle.style.borderColor = showNsfw ? '#f85149' : 'var(--border)';
    nsfwToggle.style.background = showNsfw ? '#f85149' : 'var(--bg)';
    nsfwToggle.innerHTML = `
      <input type="checkbox" ${showNsfw ? 'checked' : ''}
             style="margin-right: 4px;" id="tag_nsfw">
      <span>Show NSFW</span>
    `;

    nsfwToggle.addEventListener('click', () => {
      showNsfw = !showNsfw;
      localStorage.setItem('showNsfw', showNsfw.toString());
      renderTagFilters();
      currentPage = 1;
      loadRuns();
    });

    container.appendChild(nsfwToggle);
  }
}

async function loadRuns() {
  contentEl.innerHTML = '<div class="loading">Loading...</div>';

  try {
    const includeParam = selectedTags.size ? `&include_tags=${[...selectedTags].join(',')}` : '';
    const nsfwParam = `&show_nsfw=${showNsfw}`;
    const resp = await fetch(`/api/runs?type=${currentFilter}&page=${currentPage}&limit=${LIMIT}${includeParam}${nsfwParam}`);
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

      // Generate tag badges
      const tagBadges = run.tags && run.tags.length ?
        run.tags.map(t => `<span class="tag-badge ${t === 'nsfw' ? 'nsfw' : 'default'}">${t}</span>`).join(' ') : '';

      html += `
        <div class="thumb-card" data-id="${run.id}" data-type="${run.type}">
          <span class="thumb-badge ${badgeClass}">${run.type}</span>
          <img class="thumb-img" src="/api/runs/${run.id}/thumb" alt="" loading="lazy" />
          <div class="thumb-info">
            <div class="thumb-timestamp">${run.timestamp}</div>
            <div class="thumb-prompt">${escapeHtml(run.prompt_preview) || "(no prompt)"}</div>
            ${lineageHtml}
            ${tagBadges ? `<div style="margin-top: 4px;">${tagBadges}</div>` : ''}
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
      sourceLink.href = `/browse?run=${currentRunData.source_run_id}`;
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

    // Render tags
    renderModalTags();

  } catch (e) {
    modalPrompt.textContent = `Error: ${e.message}`;
  }
}

function renderModalTags() {
  const container = document.getElementById('modalTags');
  container.innerHTML = '';

  if (!currentRunData.tags || currentRunData.tags.length === 0) {
    container.innerHTML = '<span style="color: var(--text-muted); font-size: 0.85rem;">No tags</span>';
    return;
  }

  currentRunData.tags.forEach(tag => {
    const chip = document.createElement('div');
    chip.className = 'tag-chip';
    chip.style.background = tag === 'nsfw' ? '#f85149' : 'var(--accent)';
    chip.innerHTML = `
      <span>${tag}</span>
      <button onclick="removeTag('${tag}')" title="Remove tag">&times;</button>
    `;
    container.appendChild(chip);
  });
}

window.removeTag = async function(tag) {
  const newTags = currentRunData.tags.filter(t => t !== tag);
  await updateRunTags(newTags);
};

document.getElementById('addTagBtn').addEventListener('click', async () => {
  const input = document.getElementById('newTagInput');
  const newTag = input.value.trim().toLowerCase();

  if (!newTag) return;
  if (currentRunData.tags && currentRunData.tags.includes(newTag)) {
    alert('Tag already exists');
    return;
  }

  const newTags = [...(currentRunData.tags || []), newTag];
  await updateRunTags(newTags);
  input.value = '';
});

// Allow Enter key to add tag
document.getElementById('newTagInput').addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    document.getElementById('addTagBtn').click();
  }
});

async function updateRunTags(newTags) {
  try {
    const resp = await fetch(`/api/runs/${currentRunId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags: newTags })
    });

    if (!resp.ok) throw new Error('Failed to update tags');

    currentRunData.tags = newTags;
    renderModalTags();
    await loadTagFilters(); // Refresh available tags
    loadRuns(); // Refresh grid
  } catch (e) {
    alert(`Error updating tags: ${e.message}`);
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

// Detect if we're on client (has /generate/image) or old server (has / for image gen)
// Simple detection: try to check if /generate/image exists by seeing if client is running
const isClient = window.location.port === "8000" || document.title.includes("Client");

templateBtn.addEventListener("click", () => {
  if (!currentRunData) return;

  const params = new URLSearchParams();
  params.set("prompt", currentRunData.prompt);
  params.set("preset", currentRunData.preset);
  params.set("seed", currentRunData.seed);
  if (currentRunData.aspect_ratio) params.set("aspect_ratio", currentRunData.aspect_ratio);
  if (currentRunData.height) params.set("height", currentRunData.height);
  if (currentRunData.width) params.set("width", currentRunData.width);
  if (currentRunData.num_inference_steps) params.set("steps", currentRunData.num_inference_steps);
  if (currentRunData.guidance_scale !== undefined) params.set("guidance", currentRunData.guidance_scale);

  // Client uses /generate/image, old server uses /
  const imageUrl = isClient ? "/generate/image" : "/";
  window.location.href = imageUrl + "?" + params.toString();
});

videoBtn.addEventListener("click", () => {
  if (!currentRunId) return;

  // Client uses /generate/video, old server uses /video
  const videoUrl = isClient ? "/generate/video" : "/video";
  window.location.href = `${videoUrl}?source=${currentRunId}`;
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
(async () => {
  await loadTagFilters();
  loadRuns();
})();

// Check for URL parameter to open specific run
const urlParams = new URLSearchParams(window.location.search);
const runParam = urlParams.get('run');
if (runParam) {
  // Fetch run details to determine type, then open modal
  fetch(`/api/runs/${runParam}`)
    .then(res => res.json())
    .then(data => {
      openModal(runParam, data.type);
      // Clear URL parameter after opening (cleaner UX)
      window.history.replaceState({}, '', '/browse');
    })
    .catch(err => {
      console.error('Failed to load run from URL parameter:', err);
    });
}
