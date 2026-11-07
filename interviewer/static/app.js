/* ============================================================
   app.js — Frontend Controller for AI Mock Interviewer
   ============================================================
   Connects:
     • Backend Health Check : GET /api/health
     • Resume Upload & Parse: POST /resume/upload (multipart/form-data)
     • Stateful Chat & LLM  : POST /chat          (application/json)
     • Session History      : GET /api/session/{id}
   ============================================================ */

// ── Session State ─────────────────────────────────────────────
let currentConversationId = null;
let lastMessageId = null;
let isProcessing = false;

// ── API Base URL Resolution ───────────────────────────────────
/**
 * Resolves the backend base URL.
 * Defaults to port 8000 if opened through Live Server (5500), file protocol, or dev ports.
 */
function getApiBaseUrl() {
    if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {
        // If served directly by FastAPI on port 8000
        if (window.location.port === '8000') {
            return window.location.origin;
        }
    }
    // Default backend address
    return 'http://localhost:8000';
}

// ── Backend Health Check on Startup ───────────────────────────
async function checkBackendHealth() {
    const apiBase = getApiBaseUrl();
    try {
        const response = await fetch(`${apiBase}/api/health`, {
            method: 'GET',
            headers: { 'Accept': 'application/json' }
        });

        if (response.ok) {
            const data = await response.json();
            console.log(`[HealthCheck] Connected to backend at ${apiBase}:`, data);
            if (data.redis_connected) {
                updateConnectionStatus('Ready', true);
            } else {
                updateConnectionStatus('Redis Offline', false);
                showAlert('Redis is unreachable! Please start Redis on localhost:6379.', 'error');
            }
        } else {
            updateConnectionStatus('Degraded', false);
        }
    } catch (err) {
        console.warn(`[HealthCheck] Could not reach backend at ${apiBase}:`, err.message);
        updateConnectionStatus('Server Offline', false);
        showAlert(
            `Cannot connect to FastAPI backend at ${apiBase}. ` +
            `Ensure \`uvicorn app:app --reload\` is running in terminal.`,
            'error'
        );
    }
}

// ── Alert Banner Helpers ──────────────────────────────────────
function showAlert(message, type = 'error') {
    const alertBox = document.getElementById('alert-box');
    const alertMsg = document.getElementById('alert-message');
    if (!alertBox || !alertMsg) return;

    alertBox.className = `alert ${type}`;
    alertMsg.textContent = message;
    alertBox.style.display = 'flex';
}

function hideAlert() {
    const alertBox = document.getElementById('alert-box');
    if (alertBox) {
        alertBox.style.display = 'none';
    }
}

// ── Connection Status Pill ────────────────────────────────────
function updateConnectionStatus(text, isConnected) {
    const pill = document.getElementById('connection-pill');
    const label = document.getElementById('connection-text');
    if (label) {
        label.textContent = text;
    }
    if (pill) {
        if (isConnected) {
            pill.classList.add('connected');
        } else {
            pill.classList.remove('connected');
        }
    }
}

// ── File Selection & Drag-and-Drop ────────────────────────────
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function onFileSelected(input) {
    hideAlert();
    const fileInfo = document.getElementById('file-info');
    const fileInfoText = document.getElementById('file-info-text');

    if (input.files && input.files[0]) {
        const file = input.files[0];
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            showAlert('Only PDF files are supported. Please select a valid .pdf file.');
            input.value = '';
            if (fileInfo) fileInfo.style.display = 'none';
            return;
        }

        if (fileInfo && fileInfoText) {
            fileInfoText.textContent = `${file.name} (${formatBytes(file.size)})`;
            fileInfo.style.display = 'inline-flex';
        }
    } else {
        if (fileInfo) fileInfo.style.display = 'none';
    }
}

function clearSelectedFile() {
    const fileInput = document.getElementById('resume-file');
    const fileInfo = document.getElementById('file-info');
    if (fileInput) fileInput.value = '';
    if (fileInfo) fileInfo.style.display = 'none';
    hideAlert();
}

// ── Textarea Auto-resize ──────────────────────────────────────
function autoResizeTextarea(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 180) + 'px';
}

// ── Keyboard Shortcut (Enter to send, Shift+Enter for newline) ─
function handleInputKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

// ============================================================
// Step 1 — Upload Resume (POST /resume/upload)
// ============================================================
async function startInterviewSession() {
    hideAlert();
    const fileInput = document.getElementById('resume-file');
    const uploadBtn = document.getElementById('upload-btn');
    const uploadBtnText = document.getElementById('upload-btn-text');
    const apiBase = getApiBaseUrl();

    if (!fileInput.files || fileInput.files.length === 0) {
        showAlert('Please choose or drop a PDF resume file to start the assessment.');
        return;
    }

    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        showAlert('Only PDF files (.pdf) are supported. Please choose a valid PDF.');
        return;
    }

    // UI state: uploading & analyzing
    uploadBtn.disabled = true;
    uploadBtnText.innerHTML = '<span class="spinner"></span> Extracting & Analyzing Resume with Gemini...';
    updateConnectionStatus('Analyzing Resume...', false);

    // Build multipart/form-data payload
    const formData = new FormData();
    formData.append('file', file);

    console.log(`[Upload] Sending ${file.name} (${formatBytes(file.size)}) to ${apiBase}/resume/upload...`);

    try {
        const response = await fetch(`${apiBase}/resume/upload`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            let errDetail = 'Failed to process resume';
            try {
                const errJson = await response.json();
                errDetail = errJson.detail || errDetail;
            } catch (e) {
                errDetail = `HTTP Error ${response.status}: ${response.statusText}`;
            }
            throw new Error(errDetail);
        }

        const data = await response.json();
        console.log('[Upload] Success. Extracted data:', data);

        currentConversationId = data.conversation_id;
        lastMessageId = null;

        // Render structured resume profile
        renderProfilePreview(data.extracted_data);

        // Update session ID indicator in header
        const sessionDisplay = document.getElementById('session-id-display');
        if (sessionDisplay) {
            sessionDisplay.textContent = `ID: ${currentConversationId}`;
            sessionDisplay.style.display = 'inline-block';
        }
        updateConnectionStatus('Active Interview', true);

        // Hide setup section, reveal active chat workspace
        document.getElementById('setup-section').style.display = 'none';
        document.getElementById('chat-section').style.display = 'flex';

        // Automatically kick off the first interviewer turn
        await triggerInterviewKickoff();

    } catch (err) {
        console.error('[Upload] Error:', err);
        showAlert(`Upload Failed: ${err.message}`);
        updateConnectionStatus('Upload Error', false);
    } finally {
        uploadBtn.disabled = false;
        uploadBtnText.textContent = 'Upload Resume & Start Interview';
    }
}

// ============================================================
// Auto-Kickoff — Sends initial prompt to start the interview
// ============================================================
async function triggerInterviewKickoff() {
    showTypingIndicator();
    const apiBase = getApiBaseUrl();

    const initialPrompt = "Hello. I have submitted my resume and I'm ready to begin the technical interview.";

    console.log(`[Chat] Sending kickoff prompt to ${apiBase}/chat...`);

    try {
        const response = await fetch(`${apiBase}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                conversation_id: currentConversationId,
                message: initialPrompt,
                parent_id: null
            })
        });

        removeTypingIndicator();

        if (!response.ok) {
            let errDetail = 'Initial interview kickoff failed.';
            try {
                const errData = await response.json();
                errDetail = errData.detail || errDetail;
            } catch (e) {
                errDetail = `HTTP ${response.status}: ${response.statusText}`;
            }
            throw new Error(errDetail);
        }

        const data = await response.json();
        console.log('[Chat] Kickoff response received:', data);

        lastMessageId = data.message_id;

        // Display interviewer opening question
        appendMessage('ai', data.response);

        // Focus user input for seamless chatting
        const userInput = document.getElementById('user-input');
        if (userInput) userInput.focus();

    } catch (err) {
        removeTypingIndicator();
        console.error('[Chat] Kickoff failed:', err);
        showAlert(`Failed to initiate dialogue with Interviewer: ${err.message}`);
    }
}

// ============================================================
// Step 2 — Send Chat Message (POST /chat)
// ============================================================
async function sendMessage() {
    if (isProcessing) return;

    const inputEl = document.getElementById('user-input');
    const messageText = inputEl.value.trim();
    const sendBtn = document.getElementById('send-btn');
    const apiBase = getApiBaseUrl();

    if (!messageText) return;

    if (!currentConversationId) {
        showAlert('No active interview session found. Please upload a resume first.');
        return;
    }

    hideAlert();

    // Display user message in chat immediately (optimistic UI)
    appendMessage('user', messageText);
    inputEl.value = '';
    autoResizeTextarea(inputEl);

    // Set loading state
    isProcessing = true;
    sendBtn.disabled = true;
    showTypingIndicator();

    try {
        const payload = {
            conversation_id: currentConversationId,
            message: messageText,
            parent_id: lastMessageId
        };

        console.log(`[Chat] Sending candidate response (${messageText.length} chars)...`);

        const response = await fetch(`${apiBase}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        removeTypingIndicator();

        if (!response.ok) {
            let errDetail = 'Chat response failed';
            try {
                const errData = await response.json();
                errDetail = errData.detail || errDetail;
            } catch (e) {
                errDetail = `HTTP ${response.status}: ${response.statusText}`;
            }
            throw new Error(errDetail);
        }

        const data = await response.json();
        console.log('[Chat] Received AI response:', data);

        lastMessageId = data.message_id;

        // Render interviewer response
        appendMessage('ai', data.response);

    } catch (err) {
        removeTypingIndicator();
        console.error('[Chat] Send message error:', err);
        showAlert(`Interviewer response error: ${err.message}`);
    } finally {
        isProcessing = false;
        sendBtn.disabled = false;
        inputEl.focus();
    }
}

// ============================================================
// DOM Rendering Helpers
// ============================================================

/** Render the structured candidate profile card */
function renderProfilePreview(data) {
    if (!data) return;
    const previewCard = document.getElementById('profile-preview');
    const summaryEl = document.getElementById('profile-summary');
    const skillsEl = document.getElementById('profile-skills');
    const roleTag = document.getElementById('profile-role-tag');

    // Inferred Role Tag
    if (roleTag) {
        if (data.inferred_role) {
            roleTag.textContent = `🎯 ${data.inferred_role}`;
            roleTag.style.display = 'inline-block';
        } else {
            roleTag.style.display = 'none';
        }
    }

    // Professional Summary
    if (summaryEl) {
        summaryEl.textContent = data.summary || 'Summary parsed from candidate resume.';
    }

    // Key Skills Tags
    if (skillsEl) {
        skillsEl.innerHTML = '';
        const skills = data.skills || [];
        if (skills.length > 0) {
            skills.forEach(skill => {
                const tag = document.createElement('span');
                tag.className = 'skill-tag';
                tag.textContent = skill;
                skillsEl.appendChild(tag);
            });
        } else {
            skillsEl.innerHTML = '<span style="font-size: 12px; color: #94a3b8;">No skills parsed.</span>';
        }
    }

    // Key Projects
    const projectsSec = document.getElementById('profile-projects-section');
    const projectsEl = document.getElementById('profile-projects');
    if (projectsSec && projectsEl) {
        const projects = data.projects || [];
        if (projects.length > 0) {
            projectsEl.innerHTML = '';
            projects.forEach(p => {
                const card = document.createElement('div');
                card.className = 'project-card';

                const title = document.createElement('div');
                title.className = 'project-title';
                title.textContent = p.title || 'Project';
                card.appendChild(title);

                if (p.highlights && p.highlights.length > 0) {
                    const ul = document.createElement('ul');
                    ul.className = 'project-highlights';
                    p.highlights.forEach(h => {
                        const li = document.createElement('li');
                        li.textContent = h;
                        ul.appendChild(li);
                    });
                    card.appendChild(ul);
                }

                projectsEl.appendChild(card);
            });
            projectsSec.style.display = 'block';
        } else {
            projectsSec.style.display = 'none';
        }
    }

    // Certifications
    const certsSec = document.getElementById('profile-certifications-section');
    const certsEl = document.getElementById('profile-certifications');
    if (certsSec && certsEl) {
        const certs = data.certifications || [];
        if (certs.length > 0) {
            certsEl.innerHTML = '';
            certs.forEach(c => {
                const tag = document.createElement('span');
                tag.className = 'cert-tag';
                tag.textContent = `📜 ${c}`;
                certsEl.appendChild(tag);
            });
            certsSec.style.display = 'block';
        } else {
            certsSec.style.display = 'none';
        }
    }

    if (previewCard) {
        previewCard.style.display = 'block';
    }
}

/** Toggle expand/collapse of the profile summary card */
function toggleProfileDetails() {
    const details = document.getElementById('profile-details-body');
    const btn = document.getElementById('toggle-profile-btn');
    if (!details || !btn) return;

    if (details.style.display === 'none') {
        details.style.display = 'block';
        btn.textContent = 'Hide Details ▲';
    } else {
        details.style.display = 'none';
        btn.textContent = 'Show Details ▼';
    }
}

/** Append a message bubble to the chat window */
function appendMessage(role, text) {
    const chatWindow = document.getElementById('chat-window');
    if (!chatWindow) return;

    const messageRow = document.createElement('div');
    messageRow.className = `message-row ${role}`;

    const contentWrapper = document.createElement('div');
    contentWrapper.className = 'message-content';

    // Header with sender name and current time
    const headerRow = document.createElement('div');
    headerRow.className = 'message-header';

    const senderLabel = document.createElement('span');
    senderLabel.className = 'message-sender';
    senderLabel.textContent = role === 'user' ? 'Candidate' : 'Interviewer';

    const timeLabel = document.createElement('span');
    timeLabel.className = 'message-time';
    const now = new Date();
    timeLabel.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    headerRow.appendChild(senderLabel);
    headerRow.appendChild(timeLabel);

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = formatMarkdown(text);

    contentWrapper.appendChild(headerRow);
    contentWrapper.appendChild(bubble);

    messageRow.appendChild(contentWrapper);
    chatWindow.appendChild(messageRow);

    // Smoothly scroll down
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

// ============================================================
// Typing Indicator
// ============================================================
function showTypingIndicator() {
    removeTypingIndicator();
    const chatWindow = document.getElementById('chat-window');
    if (!chatWindow) return;

    const row = document.createElement('div');
    row.className = 'message-row ai';
    row.id = 'typing-indicator-row';

    const contentWrapper = document.createElement('div');
    contentWrapper.className = 'message-content';

    const senderLabel = document.createElement('div');
    senderLabel.className = 'message-sender';
    senderLabel.textContent = 'Interviewer is evaluating...';

    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator';
    indicator.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';

    contentWrapper.appendChild(senderLabel);
    contentWrapper.appendChild(indicator);
    row.appendChild(contentWrapper);

    chatWindow.appendChild(row);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function removeTypingIndicator() {
    const existing = document.getElementById('typing-indicator-row');
    if (existing) {
        existing.remove();
    }
}

// ============================================================
// Reset / New Session
// ============================================================
function resetInterviewSession() {
    if (confirm('Start a new interview session? This will reset the dialogue and let you upload a new resume.')) {
        currentConversationId = null;
        lastMessageId = null;

        const chatWindow = document.getElementById('chat-window');
        if (chatWindow) chatWindow.innerHTML = '';

        document.getElementById('chat-section').style.display = 'none';
        document.getElementById('profile-preview').style.display = 'none';
        document.getElementById('setup-section').style.display = 'block';

        clearSelectedFile();

        const sessionDisplay = document.getElementById('session-id-display');
        if (sessionDisplay) {
            sessionDisplay.textContent = '';
            sessionDisplay.style.display = 'none';
        }

        updateConnectionStatus('Ready', true);
        hideAlert();
    }
}

// ============================================================
// Markdown Formatter (lightweight & secure)
// ============================================================
function formatMarkdown(text) {
    if (!text) return '';

    // Escape HTML to prevent injection
    let escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Fenced Code blocks: ```code```
    escaped = escaped.replace(/```([\s\S]*?)```/g, function (match, code) {
        return '<pre><code>' + code.trim() + '</code></pre>';
    });

    // Inline code: `code`
    escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold: **text**
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Italic: *text*
    escaped = escaped.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Process line-by-line for paragraphs and lists
    const lines = escaped.split('\n');
    let formatted = '';
    let inList = false;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();

        if (line.startsWith('- ') || line.startsWith('* ')) {
            if (!inList) {
                formatted += '<ul>';
                inList = true;
            }
            formatted += '<li>' + line.substring(2) + '</li>';
        } else {
            if (inList) {
                formatted += '</ul>';
                inList = false;
            }
            if (line.length > 0) {
                if (!line.startsWith('<pre>') && !line.endsWith('</pre>')) {
                    formatted += '<p>' + line + '</p>';
                } else {
                    formatted += line;
                }
            }
        }
    }

    if (inList) {
        formatted += '</ul>';
    }

    return formatted || escaped;
}

// ============================================================
// Event Listeners: Drag & Drop + DOM Initialization
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    // 1. Check backend connection
    checkBackendHealth();

    // 2. Drag & Drop on setup-section and drop-zone
    const dropZone = document.getElementById('drop-zone');
    const setupSection = document.getElementById('setup-section');
    const fileInput = document.getElementById('resume-file');

    if (dropZone && fileInput) {
        // Clicking dropZone triggers hidden file input
        dropZone.addEventListener('click', () => {
            fileInput.click();
        });

        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.add('dragover');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.remove('dragover');
            }, false);
        });

        dropZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files && files.length > 0) {
                fileInput.files = files;
                onFileSelected(fileInput);
            }
        });
    }
});
