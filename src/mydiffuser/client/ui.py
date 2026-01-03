"""Client UI forms for job submission."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

# Setup Jinja2 templates
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/generate/image", response_class=HTMLResponse)
def image_form(request: Request):
    """Image generation form with worker selection."""
    return templates.TemplateResponse("generate_image.html", {"request": request})


# Legacy inline HTML image form (keeping for reference, can be deleted later)
def _image_form_old() -> str:
    """OLD: Image generation form with inline HTML."""
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Generate Image - MyDiffuser Client</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0d1117;
            color: #e6edf3;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        h1 {
            font-size: 2em;
            margin-bottom: 0.5em;
            color: #58a6ff;
        }
        .nav {
            margin-bottom: 2em;
            padding-bottom: 1em;
            border-bottom: 1px solid #30363d;
        }
        .nav a {
            color: #58a6ff;
            text-decoration: none;
            margin-right: 1em;
        }
        .nav a:hover {
            text-decoration: underline;
        }
        .form-group {
            margin-bottom: 1.5em;
        }
        label {
            display: block;
            margin-bottom: 0.5em;
            font-weight: 600;
            color: #8b949e;
        }
        input[type="text"],
        input[type="number"],
        select,
        textarea {
            width: 100%;
            padding: 10px;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: #e6edf3;
            font-size: 14px;
            font-family: inherit;
        }
        textarea {
            min-height: 120px;
            resize: vertical;
        }
        input:focus, select:focus, textarea:focus {
            outline: none;
            border-color: #58a6ff;
        }
        .preset-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
        }
        .preset-btn {
            display: block;
            width: 100%;
            padding: 12px;
            background: #161b22;
            border: 2px solid #30363d;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
            text-align: center;
            color: #e6edf3;
            font-family: inherit;
        }
        .preset-btn:hover {
            border-color: #58a6ff;
            background: #1c2128;
        }
        .preset-btn:active {
            background: #238636;
            border-color: #238636;
        }
        .preset-name {
            font-weight: 600;
            display: block;
            margin-bottom: 4px;
        }
        .preset-desc {
            font-size: 12px;
            color: #8b949e;
        }
        button {
            background: #238636;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover {
            background: #2ea043;
        }
        button:active {
            background: #1f7a2e;
        }
        .info {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 1.5em;
            font-size: 14px;
            color: #8b949e;
        }
        #status {
            margin-top: 20px;
            padding: 15px;
            border-radius: 6px;
            display: none;
        }
        #status.success {
            background: #1a3d2a;
            border: 1px solid #238636;
            color: #3fb950;
            display: block;
        }
        #status.error {
            background: #3d1a1a;
            border: 1px solid #f85149;
            color: #f85149;
            display: block;
        }
        #status.progress {
            background: #1c2a3d;
            border: 1px solid #58a6ff;
            color: #58a6ff;
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎨 Generate Image</h1>

        <div class="nav">
            <a href="/">← Home</a>
            <a href="/browse">Browse Results</a>
            <a href="/jobs">Job Queue</a>
            <a href="/generate/video">Generate Video</a>
        </div>

        <div class="info">
            <strong>Note:</strong> This form submits jobs to remote workers.
            Results will automatically appear in <a href="/browse" style="color: #58a6ff;">Browse</a> when complete.
        </div>

        <form id="imageForm" onsubmit="submitImageJob(event)">
            <div class="form-group">
                <label for="prompt">Prompt *</label>
                <textarea
                    id="prompt"
                    name="prompt"
                    required
                    placeholder="a serene mountain landscape at sunset, photorealistic, 4k"
                ></textarea>
            </div>

            <div class="form-group">
                <label for="worker">Worker *</label>
                <select id="worker" name="worker" required>
                    <option value="local" selected>Local Worker (localhost:8001)</option>
                    <option value="remote">Remote Worker (localhost:8002)</option>
                </select>
            </div>

            <div class="form-group">
                <label>Quick Presets (click to populate form)</label>
                <div class="preset-grid">
                    <button type="button" class="preset-btn" onclick="applyImagePreset('draft')">
                        <span class="preset-name">Draft</span>
                        <span class="preset-desc">480p, 4 steps</span>
                    </button>
                    <button type="button" class="preset-btn" onclick="applyImagePreset('fast')">
                        <span class="preset-name">Fast</span>
                        <span class="preset-desc">480p, 6 steps</span>
                    </button>
                    <button type="button" class="preset-btn" onclick="applyImagePreset('balanced')">
                        <span class="preset-name">Balanced</span>
                        <span class="preset-desc">720p, 8 steps</span>
                    </button>
                    <button type="button" class="preset-btn" onclick="applyImagePreset('quality')">
                        <span class="preset-name">Quality</span>
                        <span class="preset-desc">720p, 12 steps</span>
                    </button>
                </div>
            </div>

            <div class="form-group">
                <label for="aspect_ratio">Aspect Ratio *</label>
                <select id="aspect_ratio" name="aspect_ratio" required>
                    <option value="landscape" selected>Landscape 16:9</option>
                    <option value="portrait">Portrait 9:16</option>
                    <option value="square">Square 1:1</option>
                </select>
            </div>

            <div class="form-group">
                <label for="height">Height (pixels) *</label>
                <input type="number" id="height" name="height" value="480" min="256" max="2048" step="8" required>
            </div>

            <div class="form-group">
                <label for="width">Width (pixels) *</label>
                <input type="number" id="width" name="width" value="832" min="256" max="2048" step="8" required>
            </div>

            <div class="form-group">
                <label for="seed">Seed</label>
                <input type="number" id="seed" name="seed" value="42" min="0" max="999999">
            </div>

            <div class="form-group">
                <label for="steps">Steps *</label>
                <input type="number" id="steps" name="steps" value="4" min="1" max="100" required>
            </div>

            <div class="form-group">
                <label for="guidance">Guidance Scale *</label>
                <input type="number" id="guidance" name="guidance" value="0.0" min="0" max="20" step="0.1" required>
            </div>

            <button type="submit">Generate Image</button>
        </form>

        <div id="status"></div>
    </div>

    <script>
        // Aspect ratio dimensions
        const ASPECT_RATIOS = {
            landscape: { width: 832, height: 480 },   // 16:9 480p
            portrait: { width: 480, height: 832 },    // 9:16 480p
            square: { width: 768, height: 768 },      // 1:1 square
        };

        // Image presets (populate form fields)
        const IMAGE_PRESETS = {
            draft: { height: 480, width: 832, steps: 4, guidance: 0.0 },
            fast: { height: 480, width: 832, steps: 6, guidance: 0.0 },
            balanced: { height: 704, width: 1280, steps: 8, guidance: 0.0 },
            quality: { height: 704, width: 1280, steps: 12, guidance: 0.0 },
        };

        function applyImagePreset(name) {
            const preset = IMAGE_PRESETS[name];
            if (!preset) return;

            document.getElementById('height').value = preset.height;
            document.getElementById('width').value = preset.width;
            document.getElementById('steps').value = preset.steps;
            document.getElementById('guidance').value = preset.guidance;
        }

        // Update height/width when aspect ratio changes
        document.getElementById('aspect_ratio').addEventListener('change', (e) => {
            const ratio = ASPECT_RATIOS[e.target.value];
            if (ratio) {
                document.getElementById('height').value = ratio.height;
                document.getElementById('width').value = ratio.width;
            }
        });

        // Load form from query parameters (for "Use as Template" flow)
        function loadFromQueryParams() {
            const params = new URLSearchParams(window.location.search);

            if (params.has('prompt')) {
                document.getElementById('prompt').value = params.get('prompt');
            }
            if (params.has('aspect_ratio')) {
                document.getElementById('aspect_ratio').value = params.get('aspect_ratio');
            }
            if (params.has('height')) {
                document.getElementById('height').value = params.get('height');
            }
            if (params.has('width')) {
                document.getElementById('width').value = params.get('width');
            }
            if (params.has('seed')) {
                document.getElementById('seed').value = params.get('seed');
            }
            if (params.has('steps')) {
                document.getElementById('steps').value = params.get('steps');
            }
            if (params.has('guidance')) {
                document.getElementById('guidance').value = params.get('guidance');
            }

            // Clear query params from URL after loading (cleaner UX)
            if (params.toString()) {
                window.history.replaceState({}, '', '/generate/image');
            }
        }

        // Load on page load
        loadFromQueryParams();

        async function submitImageJob(event) {
            event.preventDefault();

            const form = document.getElementById('imageForm');
            const formData = new FormData(form);
            const statusDiv = document.getElementById('status');

            // Show submitting status
            statusDiv.className = 'progress';
            statusDiv.textContent = 'Submitting job to worker...';

            try {
                const response = await fetch('/api/jobs/image', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (!response.ok) {
                    throw new Error(result.detail || 'Submission failed');
                }

                // Show success with job ID
                statusDiv.className = 'progress';
                statusDiv.innerHTML = `
                    <strong>✓ Job submitted!</strong><br>
                    Job ID: ${result.job_id}<br>
                    Worker: ${result.worker}<br>
                    <br>
                    Monitoring progress... (polling every 2 seconds)<br>
                    <span id="progressStatus">Waiting...</span>
                `;

                // Start polling for progress
                pollJobStatus(result.job_id);

            } catch (error) {
                statusDiv.className = 'error';
                statusDiv.textContent = '✗ Error: ' + error.message;
            }
        }

        async function pollJobStatus(jobId) {
            const statusSpan = document.getElementById('progressStatus');
            const statusDiv = document.getElementById('status');

            const poll = async () => {
                try {
                    const response = await fetch(`/api/jobs/${jobId}`);
                    const job = await response.json();

                    const percent = Math.round(job.progress.progress * 100);
                    const step = job.progress.step;
                    const total = job.progress.total_steps;

                    if (job.status === 'complete') {
                        statusDiv.className = 'success';
                        statusDiv.innerHTML = `
                            <strong>✓ Generation complete!</strong><br>
                            Job ID: ${jobId}<br>
                            Run ID: ${job.results.local_run_id}<br>
                            <br>
                            <a href="/browse" style="color: #3fb950; font-weight: 600;">→ View in Browse</a>
                        `;
                        return;
                    } else if (job.status === 'failed') {
                        statusDiv.className = 'error';
                        statusDiv.textContent = '✗ Generation failed: ' + (job.error || 'Unknown error');
                        return;
                    }

                    // Update progress
                    statusSpan.textContent = `${job.status} - ${percent}% (step ${step}/${total})`;

                    // Continue polling
                    setTimeout(poll, 2000);

                } catch (error) {
                    statusDiv.className = 'error';
                    statusDiv.textContent = '✗ Error checking status: ' + error.message;
                }
            };

            poll();
        }
    </script>
</body>
</html>
"""


@router.get("/generate/video", response_class=HTMLResponse)
def video_form(request: Request):
    """Video generation form with worker selection and image upload."""
    return templates.TemplateResponse("generate_video.html", {"request": request})


# Legacy inline HTML video form (keeping for reference, can be deleted later)
def _video_form_old() -> str:
    """OLD: Video generation form with inline HTML."""
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Generate Video - MyDiffuser Client</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0d1117;
            color: #e6edf3;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        h1 {
            font-size: 2em;
            margin-bottom: 0.5em;
            color: #58a6ff;
        }
        .nav {
            margin-bottom: 2em;
            padding-bottom: 1em;
            border-bottom: 1px solid #30363d;
        }
        .nav a {
            color: #58a6ff;
            text-decoration: none;
            margin-right: 1em;
        }
        .nav a:hover {
            text-decoration: underline;
        }
        .form-group {
            margin-bottom: 1.5em;
        }
        label {
            display: block;
            margin-bottom: 0.5em;
            font-weight: 600;
            color: #8b949e;
        }
        input[type="text"],
        input[type="number"],
        input[type="file"],
        select,
        textarea {
            width: 100%;
            padding: 10px;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: #e6edf3;
            font-size: 14px;
            font-family: inherit;
        }
        textarea {
            min-height: 100px;
            resize: vertical;
        }
        input:focus, select:focus, textarea:focus {
            outline: none;
            border-color: #58a6ff;
        }
        .preset-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
        }
        .preset-btn {
            display: block;
            width: 100%;
            padding: 12px;
            background: #161b22;
            border: 2px solid #30363d;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
            text-align: center;
            color: #e6edf3;
            font-family: inherit;
        }
        .preset-btn:hover {
            border-color: #58a6ff;
            background: #1c2128;
        }
        .preset-btn:active {
            background: #238636;
            border-color: #238636;
        }
        .preset-name {
            font-weight: 600;
            display: block;
            margin-bottom: 4px;
        }
        .preset-desc {
            font-size: 12px;
            color: #8b949e;
        }
        button {
            background: #238636;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover {
            background: #2ea043;
        }
        button:active {
            background: #1f7a2e;
        }
        .info {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 1.5em;
            font-size: 14px;
            color: #8b949e;
        }
        .file-upload {
            border: 2px dashed #30363d;
            border-radius: 6px;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            transition: border-color 0.2s;
        }
        .file-upload:hover {
            border-color: #58a6ff;
        }
        .file-upload.has-file {
            border-color: #238636;
            background: #1a3d2a;
        }
        #imagePreview {
            max-width: 100%;
            max-height: 300px;
            margin-top: 15px;
            border-radius: 6px;
            display: none;
        }
        #status {
            margin-top: 20px;
            padding: 15px;
            border-radius: 6px;
            display: none;
        }
        #status.success {
            background: #1a3d2a;
            border: 1px solid #238636;
            color: #3fb950;
            display: block;
        }
        #status.error {
            background: #3d1a1a;
            border: 1px solid #f85149;
            color: #f85149;
            display: block;
        }
        #status.progress {
            background: #1c2a3d;
            border: 1px solid #58a6ff;
            color: #58a6ff;
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 Generate Video (I2V)</h1>

        <div class="nav">
            <a href="/">← Home</a>
            <a href="/browse">Browse Results</a>
            <a href="/jobs">Job Queue</a>
            <a href="/generate/image">Generate Image</a>
        </div>

        <div class="info">
            <strong>Note:</strong> Video generation requires a source image. Upload an image and add a prompt describing the motion/animation you want.
        </div>

        <form id="videoForm" onsubmit="submitVideoJob(event)">
            <div class="form-group">
                <label for="sourceRunId">Source Run ID (from Browse)</label>
                <input type="text" id="sourceRunId" name="source_run_id" placeholder="20251229-024410-e51939f0" onchange="loadSourcePreview()" onblur="loadSourcePreview()">
                <small style="color: #8b949e; display: block; margin-top: 4px;">
                    Paste a run ID to use an image from Browse, or upload a file below
                </small>
            </div>

            <div class="form-group">
                <label>Or Upload Image</label>
                <div class="file-upload" onclick="document.getElementById('imageFile').click()">
                    <input type="file" id="imageFile" name="image" accept="image/*" style="display: none;" onchange="previewImage(event)">
                    <div id="uploadText">Click to upload or drag and drop<br><small>PNG, JPG, or WebP</small></div>
                    <img id="imagePreview" alt="Preview">
                </div>
            </div>

            <div class="form-group">
                <label for="prompt">Motion Prompt *</label>
                <textarea
                    id="prompt"
                    name="prompt"
                    required
                    placeholder="gentle breathing, slight movement, camera slowly zooming in"
                ></textarea>
            </div>

            <div class="form-group">
                <label for="worker">Worker *</label>
                <select id="worker" name="worker" required>
                    <option value="local" selected>Local Worker (localhost:8001)</option>
                    <option value="remote">Remote Worker (localhost:8002)</option>
                </select>
            </div>

            <div class="form-group">
                <label>Quick Presets (click to populate form)</label>
                <div class="preset-grid">
                    <button type="button" class="preset-btn" onclick="applyVideoPreset('draft')">
                        <span class="preset-name">Draft</span>
                        <span class="preset-desc">3s, 12fps, 15 steps</span>
                    </button>
                    <button type="button" class="preset-btn" onclick="applyVideoPreset('final')">
                        <span class="preset-name">Final</span>
                        <span class="preset-desc">5s, 16fps, 30 steps</span>
                    </button>
                    <button type="button" class="preset-btn" onclick="applyVideoPreset('hq')">
                        <span class="preset-name">HQ</span>
                        <span class="preset-desc">7s, 24fps, 50 steps</span>
                    </button>
                </div>
            </div>

            <div class="form-group">
                <label for="seed">Seed</label>
                <input type="number" id="vseed" name="seed" value="42" min="0" max="999999">
            </div>

            <div class="form-group">
                <label for="duration">Duration (seconds) *</label>
                <input type="number" id="duration" name="duration_seconds" value="3" min="1" max="30" step="1" required>
            </div>

            <div class="form-group">
                <label for="fps">FPS (frames per second) *</label>
                <input type="number" id="fps" name="fps" value="12" min="8" max="30" required>
            </div>

            <div class="form-group">
                <label for="vsteps">Steps *</label>
                <input type="number" id="vsteps" name="steps" value="15" min="1" max="100" required>
            </div>

            <div class="form-group">
                <label for="vguidance">Guidance Scale *</label>
                <input type="number" id="vguidance" name="guidance" value="3.0" min="0" max="20" step="0.1" required>
            </div>

            <button type="submit">Generate Video</button>
        </form>

        <div id="status"></div>
    </div>

    <script>
        // Video presets (populate form fields)
        const VIDEO_PRESETS = {
            draft: { duration: 3, fps: 12, steps: 15, guidance: 3.0 },
            final: { duration: 5, fps: 16, steps: 30, guidance: 3.5 },
            hq: { duration: 7, fps: 24, steps: 50, guidance: 4.0 },
        };

        function applyVideoPreset(name) {
            const preset = VIDEO_PRESETS[name];
            if (!preset) return;

            document.getElementById('duration').value = preset.duration;
            document.getElementById('fps').value = preset.fps;
            document.getElementById('vsteps').value = preset.steps;
            document.getElementById('vguidance').value = preset.guidance;
        }

        // Load form from query parameters (for "Generate Video" from Browse)
        function loadFromQueryParams() {
            const params = new URLSearchParams(window.location.search);

            if (params.has('source')) {
                const sourceRunId = params.get('source');
                document.getElementById('sourceRunId').value = sourceRunId;
                loadSourcePreview();
            }

            // Clear query params from URL after loading
            if (params.toString()) {
                window.history.replaceState({}, '', '/generate/video');
            }
        }

        // Load on page load
        loadFromQueryParams();

        // Load and preview image from run ID
        async function loadSourcePreview() {
            const runId = document.getElementById('sourceRunId').value.trim();
            if (!runId) return;

            const preview = document.getElementById('imagePreview');
            const uploadText = document.getElementById('uploadText');
            const fileUpload = document.querySelector('.file-upload');

            try {
                // Try to load the image from the run ID using browse API endpoint
                const response = await fetch(`/api/runs/${runId}/image`);
                if (response.ok) {
                    const blob = await response.blob();
                    preview.src = URL.createObjectURL(blob);
                    preview.style.display = 'block';
                    uploadText.style.display = 'none';
                    fileUpload.classList.add('has-file');
                } else {
                    // Run not found - show error in preview area
                    uploadText.innerHTML = `<span style="color: #f85149;">Run ID not found: ${runId}</span><br><small>Try browsing for a valid run</small>`;
                    uploadText.style.display = 'block';
                    preview.style.display = 'none';
                    fileUpload.classList.remove('has-file');
                }
            } catch (e) {
                console.warn('Error loading source image:', e);
                uploadText.innerHTML = `<span style="color: #f85149;">Error loading image</span><br><small>${e.message}</small>`;
                uploadText.style.display = 'block';
                preview.style.display = 'none';
                fileUpload.classList.remove('has-file');
            }
        }

        function previewImage(event) {
            const file = event.target.files[0];
            if (file) {
                // Clear run ID when uploading a file
                document.getElementById('sourceRunId').value = '';

                const reader = new FileReader();
                reader.onload = function(e) {
                    const preview = document.getElementById('imagePreview');
                    preview.src = e.target.result;
                    preview.style.display = 'block';
                    document.getElementById('uploadText').style.display = 'none';
                    document.querySelector('.file-upload').classList.add('has-file');
                };
                reader.readAsDataURL(file);
            }
        }

        async function submitVideoJob(event) {
            event.preventDefault();

            const form = document.getElementById('videoForm');
            const formData = new FormData(form);
            const statusDiv = document.getElementById('status');
            const sourceRunId = document.getElementById('sourceRunId').value.trim();
            const imageFile = document.getElementById('imageFile').files[0];

            // Validate that we have either a run ID or a file
            if (!sourceRunId && !imageFile) {
                statusDiv.className = 'error';
                statusDiv.textContent = '✗ Error: Please provide either a source run ID or upload an image';
                return;
            }

            // Show submitting status
            statusDiv.className = 'progress';
            if (sourceRunId) {
                statusDiv.textContent = 'Submitting job to worker with run ID...';
            } else {
                statusDiv.textContent = 'Uploading image and submitting job to worker...';
            }

            try {
                const response = await fetch('/api/jobs/video', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (!response.ok) {
                    throw new Error(result.detail || 'Submission failed');
                }

                // Show success with job ID
                statusDiv.className = 'progress';
                statusDiv.innerHTML = `
                    <strong>✓ Job submitted!</strong><br>
                    Job ID: ${result.job_id}<br>
                    Worker: ${result.worker}<br>
                    <br>
                    Monitoring progress... (polling every 2 seconds)<br>
                    <small>Video generation takes longer than images (several minutes)</small><br>
                    <span id="progressStatus">Waiting...</span>
                `;

                // Start polling for progress
                pollJobStatus(result.job_id);

            } catch (error) {
                statusDiv.className = 'error';
                statusDiv.textContent = '✗ Error: ' + error.message;
            }
        }

        async function pollJobStatus(jobId) {
            const statusSpan = document.getElementById('progressStatus');
            const statusDiv = document.getElementById('status');

            const poll = async () => {
                try {
                    const response = await fetch(`/api/jobs/${jobId}`);
                    const job = await response.json();

                    const percent = Math.round(job.progress.progress * 100);
                    const step = job.progress.step;
                    const total = job.progress.total_steps;

                    if (job.status === 'complete') {
                        statusDiv.className = 'success';
                        statusDiv.innerHTML = `
                            <strong>✓ Video generation complete!</strong><br>
                            Job ID: ${jobId}<br>
                            Run ID: ${job.results.local_run_id}<br>
                            <br>
                            <a href="/browse" style="color: #3fb950; font-weight: 600;">→ View in Browse</a>
                        `;
                        return;
                    } else if (job.status === 'failed') {
                        statusDiv.className = 'error';
                        statusDiv.textContent = '✗ Generation failed: ' + (job.error || 'Unknown error');
                        return;
                    }

                    // Update progress
                    statusSpan.textContent = `${job.status} - ${percent}% (step ${step}/${total})`;

                    // Continue polling
                    setTimeout(poll, 2000);

                } catch (error) {
                    statusDiv.className = 'error';
                    statusDiv.textContent = '✗ Error checking status: ' + error.message;
                }
            };

            poll();
        }
    </script>
</body>
</html>
"""


@router.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request):
    """Job queue monitoring page."""
    return templates.TemplateResponse("jobs.html", {"request": request})


# Legacy inline HTML job page (keeping for reference, can be deleted later)
def _jobs_page_old() -> str:
    """OLD: Job queue monitoring page with inline HTML."""
    return r"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Job Queue - MyDiffuser Client</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0d1117;
            color: #e6edf3;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 {
            font-size: 2em;
            margin-bottom: 0.5em;
            color: #58a6ff;
        }
        .nav {
            margin-bottom: 2em;
            padding-bottom: 1em;
            border-bottom: 1px solid #30363d;
        }
        .nav a {
            color: #58a6ff;
            text-decoration: none;
            margin-right: 1em;
        }
        .nav a:hover {
            text-decoration: underline;
        }
        .info {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 1.5em;
            font-size: 14px;
            color: #8b949e;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: #161b22;
            border-radius: 6px;
            overflow: hidden;
        }
        th {
            background: #21262d;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #8b949e;
            border-bottom: 1px solid #30363d;
        }
        td {
            padding: 12px;
            border-bottom: 1px solid #30363d;
        }
        tr:last-child td {
            border-bottom: none;
        }
        tr:hover {
            background: #1c2128;
        }
        .status-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        .status-queued {
            background: #1a3d5c;
            color: #58a6ff;
        }
        .status-submitted, .status-processing {
            background: #3d2a1a;
            color: #f2cc60;
        }
        .status-complete {
            background: #1a3d2a;
            color: #3fb950;
        }
        .status-failed, .status-error {
            background: #4c1d1d;
            color: #f85149;
        }
        .progress-bar {
            width: 100%;
            height: 20px;
            background: #21262d;
            border-radius: 4px;
            overflow: hidden;
            position: relative;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #238636 0%, #2ea043 100%);
            transition: width 0.3s ease;
        }
        .progress-text {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 11px;
            font-weight: 600;
            color: #e6edf3;
            text-shadow: 0 1px 2px rgba(0,0,0,0.5);
        }
        .prompt {
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 12px;
            color: #8b949e;
            max-width: 300px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .worker-badge {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: 600;
            background: #21262d;
            color: #8b949e;
        }
        .worker-offline {
            opacity: 0.5;
        }
        .worker-status {
            font-size: 12px;
            color: #8b949e;
            margin-top: 5px;
        }
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #8b949e;
        }
        .empty-state svg {
            width: 64px;
            height: 64px;
            margin-bottom: 16px;
            opacity: 0.5;
        }
        a {
            color: #58a6ff;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        .refresh-info {
            font-size: 12px;
            color: #8b949e;
            margin-bottom: 1em;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Job Queue</h1>

        <div class="nav">
            <a href="/">← Home</a>
            <a href="/browse">Browse Results</a>
            <a href="/generate/image">Generate Image</a>
            <a href="/generate/video">Generate Video</a>
        </div>

        <div class="info">
            Monitor all submitted jobs across all workers. Page auto-refreshes every 5 seconds.
        </div>

        <div class="refresh-info" id="refreshInfo">Loading jobs...</div>

        <div id="jobsContainer">
            <div class="empty-state">
                <svg viewBox="0 0 16 16" fill="currentColor">
                    <path d="M8 1.5c-2.363 0-4 1.69-4 3.75 0 .984.424 1.625.984 2.304l.214.253c.223.264.47.556.673.848.284.411.537.896.621 1.49a.75.75 0 0 1-1.484.211c-.04-.282-.163-.547-.37-.847a8.456 8.456 0 0 0-.542-.68c-.084-.1-.173-.205-.268-.32C3.201 7.75 2.5 6.766 2.5 5.25 2.5 2.31 4.863 0 8 0s5.5 2.31 5.5 5.25c0 1.516-.701 2.5-1.328 3.259-.095.115-.184.22-.268.319-.207.245-.383.453-.541.681-.208.3-.33.565-.37.847a.751.751 0 0 1-1.485-.212c.084-.593.337-1.078.621-1.489.203-.292.45-.584.673-.848.075-.088.147-.173.213-.253.561-.679.985-1.32.985-2.304 0-2.06-1.637-3.75-4-3.75ZM5.75 12h4.5a.75.75 0 0 1 0 1.5h-4.5a.75.75 0 0 1 0-1.5ZM6 15.25a.75.75 0 0 1 .75-.75h2.5a.75.75 0 0 1 0 1.5h-2.5a.75.75 0 0 1-.75-.75Z"/>
                </svg>
                <p>No jobs yet. Start by generating an image or video!</p>
            </div>
        </div>
    </div>

    <script>
        let lastRefresh = Date.now();

        async function loadJobs() {
            try {
                const response = await fetch('/api/jobs');
                const data = await response.json();

                lastRefresh = Date.now();
                updateRefreshInfo();

                if (!data.jobs || data.jobs.length === 0) {
                    document.getElementById('jobsContainer').innerHTML = \`
                        <div class="empty-state">
                            <svg viewBox="0 0 16 16" fill="currentColor">
                                <path d="M8 1.5c-2.363 0-4 1.69-4 3.75 0 .984.424 1.625.984 2.304l.214.253c.223.264.47.556.673.848.284.411.537.896.621 1.49a.75.75 0 0 1-1.484.211c-.04-.282-.163-.547-.37-.847a8.456 8.456 0 0 0-.542-.68c-.084-.1-.173-.205-.268-.32C3.201 7.75 2.5 6.766 2.5 5.25 2.5 2.31 4.863 0 8 0s5.5 2.31 5.5 5.25c0 1.516-.701 2.5-1.328 3.259-.095.115-.184.22-.268.319-.207.245-.383.453-.541.681-.208.3-.33.565-.37.847a.751.751 0 0 1-1.485-.212c.084-.593.337-1.078.621-1.489.203-.292.45-.584.673-.848.075-.088.147-.173.213-.253.561-.679.985-1.32.985-2.304 0-2.06-1.637-3.75-4-3.75ZM5.75 12h4.5a.75.75 0 0 1 0 1.5h-4.5a.75.75 0 0 1 0-1.5ZM6 15.25a.75.75 0 0 1 .75-.75h2.5a.75.75 0 0 1 0 1.5h-2.5a.75.75 0 0 1-.75-.75Z"/>
                            </svg>
                            <p>No jobs yet. Start by generating an image or video!</p>
                        </div>
                    \`;
                    return;
                }

                // Sort jobs by created_at (newest first)
                data.jobs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

                let tableHTML = \`
                    <table>
                        <thead>
                            <tr>
                                <th style="width: 80px;">Type</th>
                                <th style="width: 100px;">Worker</th>
                                <th style="width: 120px;">Status</th>
                                <th>Prompt</th>
                                <th style="width: 200px;">Progress</th>
                                <th style="width: 180px;">Created</th>
                                <th style="width: 100px;">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                \`;

                for (const job of data.jobs) {
                    const statusClass = \`status-\${job.status.toLowerCase()}\`;
                    const progress = Math.round(job.progress * 100);
                    const createdDate = new Date(job.created_at);
                    const timeAgo = getTimeAgo(createdDate);

                    let actionsHTML = '';
                    if (job.status === 'complete' && job.local_run_id) {
                        actionsHTML = \`<a href="/browse">View</a>\`;
                    } else if (job.status === 'failed' && job.error) {
                        actionsHTML = \`<span style="color: #f85149; font-size: 12px;" title="\${escapeHtml(job.error)}">Error</span>\`;
                    }

                    tableHTML += \`
                        <tr>
                            <td><span class="worker-badge">\${job.type}</span></td>
                            <td><span class="worker-badge">\${job.worker}</span></td>
                            <td><span class="status-badge \${statusClass}">\${job.status}</span></td>
                            <td><div class="prompt" title="\${escapeHtml(job.prompt)}">\${escapeHtml(job.prompt)}</div></td>
                            <td>
                                <div class="progress-bar">
                                    <div class="progress-fill" style="width: \${progress}%"></div>
                                    <div class="progress-text">\${job.step} · \${progress}%</div>
                                </div>
                            </td>
                            <td style="font-size: 12px; color: #8b949e;">\${timeAgo}</td>
                            <td>\${actionsHTML}</td>
                        </tr>
                    \`;
                }

                tableHTML += '</tbody></table>';
                document.getElementById('jobsContainer').innerHTML = tableHTML;

            } catch (error) {
                console.error('Error loading jobs:', error);
                document.getElementById('jobsContainer').innerHTML = \`
                    <div class="empty-state">
                        <p style="color: #f85149;">Error loading jobs: \${error.message}</p>
                        <p style="margin-top: 10px;">Retrying in 5 seconds...</p>
                    </div>
                \`;
            }
        }

        function updateRefreshInfo() {
            const elapsed = Math.round((Date.now() - lastRefresh) / 1000);
            const nextRefresh = Math.max(0, 5 - elapsed);
            document.getElementById('refreshInfo').textContent = \`Last refresh: \${elapsed}s ago · Next refresh: \${nextRefresh}s\`;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function getTimeAgo(date) {
            const seconds = Math.floor((Date.now() - date) / 1000);
            if (seconds < 60) return \`\${seconds}s ago\`;
            const minutes = Math.floor(seconds / 60);
            if (minutes < 60) return \`\${minutes}m ago\`;
            const hours = Math.floor(minutes / 60);
            if (hours < 24) return \`\${hours}h ago\`;
            const days = Math.floor(hours / 24);
            return \`\${days}d ago\`;
        }

        // Initial load
        loadJobs();

        // Auto-refresh every 5 seconds
        setInterval(loadJobs, 5000);

        // Update refresh info every second
        setInterval(updateRefreshInfo, 1000);
    </script>
</body>
</html>
"""
