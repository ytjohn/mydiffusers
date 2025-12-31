/**
 * Prompt Assistant Frontend Logic
 * Handles image uploads, form submission, and chat UI updates
 */

// File upload handling
const fileUploadArea = document.getElementById('fileUploadArea');
const imageFile = document.getElementById('imageFile');
const uploadPlaceholder = document.getElementById('uploadPlaceholder');
const imagePreview = document.getElementById('imagePreview');
const previewImg = document.getElementById('previewImg');
const fileName = document.getElementById('fileName');

// Click to select file
fileUploadArea.addEventListener('click', () => {
    imageFile.click();
});

// Handle file selection
imageFile.addEventListener('change', (e) => {
    handleFileSelect(e.target.files[0]);
});

// Drag and drop
fileUploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    fileUploadArea.classList.add('dragover');
});

fileUploadArea.addEventListener('dragleave', () => {
    fileUploadArea.classList.remove('dragover');
});

fileUploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    fileUploadArea.classList.remove('dragover');
    handleFileSelect(e.dataTransfer.files[0]);
});

function handleFileSelect(file) {
    if (!file) return;

    if (!file.type.match('image/(png|jpeg)')) {
        showError('Please select a PNG or JPG image');
        return;
    }

    if (file.size > 10 * 1024 * 1024) {
        showError('Image must be less than 10MB');
        return;
    }

    // Show preview
    const reader = new FileReader();
    reader.onload = (e) => {
        previewImg.src = e.target.result;
        fileName.textContent = file.name;
        uploadPlaceholder.style.display = 'none';
        imagePreview.style.display = 'block';
    };
    reader.readAsDataURL(file);
}

// Form submission
const analyzeForm = document.getElementById('analyzeForm');
const submitBtn = document.getElementById('submitBtn');

analyzeForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(analyzeForm);
    const sessionId = document.getElementById('sessionId').value;

    // Add session_id if exists
    if (sessionId) {
        formData.append('session_id', sessionId);
    }

    // Validate image is selected
    if (!imageFile.files[0]) {
        showError('Please select an image to analyze');
        return;
    }

    // Disable submit button
    submitBtn.disabled = true;
    submitBtn.textContent = '🔄 Analyzing...';

    try {
        const response = await fetch('/api/assist/analyze', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Analysis failed');
        }

        const result = await response.json();
        console.log('Analysis result:', result);

        // Show success and reload page to show new turn
        showSuccess('Analysis complete! Reloading conversation...');

        // Reload page with session_id to show updated conversation
        setTimeout(() => {
            window.location.href = `/assist?session_id=${result.session_id}`;
        }, 1000);

    } catch (error) {
        console.error('Analysis error:', error);
        showError(`Analysis failed: ${error.message}`);
        submitBtn.disabled = false;
        submitBtn.textContent = '🤖 Analyze & Get Suggestions';
    }
});

// Copy suggestion to clipboard
function copySuggestion(prompt) {
    navigator.clipboard.writeText(prompt).then(() => {
        showSuccess('Prompt copied to clipboard!');
    }).catch(err => {
        showError('Failed to copy to clipboard');
        console.error('Copy failed:', err);
    });
}

// Navigate to generate page with prompt pre-filled
function useSuggestion(prompt) {
    // Encode prompt for URL
    const encodedPrompt = encodeURIComponent(prompt);
    window.location.href = `/generate/image?prompt=${encodedPrompt}`;
}

// Resolve session
async function resolveSession() {
    const sessionId = document.getElementById('sessionId').value;
    if (!sessionId) {
        showError('No active session');
        return;
    }

    const finalPrompt = prompt('Enter the final improved prompt (the one that worked):');
    if (!finalPrompt) return;

    try {
        const formData = new FormData();
        formData.append('final_prompt', finalPrompt);

        const response = await fetch(`/api/assist/sessions/${sessionId}/resolve`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('Failed to resolve session');
        }

        showSuccess('Session marked as resolved!');
        setTimeout(() => {
            window.location.reload();
        }, 1000);

    } catch (error) {
        console.error('Resolve error:', error);
        showError(`Failed to resolve session: ${error.message}`);
    }
}

// Start new session
function startNewSession() {
    if (confirm('Start a new conversation? This will create a new session.')) {
        window.location.href = '/assist';
    }
}

// Status message helpers
function showError(message) {
    const statusDiv = document.getElementById('statusMessage');
    statusDiv.innerHTML = `<div class="error">${message}</div>`;
    setTimeout(() => {
        statusDiv.innerHTML = '';
    }, 5000);
}

function showSuccess(message) {
    const statusDiv = document.getElementById('statusMessage');
    statusDiv.innerHTML = `<div class="success">${message}</div>`;
    setTimeout(() => {
        statusDiv.innerHTML = '';
    }, 5000);
}
