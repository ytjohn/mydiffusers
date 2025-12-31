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
                    <div class="section-title">Active Model</div>
            `;

            if (h.active_model) {
                html += `<div class="active-model-badge">${escapeHtml(h.active_model)}</div>`;
            } else {
                html += `<div style="color: #8b949e; font-size: 13px; margin-top: 6px;">No model loaded (lazy loading)</div>`;
            }

            html += `</div>`;

            // Capabilities
            html += `
                <div class="worker-section">
                    <div class="section-title">Capabilities</div>
                    <div class="capabilities-list">
            `;

            if (h.capabilities && h.capabilities.length > 0) {
                for (const cap of h.capabilities) {
                    const capClass = cap === 'video' ? 'video' : '';
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
