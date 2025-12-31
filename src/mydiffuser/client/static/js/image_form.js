// Aspect ratio dimensions
        const ASPECT_RATIOS = {
            landscape: { width: 832, height: 480 },   // 16:9 480p
            portrait: { width: 480, height: 832 },    // 9:16 480p
            square: { width: 768, height: 768 },      // 1:1 square
        };

        // Image presets (populate form fields)
        const IMAGE_PRESETS = {
            draft: { height: 480, width: 832, steps: 4, guidance: 0.3 },
            fast: { height: 480, width: 832, steps: 6, guidance: 0.3 },
            balanced: { height: 704, width: 1280, steps: 8, guidance: 0.3 },
            quality: { height: 704, width: 1280, steps: 12, guidance: 0.3 },
            hq: { height: 1088, width: 1920, steps: 12, guidance: 0.3 },
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
            if (params.has('tags')) {
                const tags = JSON.parse(params.get('tags'));
                const commonTags = ['nsfw', 'portrait', 'landscape'];
                // Check common tag checkboxes
                tags.forEach(tag => {
                    const cb = document.querySelector(`input[value="${tag}"]`);
                    if (cb) cb.checked = true;
                });
                // Put remaining in custom tags field
                const customTags = tags.filter(t => !commonTags.includes(t));
                if (customTags.length) {
                    document.getElementById('customTags').value = customTags.join(', ');
                }
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
                        // Display image in output container
                        const outputContainer = document.getElementById('outputContainer');
                        if (job.results.local_run_id) {
                            const imageUrl = `/api/runs/${job.results.local_run_id}/image`;
                            outputContainer.innerHTML = `<img src="${imageUrl}" style="max-width: 100%; height: auto; border-radius: 6px;" alt="Generated image">`;
                        }

                        // Show success message
                        statusDiv.className = 'success';
                        statusDiv.innerHTML = `
                            <strong>✓ Generation complete!</strong><br>
                            Run ID: ${job.results.local_run_id}<br>
                            <a href="/browse?run=${job.results.local_run_id}" style="color: #3fb950; font-weight: 600;">→ View in Browse</a> |
                            <a href="/generate/video?source=${job.results.local_run_id}" style="color: #58a6ff; font-weight: 600;">→ Generate Video</a>
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
                        const etaSecs = Math.round(job.progress.eta_seconds);
                        if (etaSecs >= 60) {
                            const etaMins = Math.floor(etaSecs / 60);
                            progressText += ` - ETA: ${etaMins}m ${etaSecs % 60}s`;
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