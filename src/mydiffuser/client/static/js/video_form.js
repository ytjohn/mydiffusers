// Video presets (populate form fields)
        const VIDEO_PRESETS = {
            draft: { duration: 3, fps: 12, steps: 15, guidance: 3.0, resolution: "480p" },
            final: { duration: 5, fps: 16, steps: 30, guidance: 3.5, resolution: "720p" },
            hq: { duration: 7, fps: 24, steps: 50, guidance: 4.0, resolution: "720p" },
        };

        function applyVideoPreset(name) {
            const preset = VIDEO_PRESETS[name];
            if (!preset) return;

            document.getElementById('duration').value = preset.duration;
            document.getElementById('fps').value = preset.fps;
            document.getElementById('vsteps').value = preset.steps;
            document.getElementById('vguidance').value = preset.guidance;
            document.getElementById('resolution').value = preset.resolution;
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

        // Worker capabilities management
        async function updateWorkerCapabilities() {
            const workerSelect = document.getElementById('worker');
            const modelSelect = document.getElementById('modelSize');
            const modelInfo = document.getElementById('modelInfo');
            const selectedWorker = workerSelect.value;

            // Reset to loading state
            modelInfo.textContent = 'Loading worker capabilities...';
            modelInfo.style.color = '#8b949e';

            try {
                const response = await fetch(`/api/workers/${selectedWorker}/capabilities`);
                if (!response.ok) {
                    throw new Error(`Worker unreachable (${response.status})`);
                }

                const caps = await response.json();
                const availableModels = caps.video_models || [];

                // Update model dropdown based on capabilities
                const modelOptions = modelSelect.querySelectorAll('option');
                modelOptions.forEach(option => {
                    const value = option.value;
                    if (value === '') {
                        // "Worker Default" is always enabled
                        option.disabled = false;
                    } else if (availableModels.includes(value)) {
                        option.disabled = false;
                    } else {
                        option.disabled = true;
                        option.textContent = option.textContent.replace(' (unavailable)', '') + ' (unavailable)';
                    }
                });

                // Update info text
                if (availableModels.length === 0) {
                    modelInfo.textContent = 'No video models available on this worker';
                    modelInfo.style.color = '#f85149';
                } else {
                    const platform = caps.platform || 'unknown';
                    modelInfo.textContent = `Available models: ${availableModels.join(', ')} (${platform})`;
                    modelInfo.style.color = '#3fb950';
                }

                // If currently selected model is unavailable, reset to default
                if (modelSelect.value && !availableModels.includes(modelSelect.value)) {
                    modelSelect.value = '';
                }
            } catch (error) {
                console.error('Failed to fetch worker capabilities:', error);
                modelInfo.textContent = `Failed to query worker: ${error.message}`;
                modelInfo.style.color = '#f85149';
            }
        }

        // Update capabilities on worker change
        document.getElementById('worker').addEventListener('change', updateWorkerCapabilities);

        // Load capabilities on page load
        updateWorkerCapabilities();

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

            // Add source inputs to formData (they're outside the form element in the HTML)
            if (sourceRunId) {
                formData.append('source_run_id', sourceRunId);
            }
            if (imageFile) {
                // Append file with filename (important for FastAPI UploadFile)
                formData.append('image', imageFile, imageFile.name);
            }

            // Collect tags from checkboxes and custom text input
            const tags = [];
            document.querySelectorAll('input[type="checkbox"][name^="tag_"]').forEach(cb => {
                if (cb.checked) tags.push(cb.value);
            });
            const customTags = document.getElementById('customTags').value
                .split(',').map(t => t.trim().toLowerCase()).filter(t => t);
            tags.push(...customTags);
            formData.append('tags', JSON.stringify(tags));

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
                        // Display video in left panel
                        const videoPreviewContainer = document.getElementById('videoPreviewContainer');
                        const videoPreview = document.getElementById('videoPreview');
                        if (job.results.local_run_id) {
                            const videoUrl = `/api/runs/${job.results.local_run_id}/video`;
                            videoPreview.src = videoUrl;
                            videoPreviewContainer.style.display = 'block';
                        }

                        // Show success message
                        statusDiv.className = 'success';
                        statusDiv.innerHTML = `
                            <strong>✓ Video generation complete!</strong><br>
                            Run ID: ${job.results.local_run_id}<br>
                            <a href="/browse?run=${job.results.local_run_id}" style="color: #3fb950; font-weight: 600;">→ View in Browse</a>
                        `;
                        return;
                    } else if (job.status === 'failed') {
                        statusDiv.className = 'error';
                        statusDiv.textContent = '✗ Generation failed: ' + (job.error || 'Unknown error');
                        return;
                    }

                    // Update progress with ETA if available
                    let progressText = `${job.status} - ${percent}% (step ${step}/${total})`;

                    if (job.progress.eta_seconds !== null && job.progress.eta_seconds !== undefined) {
                        const etaMins = Math.floor(job.progress.eta_seconds / 60);
                        const etaSecs = Math.round(job.progress.eta_seconds % 60);
                        if (etaMins > 0) {
                            progressText += ` - ETA: ${etaMins}m ${etaSecs}s`;
                        } else {
                            progressText += ` - ETA: ${etaSecs}s`;
                        }

                        // Show seconds per iteration for context
                        if (job.progress.seconds_per_iteration) {
                            progressText += ` (${job.progress.seconds_per_iteration.toFixed(1)}s/it)`;
                        }
                    }

                    statusSpan.textContent = progressText;

                    // Continue polling
                    setTimeout(poll, 2000);

                } catch (error) {
                    statusDiv.className = 'error';
                    statusDiv.textContent = '✗ Error checking status: ' + error.message;
                }
            };

            poll();
        }