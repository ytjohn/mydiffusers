// Job queue page JavaScript
let lastRefresh = Date.now();

async function loadJobs() {
    try {
        const response = await fetch('/api/jobs');
        const data = await response.json();

        lastRefresh = Date.now();
        updateRefreshInfo();

        if (!data.jobs || data.jobs.length === 0) {
            document.getElementById('jobsContainer').innerHTML = `
                <div class="empty-state">
                    <svg viewBox="0 0 16 16" fill="currentColor">
                        <path d="M8 1.5c-2.363 0-4 1.69-4 3.75 0 .984.424 1.625.984 2.304l.214.253c.223.264.47.556.673.848.284.411.537.896.621 1.49a.75.75 0 0 1-1.484.211c-.04-.282-.163-.547-.37-.847a8.456 8.456 0 0 0-.542-.68c-.084-.1-.173-.205-.268-.32C3.201 7.75 2.5 6.766 2.5 5.25 2.5 2.31 4.863 0 8 0s5.5 2.31 5.5 5.25c0 1.516-.701 2.5-1.328 3.259-.095.115-.184.22-.268.319-.207.245-.383.453-.541.681-.208.3-.33.565-.37.847a.751.751 0 0 1-1.485-.212c.084-.593.337-1.078.621-1.489.203-.292.45-.584.673-.848.075-.088.147-.173.213-.253.561-.679.985-1.32.985-2.304 0-2.06-1.637-3.75-4-3.75ZM5.75 12h4.5a.75.75 0 0 1 0 1.5h-4.5a.75.75 0 0 1 0-1.5ZM6 15.25a.75.75 0 0 1 .75-.75h2.5a.75.75 0 0 1 0 1.5h-2.5a.75.75 0 0 1-.75-.75Z"/>
                    </svg>
                    <p>No jobs yet. Start by generating an image or video!</p>
                </div>
            `;
            return;
        }

        // Sort jobs by created_at (newest first)
        data.jobs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

        let tableHTML = `
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
        `;

        for (const job of data.jobs) {
            const statusClass = `status-${job.status.toLowerCase()}`;
            const progress = Math.round(job.progress * 100);
            const createdDate = new Date(job.created_at);
            const timeAgo = getTimeAgo(createdDate);

            let actionsHTML = '';
            if (job.status === 'complete' && job.local_run_id) {
                actionsHTML = `<a href="/browse?run=${job.local_run_id}">View</a>`;
            } else if (job.status === 'failed' && job.error) {
                actionsHTML = `<span style="color: #f85149; font-size: 12px;" title="${escapeHtml(job.error)}">Error</span>`;
            }

            tableHTML += `
                <tr>
                    <td><span class="worker-badge">${job.type}</span></td>
                    <td><span class="worker-badge">${job.worker}</span></td>
                    <td><span class="status-badge ${statusClass}">${job.status}</span></td>
                    <td><div class="prompt" title="${escapeHtml(job.prompt)}">${escapeHtml(job.prompt)}</div></td>
                    <td>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${progress}%"></div>
                            <div class="progress-text">
                                ${job.step} · ${progress}%
                                ${job.eta_seconds ? ` · ETA ${formatETA(job.eta_seconds)}` : ''}
                            </div>
                        </div>
                    </td>
                    <td style="font-size: 12px; color: #8b949e;">${timeAgo}</td>
                    <td>${actionsHTML}</td>
                </tr>
            `;
        }

        tableHTML += '</tbody></table>';
        document.getElementById('jobsContainer').innerHTML = tableHTML;

    } catch (error) {
        console.error('Error loading jobs:', error);
        document.getElementById('jobsContainer').innerHTML = `
            <div class="empty-state">
                <p style="color: #f85149;">Error loading jobs: ${error.message}</p>
                <p style="margin-top: 10px;">Retrying in 5 seconds...</p>
            </div>
        `;
    }
}

function updateRefreshInfo() {
    const elapsed = Math.round((Date.now() - lastRefresh) / 1000);
    const nextRefresh = Math.max(0, 5 - elapsed);
    document.getElementById('refreshInfo').textContent = `Last refresh: ${elapsed}s ago · Next refresh: ${nextRefresh}s`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getTimeAgo(date) {
    const seconds = Math.floor((Date.now() - date) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

function formatETA(seconds) {
    if (seconds < 60) {
        return `${Math.round(seconds)}s`;
    }
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins}m ${secs}s`;
}

// Initial load
loadJobs();

// Auto-refresh every 5 seconds
setInterval(loadJobs, 5000);

// Update refresh info every second
setInterval(updateRefreshInfo, 1000);
