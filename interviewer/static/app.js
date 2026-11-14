/* ============================================================
   AI Mock Interviewer — Frontend Controller
   ============================================================ */

// ── State ─────────────────────────────────────────────────────
let currentConversationId = null;
let lastMessageId = null;
let isBusy = false;

// ── Backend URL Resolution ────────────────────────────────────
function getBackendUrl() {
    if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {
        if (window.location.port === '8000') {
            return window.location.origin;
        }
    }
    // Default backend URL
    return 'http://localhost:8000';
}

// ── Health Check on Load ──────────────────────────────────────
async function pingBackend() {
    const backend = getBackendUrl();
    try {
        const res = await fetch(`${backend}/api/health`, { method: 'GET' });
        if (res.ok) {
            const data = await res.json();
            if (data.redis_connected) {
                setStatus('Ready', true);
            } else {
                setStatus('Redis Offline', false);
                showAlert('Redis is not reachable on localhost:6379. Make sure Redis is started.');
            }
        } else {
            setStatus('Degraded', false);
        }
    } catch (e) {
        setStatus('Backend Offline', false);
        showAlert(
            `Cannot connect to FastAPI backend at ${backend}. ` +
            `Make sure you ran \`uvicorn app:app --reload --port 8000\` and opened http://localhost:8000 in your browser.`
        );
    }
}

// ── Status & Alert UI Helpers ─────────────────────────────────
function setStatus(text, isConnected) {
    const pill = document.getElementById('connection-pill');
    const label = document.getElementById('connection-text');
    if (label) label.textContent = text;
    if (pill) {
        if (isConnected) pill.classList.add('connected');
        else pill.classList.remove('connected');
    }
}

function showAlert(message) {
    const box = document.getElementById('alert-box');
    const text = document.getElementById('alert-message');
    if (box && text) {
        text.textContent = message;
        box.style.display = 'flex';
    }
}

function hideAlert() {
    const box = document.getElementById('alert-box');
    if (box) box.style.display = 'none';
}

// ── File Selection ────────────────────────────────────────────
function handleFileSelect(input) {
    hideAlert();
    const preview = document.getElementById('file-preview');
    const nameLabel = document.getElementById('file-name');

    if (input.files && input.files[0]) {
        const file = input.files[0];
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            showAlert('Please select a valid PDF file (.pdf).');
            input.value = '';
            if (preview) preview.style.display = 'none';
            return;
        }

        const sizeKb = (file.size / 1024).toFixed(1);
        if (nameLabel) nameLabel.textContent = `${file.name} (${sizeKb} KB)`;
        if (preview) preview.style.display = 'inline-flex';
    } else {
        if (preview) preview.style.display = 'none';
    }
}

function clearSelectedFile(e) {
    if (e) e.stopPropagation();
    const input = document.getElementById('resume-file');
    const preview = document.getElementById('file-preview');
    if (input) input.value = '';
    if (preview) preview.style.display = 'none';
    hideAlert();
}

// ── Upload Resume & Transition to Chat ────────────────────────
async function submitResume() {
    hideAlert();
    const fileInput = document.getElementById('resume-file');
    const startBtn = document.getElementById('start-btn');
    const startBtnText = document.getElementById('start-btn-text');
    const backend = getBackendUrl();

    if (!fileInput.files || fileInput.files.length === 0) {
        showAlert('Please choose or drop your PDF resume to start.');
        return;
    }

    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        showAlert('Only PDF files are supported.');
        return;
    }

    // Set UI loading state
    startBtn.disabled = true;
    startBtnText.innerHTML = '<span class="spinner"></span> Analyzing Resume with Gemini...';
    setStatus('Analyzing...', false);

    const formData = new FormData();
    formData.append('file', file);

    try {
        console.log(`[Upload] Sending ${file.name} to ${backend}/resume/upload...`);

        const res = await fetch(`${backend}/resume/upload`, {
            method: 'POST',
            body: formData
        });

        if (!res.ok) {
            let detail = 'Resume upload failed';
            try {
                const errData = await res.json();
                detail = errData.detail || detail;
            } catch (_) {
                detail = `HTTP ${res.status}: ${res.statusText}`;
            }
            throw new Error(detail);
        }

        const data = await res.json();
        console.log('[Upload] Extraction success:', data);

        currentConversationId = data.conversation_id;
        lastMessageId = null;

        // Display Inferred Role Badge
        const roleBadge = document.getElementById('role-badge');
        if (roleBadge) {
            const role = data.extracted_data?.inferred_role || 'Software Engineer';
            roleBadge.textContent = `🎯 ${role}`;
            roleBadge.style.display = 'inline-block';
        }

        // Show restart button
        const restartBtn = document.getElementById('restart-btn');
        if (restartBtn) restartBtn.style.display = 'inline-block';

        setStatus('Interviewing', true);

        // Switch from Upload View to Chat View
        document.getElementById('upload-view').style.display = 'none';
        document.getElementById('chat-view').style.display = 'flex';

        // Auto kickoff first interviewer question
        await triggerKickoff();

    } catch (err) {
        console.error('[Upload] Error:', err);
        showAlert(`Upload error: ${err.message}`);
        setStatus('Error', false);
    } finally {
        startBtn.disabled = false;
        startBtnText.textContent = 'Start Interview';
    }
}

// ── Kickoff AI First Message ──────────────────────────────────
async function triggerKickoff() {
    showTyping();
    const backend = getBackendUrl();

    const kickoffPrompt = "Hello. I have submitted my resume and I'm ready to begin the technical interview.";

    try {
        const res = await fetch(`${backend}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                conversation_id: currentConversationId,
                message: kickoffPrompt,
                parent_id: null
            })
        });

        removeTyping();

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Failed to start interview.' }));
            throw new Error(err.detail || 'Initial request failed');
        }

        const data = await res.json();
        lastMessageId = data.message_id;

        // Render AI opening message
        appendMessage('ai', data.response);

        const input = document.getElementById('user-input');
        if (input) input.focus();

    } catch (err) {
        removeTyping();
        showAlert(`Failed to start interview dialogue: ${err.message}`);
    }
}

// ── Send Candidate Response ───────────────────────────────────
async function sendCandidateMessage() {
    if (isBusy) return;

    const input = document.getElementById('user-input');
    const message = input.value.trim();
    const sendBtn = document.getElementById('send-btn');
    const backend = getBackendUrl();

    if (!message) return;
    if (!currentConversationId) {
        showAlert('No active interview session found. Please upload a resume.');
        return;
    }

    hideAlert();

    // Render candidate message immediately
    appendMessage('user', message);
    input.value = '';
    autoGrow(input);

    isBusy = true;
    if (sendBtn) sendBtn.disabled = true;
    showTyping();

    try {
        const payload = {
            conversation_id: currentConversationId,
            message: message,
            parent_id: lastMessageId
        };

        const res = await fetch(`${backend}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        removeTyping();

        if (!res.ok) {
            let detail = 'Error receiving AI response';
            try {
                const errJson = await res.json();
                detail = errJson.detail || detail;
            } catch (_) {
                detail = `HTTP ${res.status}: ${res.statusText}`;
            }
            throw new Error(detail);
        }

        const data = await res.json();
        lastMessageId = data.message_id;

        // Render AI response
        appendMessage('ai', data.response);

    } catch (err) {
        removeTyping();
        showAlert(`Error: ${err.message}`);
    } finally {
        isBusy = false;
        if (sendBtn) sendBtn.disabled = false;
        input.focus();
    }
}

// ── DOM Message Rendering ─────────────────────────────────────
function appendMessage(role, text) {
    const feed = document.getElementById('chat-messages');
    if (!feed) return;

    const row = document.createElement('div');
    row.className = `message-row ${role}`;

    const content = document.createElement('div');
    content.className = 'message-content';

    const sender = document.createElement('div');
    sender.className = 'message-sender';
    sender.textContent = role === 'user' ? 'You (Candidate)' : 'Technical Interviewer';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = renderMarkdown(text);

    content.appendChild(sender);
    content.appendChild(bubble);
    row.appendChild(content);

    feed.appendChild(row);
    feed.scrollTop = feed.scrollHeight;
}

// ── Typing Indicator ──────────────────────────────────────────
function showTyping() {
    removeTyping();
    const feed = document.getElementById('chat-messages');
    if (!feed) return;

    const row = document.createElement('div');
    row.className = 'message-row ai';
    row.id = 'typing-indicator';

    const content = document.createElement('div');
    content.className = 'message-content';

    const sender = document.createElement('div');
    sender.className = 'message-sender';
    sender.textContent = 'Interviewer is evaluating...';

    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator';
    indicator.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';

    content.appendChild(sender);
    content.appendChild(indicator);
    row.appendChild(content);

    feed.appendChild(row);
    feed.scrollTop = feed.scrollHeight;
}

function removeTyping() {
    const el = document.getElementById('typing-indicator');
    if (el) el.remove();
}

// ── Restart Session ───────────────────────────────────────────
function restartSession() {
    if (confirm('Restart interview? This will clear the current dialogue and return to resume upload.')) {
        currentConversationId = null;
        lastMessageId = null;

        const feed = document.getElementById('chat-messages');
        if (feed) feed.innerHTML = '';

        document.getElementById('chat-view').style.display = 'none';
        document.getElementById('upload-view').style.display = 'flex';

        clearSelectedFile();

        const roleBadge = document.getElementById('role-badge');
        if (roleBadge) roleBadge.style.display = 'none';

        const restartBtn = document.getElementById('restart-btn');
        if (restartBtn) restartBtn.style.display = 'none';

        setStatus('Ready', true);
        hideAlert();
    }
}

// ── Textarea Keyboard & Auto-Resize ───────────────────────────
function handleKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendCandidateMessage();
    }
}

function autoGrow(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 140) + 'px';
}

// ── Safe Lightweight Markdown ─────────────────────────────────
function renderMarkdown(text) {
    if (!text) return '';

    let escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Code blocks ```code```
    escaped = escaped.replace(/```([\s\S]*?)```/g, (_, code) => {
        return '<pre><code>' + code.trim() + '</code></pre>';
    });

    // Inline code `code`
    escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold **text**
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Italic *text*
    escaped = escaped.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Paragraphs and lists
    const lines = escaped.split('\n');
    let out = '';
    let inList = false;

    for (let line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
            if (!inList) {
                out += '<ul>';
                inList = true;
            }
            out += '<li>' + trimmed.substring(2) + '</li>';
        } else {
            if (inList) {
                out += '</ul>';
                inList = false;
            }
            if (trimmed.length > 0) {
                if (!trimmed.startsWith('<pre>') && !trimmed.endsWith('</pre>')) {
                    out += '<p>' + trimmed + '</p>';
                } else {
                    out += trimmed;
                }
            }
        }
    }

    if (inList) out += '</ul>';
    return out || escaped;
}

// ── Initialize Drag & Drop and Ping ───────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    pingBackend();

    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('resume-file');

    if (dropzone && fileInput) {
        ['dragenter', 'dragover'].forEach(name => {
            dropzone.addEventListener(name, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.add('dragover');
            });
        });

        ['dragleave', 'drop'].forEach(name => {
            dropzone.addEventListener(name, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove('dragover');
            });
        });

        dropzone.addEventListener('drop', (e) => {
            const files = e.dataTransfer?.files;
            if (files && files.length > 0) {
                fileInput.files = files;
                handleFileSelect(fileInput);
            }
        });
    }
});
