// Resolution scales for aspect ratio toggle
        const RESOLUTION_SCALES = {
            '480p': { landscape: { width: 832, height: 480 }, portrait: { width: 480, height: 832 }, square: { width: 768, height: 768 } },
            '720p': { landscape: { width: 1280, height: 704 }, portrait: { width: 704, height: 1280 }, square: { width: 1024, height: 1024 } },
            '1080p': { landscape: { width: 1920, height: 1088 }, portrait: { width: 1088, height: 1920 }, square: { width: 1536, height: 1536 } },
        };

        // Image presets (reference resolution scales instead of fixed dimensions)
        const IMAGE_PRESETS = {
            draft: { scale: '480p', steps: 4, guidance: 0.3 },
            fast: { scale: '480p', steps: 6, guidance: 0.3 },
            balanced: { scale: '720p', steps: 8, guidance: 0.3 },
            quality: { scale: '720p', steps: 12, guidance: 0.3 },
            hq: { scale: '1080p', steps: 12, guidance: 0.3 },
        };

        function applyImagePreset(name) {
            const preset = IMAGE_PRESETS[name];
            if (!preset) return;

            // Get current aspect ratio selection
            const aspectRatio = document.getElementById('aspect_ratio').value;
            
            // Look up dimensions based on preset scale and current aspect ratio
            if (RESOLUTION_SCALES[preset.scale] && RESOLUTION_SCALES[preset.scale][aspectRatio]) {
                const dims = RESOLUTION_SCALES[preset.scale][aspectRatio];
                document.getElementById('height').value = dims.height;
                document.getElementById('width').value = dims.width;
            }
            
            // Apply other preset parameters
            document.getElementById('steps').value = preset.steps;
            document.getElementById('guidance').value = preset.guidance;
            
            // Trigger estimation update after applying preset
            updateEstimates();
        }

        // Detect current resolution scale based on dimensions
        function detectResolutionScale(width, height) {
            // Check against known resolutions
            if ((width === 832 && height === 480) || (width === 480 && height === 832) || (width === 768 && height === 768)) {
                return '480p';
            } else if ((width === 1280 && height === 704) || (width === 704 && height === 1280) || (width === 1024 && height === 1024)) {
                return '720p';
            } else if ((width === 1920 && height === 1088) || (width === 1088 && height === 1920) || (width === 1536 && height === 1536)) {
                return '1080p';
            }
            // Default to closest match or preserve custom
            return null;
        }

        // Update height/width when aspect ratio changes (preserve resolution scale)
        document.getElementById('aspect_ratio').addEventListener('change', (e) => {
            const currentWidth = parseInt(document.getElementById('width').value);
            const currentHeight = parseInt(document.getElementById('height').value);
            const newAspect = e.target.value;

            // Try to detect current resolution scale
            const scale = detectResolutionScale(currentWidth, currentHeight);

            if (scale && RESOLUTION_SCALES[scale] && RESOLUTION_SCALES[scale][newAspect]) {
                // Use the matching resolution scale
                const dims = RESOLUTION_SCALES[scale][newAspect];
                document.getElementById('height').value = dims.height;
                document.getElementById('width').value = dims.width;
            } else {
                // Custom dimensions - intelligently swap for portrait/landscape
                if (newAspect === 'portrait' && currentWidth >= currentHeight) {
                    // Swap to portrait
                    document.getElementById('height').value = currentWidth;
                    document.getElementById('width').value = currentHeight;
                } else if (newAspect === 'landscape' && currentHeight > currentWidth) {
                    // Swap to landscape
                    document.getElementById('height').value = currentWidth;
                    document.getElementById('width').value = currentHeight;
                } else if (newAspect === 'square') {
                    // Use average or smaller dimension for square
                    const dim = Math.min(currentWidth, currentHeight);
                    document.getElementById('height').value = dim;
                    document.getElementById('width').value = dim;
                }
                // Otherwise keep as-is (already in correct orientation)
            }
        });

        // Real-time VRAM and time estimation
        async function updateEstimates() {
            const width = parseInt(document.getElementById('width').value) || 512;
            const height = parseInt(document.getElementById('height').value) || 512;
            const steps = parseInt(document.getElementById('steps').value) || 20;
            const guidance = parseFloat(document.getElementById('guidance').value) || 0.0;
            
            try {
                const response = await fetch('/api/estimate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        type: 'image',
                        model_id: 'Tongyi-MAI/Z-Image-Turbo',
                        parameters: {
                            width: width,
                            height: height,
                            num_inference_steps: steps,
                            guidance_scale: guidance
                        },
                        worker_id: 'local'
                    })
                });

                const result = await response.json();
                const estimatesDiv = document.getElementById('estimates');
                const vramDiv = document.getElementById('estimate-vram');
                const timeDiv = document.getElementById('estimate-time');
                const warningDiv = document.getElementById('estimate-warning');
                
                const timeDisplay = result.time_estimate_seconds >= 60 
                    ? `${Math.floor(result.time_estimate_seconds / 60)}m ${result.time_estimate_seconds % 60}s`
                    : `${result.time_estimate_seconds}s`;
                
                vramDiv.innerHTML = `<strong>VRAM:</strong> ${result.vram_total_needed.toFixed(1)} GB`;
                timeDiv.innerHTML = `<strong>Time:</strong> ${timeDisplay}`;
                
                if (!result.worker_available) {
                    warningDiv.innerHTML = '⚠ <strong>Warning:</strong> Worker may not have enough VRAM';
                    warningDiv.style.display = 'block';
                    warningDiv.style.color = '#ff7b72';
                } else {
                    warningDiv.style.display = 'none';
                }
                
                estimatesDiv.style.display = 'block';
                
            } catch (error) {
                console.error('Error getting estimates:', error);
            }
        }

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
        
        // Add event listeners for real-time estimates
        ['width', 'height', 'steps', 'guidance'].forEach(id => {
            document.getElementById(id).addEventListener('input', updateEstimates);
        });
        
        // Initial estimate
        console.log('Setting up real-time estimates...');
        updateEstimates();

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