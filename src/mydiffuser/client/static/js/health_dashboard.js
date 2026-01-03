// Worker health dashboard real-time monitoring
let lastRefresh = Date.now();
let refreshInterval = null;

// Load workers and health data
async function loadHealthData() {
    try {
        // Fetch list of configured workers
        const workersResponse = await fetch('/api/workers');
        const workersData = await workersResponse.json();

        lastRefresh = Date.now();
        updateRefreshInfo();

        if (!workersData.workers || Object.keys(workersData.workers).length === 0) {
            document.getElementById('workersContainer').innerHTML = `
                <div class="error-state">
                    <p>No workers configured</p>
                    <p class="error-details">Check your worker configuration in client/config.py</p>
                </div>
            `;
            return;
        }

        // Fetch health for each worker (via proxy to avoid CORS)
        const healthPromises = workersData.workers.map(async (worker) => {
            try {
                const response = await fetch(`/api/workers/${worker.id}/health`, {
                    signal: AbortSignal.timeout(5000)  // 5 second timeout
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const health = await response.json();
                return { name: worker.name, config: worker, health, online: true, error: null };
            } catch (error) {
                return {
                    name: worker.name,
                    config: worker,
                    health: null,
                    online: false,
                    error: error.message
                };
            }
        });

        const results = await Promise.all(healthPromises);

        // Render worker cards
        renderWorkerCards(results);

    } catch (error) {
        console.error('Error loading health data:', error);
        document.getElementById('workersContainer').innerHTML = `
            <div class="error-state">
                <p>Error loading health data</p>
                <p class="error-details">${escapeHtml(error.message)}</p>
                <p style="margin-top: 10px; color: #8b949e;">Retrying in 3 seconds...</p>
            </div>
        `;
    }
}

function renderWorkerCards(workers) {
    const container = document.getElementById('workersContainer');

    let html = '';

    for (const worker of workers) {
        const statusClass = worker.online ? 'online' : 'offline';
        const statusLabel = worker.online ? 'ONLINE' : 'OFFLINE';

        html += `
            <div class="worker-card ${statusClass}">
                <div class="worker-header">
                    <div class="worker-name">
                        <span class="status-indicator ${statusClass}"></span>
                        ${escapeHtml(worker.name)}
                    </div>
                    <span class="status-label ${statusClass}">${statusLabel}</span>
                </div>
        `;

        if (worker.online && worker.health) {
            const h = worker.health;

            // GPU Information
            html += `<div class="worker-section">
                <div class="section-title">GPU Status</div>`;

            if (h.gpu_available) {
                const memUsed = h.gpu_memory_used_gb || 0;
                const memTotal = h.gpu_memory_total_gb || 0;
                const memFree = h.gpu_memory_free_gb || 0;
                const memPercent = memTotal > 0 ? Math.round((memUsed / memTotal) * 100) : 0;

                html += `
                    <div class="metric-row">
                        <span class="metric-label">Device</span>
                        <span class="metric-value">${escapeHtml(h.gpu_name || 'Unknown')}</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Architecture</span>
                        <span class="metric-value">${escapeHtml(h.gpu_arch || 'unknown')}</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Memory</span>
                        <span class="metric-value">${memUsed.toFixed(1)} / ${memTotal.toFixed(1)} GB</span>
                    </div>
                    <div class="gpu-memory-bar">
                        <div class="gpu-memory-fill" style="width: ${memPercent}%"></div>
                        <div class="gpu-memory-text">${memPercent}% used (${memFree.toFixed(1)} GB free)</div>
                    </div>
                `;
            } else {
                html += `
                    <div class="metric-row">
                        <span class="metric-value" style="color: #f85149;">No GPU available</span>
                    </div>
                `;
            }

            html += `</div>`;

            // Queue Status
            const queuedJobs = h.queued_jobs || 0;
            const runningJob = h.running_job;

            html += `
                <div class="worker-section">
                    <div class="section-title">Queue Status</div>
                    <div style="margin-top: 8px;">
                        <span class="queue-badge queued">${queuedJobs} queued</span>
                        ${runningJob ? `<span class="queue-badge running">1 running</span>` : '<span style="color: #8b949e; font-size: 13px;">Idle</span>'}
                    </div>
                    ${runningJob ? `<div class="metric-row" style="margin-top: 8px;">
                        <span class="metric-label">Running Job</span>
                        <span class="metric-value" style="font-size: 11px; color: #f2cc60;">${escapeHtml(runningJob)}</span>
                    </div>` : ''}
                </div>
            `;

            // Active Model
            html += `
                <div class="worker-section">
                    <div class="section-title">
                        Active Model
                        <span class="info-icon" title="The model that was most recently used or loaded. Only one model can be active at a time.">ⓘ</span>
                    </div>
            `;

            if (h.active_model) {
                html += `<div class="active-model-badge">${escapeHtml(h.active_model)}</div>`;
            } else {
                html += `<div style="color: #8b949e; font-size: 13px; margin-top: 6px;">No model loaded (lazy loading)</div>`;
            }

            html += `</div>`;

            // Models Loaded (memory status)
            if (h.models_loaded) {
                const hasRunningJob = h.running_job !== null;

                html += `
                    <div class="worker-section">
                        <div class="section-title">
                            Models in Memory
                            <span class="info-icon" title="All models currently loaded in GPU memory. Multiple models can coexist (e.g., image + assistant = 34GB). Use 'Unload' to free GPU memory.">ⓘ</span>
                        </div>
                        <div class="capabilities-list">
                `;

                if (h.models_loaded.image) {
                    html += `
                        <span class="capability-tag model-badge">
                            Image
                            <button class="unload-btn"
                                    onclick="unloadModel('${worker.config.id}', 'image')"
                                    ${hasRunningJob ? 'disabled' : ''}>
                                Unload
                            </button>
                        </span>`;
                }
                if (h.models_loaded.video) {
                    html += `
                        <span class="capability-tag video model-badge">
                            Video
                            <button class="unload-btn"
                                    onclick="unloadModel('${worker.config.id}', 'video')"
                                    ${hasRunningJob ? 'disabled' : ''}>
                                Unload
                            </button>
                        </span>`;
                }
                if (h.models_loaded.assistant) {
                    html += `
                        <span class="capability-tag assist model-badge">
                            Assistant
                            <button class="unload-btn"
                                    onclick="unloadModel('${worker.config.id}', 'assistant')"
                                    ${hasRunningJob ? 'disabled' : ''}>
                                Unload
                            </button>
                        </span>`;
                }

                const loadedCount = Object.values(h.models_loaded).filter(Boolean).length;
                if (loadedCount === 0) {
                    html += `<span style="color: #8b949e; font-size: 13px;">No models loaded</span>`;
                } else if (hasRunningJob) {
                    html += `<div style="color: #f2cc60; font-size: 11px; margin-top: 8px;">
                        ⚠ Models locked while job is running
                    </div>`;
                }

                html += `
                        </div>
                    </div>
                `;
            }

            // Capabilities
            html += `
                <div class="worker-section">
                    <div class="section-title">Capabilities</div>
                    <div class="capabilities-list">
            `;

            if (h.capabilities && h.capabilities.length > 0) {
                for (const cap of h.capabilities) {
                    const capClass = cap === 'video' ? 'video' : (cap === 'assist' ? 'assist' : '');
                    html += `<span class="capability-tag ${capClass}">${escapeHtml(cap)}</span>`;
                }
            }

            if (h.video_models && h.video_models.length > 0) {
                html += `<span class="capability-tag video">Models: ${h.video_models.join(', ')}</span>`;
            }

            html += `
                    </div>
                </div>
            `;

            // VRAM Prediction
            if (h.vram_prediction) {
                html += `
                    <div class="worker-section">
                        <div class="section-title">
                            VRAM Predictions
                            <span class="info-icon" title="Estimated VRAM usage for different generation tasks. These are approximate values based on model parameters.">ⓘ</span>
                        </div>
                        <div style="margin-top: 8px;">
                            <div class="metric-row">
                                <span class="metric-label">Image (720p)</span>
                                <span class="metric-value">~${escapeHtml((h.vram_prediction.model_sizes?.image?.['z-image-turbo'] || 9.2).toFixed(1))} GB</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Video (5B, 5s)</span>
                                <span class="metric-value">~${escapeHtml((h.vram_prediction.model_sizes?.video?.['wan-2.1-5b'] || 8.5).toFixed(1))} GB</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Video (14B, 5s)</span>
                                <span class="metric-value">~${escapeHtml((h.vram_prediction.model_sizes?.video?.['wan-2.1-14b'] || 18.2).toFixed(1))} GB</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Assistant (7B)</span>
                                <span class="metric-value">~${escapeHtml((h.vram_prediction.model_sizes?.assistant?.['qwen2-vl-7b'] || 23.8).toFixed(1))} GB</span>
                            </div>
                        </div>
                    </div>
                `;
            }

            // Platform Info
            html += `
                <div class="worker-section">
                    <div class="metric-row">
                        <span class="metric-label">Platform</span>
                        <span class="metric-value">${escapeHtml(h.platform || 'unknown')}</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Device</span>
                        <span class="metric-value">${escapeHtml(h.device || 'unknown')}</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Endpoint</span>
                        <span class="metric-value" style="font-size: 11px;">${escapeHtml(worker.config.endpoint)}</span>
                    </div>
                </div>
            `;

        } else {
            // Worker offline
            html += `
                <div class="worker-section">
                    <div class="error-details">
                        <strong>Connection Error:</strong><br>
                        ${escapeHtml(worker.error || 'Unknown error')}
                    </div>
                    <div class="metric-row" style="margin-top: 12px;">
                        <span class="metric-label">Endpoint</span>
                        <span class="metric-value" style="font-size: 11px;">${escapeHtml(worker.config.endpoint)}</span>
                    </div>
                </div>
            `;
        }

        html += `</div>`;  // Close worker-card
    }

    container.innerHTML = html;
}

function updateRefreshInfo() {
    const elapsed = Math.round((Date.now() - lastRefresh) / 1000);
    const nextRefresh = Math.max(0, 3 - elapsed);
    document.getElementById('refreshInfo').textContent = `Last refresh: ${elapsed}s ago · Next: ${nextRefresh}s`;
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// Initial load
loadHealthData();

// Auto-refresh every 3 seconds
refreshInterval = setInterval(loadHealthData, 3000);

// Update refresh info every second
setInterval(updateRefreshInfo, 1000);

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
});

// Backfill function
async function triggerBackfill() {
    const btn = document.getElementById('backfillBtn');
    const statusDiv = document.getElementById('backfillStatus');
    const progressDiv = document.getElementById('backfillProgress');

    if (!confirm('Run database backfill?\n\nThis will read all meta.json files and populate missing parameters in the database. This may take a minute.')) {
        return;
    }

    // Disable button and show status
    btn.disabled = true;
    btn.textContent = 'Running...';
    statusDiv.style.display = 'block';
    progressDiv.innerHTML = '<p>Starting backfill...</p>';

    try {
        // Trigger backfill
        const formData = new FormData();
        formData.append('force_refresh', 'false');

        const response = await fetch('/api/admin/backfill', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const result = await response.json();
        progressDiv.innerHTML = '<p>Backfill started. Checking status...</p>';

        // Poll for status
        let attempts = 0;
        const maxAttempts = 60;  // 60 seconds max
        const pollInterval = setInterval(async () => {
            attempts++;

            try {
                const statusResponse = await fetch('/api/admin/backfill/status');
                const statusData = await statusResponse.json();

                if (!statusData.running && statusData.stats) {
                    // Backfill complete
                    clearInterval(pollInterval);

                    const stats = statusData.stats;
                    const successClass = stats.errors === 0 ? 'backfill-success' : '';

                    progressDiv.innerHTML = `
                        <p class="${successClass}">✓ Backfill complete!</p>
                        <p style="margin-top: 10px;">
                            • Total runs: ${stats.total}<br>
                            • Updated: ${stats.updated}<br>
                            • Errors: ${stats.errors}
                        </p>
                        ${stats.errors > 0 ? `
                            <details style="margin-top: 10px;">
                                <summary style="cursor: pointer; color: #f85149;">Show errors</summary>
                                <div style="margin-top: 8px; font-size: 11px;">
                                    ${stats.error_details.slice(0, 10).map(e => `• ${escapeHtml(e)}`).join('<br>')}
                                    ${stats.error_details.length > 10 ? `<br>• ...and ${stats.error_details.length - 10} more` : ''}
                                </div>
                            </details>
                        ` : ''}
                    `;

                    btn.disabled = false;
                    btn.textContent = 'Run Backfill';

                } else if (attempts >= maxAttempts) {
                    // Timeout
                    clearInterval(pollInterval);
                    progressDiv.innerHTML = '<p class="backfill-error">⚠ Status check timed out. Backfill may still be running.</p>';
                    btn.disabled = false;
                    btn.textContent = 'Run Backfill';
                } else {
                    // Still running
                    progressDiv.innerHTML = `<p>Backfill in progress... (${attempts}s)</p>`;
                }

            } catch (error) {
                console.error('Status check error:', error);
            }
        }, 1000);

    } catch (error) {
        console.error('Backfill error:', error);
        progressDiv.innerHTML = `<p class="backfill-error">✗ Error: ${escapeHtml(error.message)}</p>`;
        btn.disabled = false;
        btn.textContent = 'Run Backfill';
    }
}

// Unload model function
async function unloadModel(workerId, modelType) {
    if (!confirm(`Unload ${modelType} model?\n\nThis will free GPU memory but the model will need to be reloaded for the next ${modelType} job.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/workers/${workerId}/unload/${modelType}`, {
            method: 'POST'
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Unload failed');
        }

        const result = await response.json();

        // Show success message
        alert(`✓ ${result.message}\n\nGPU Memory: ${result.gpu_memory?.free_gib || 'N/A'} GiB free / ${result.gpu_memory?.total_gib || 'N/A'} GiB total`);

        // Refresh health data to show updated state
        loadHealthData();

    } catch (error) {
        console.error('Unload error:', error);
        alert(`✗ Failed to unload ${modelType} model: ${error.message}`);
    }
}
