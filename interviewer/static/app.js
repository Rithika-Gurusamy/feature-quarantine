/* ============================================================
   app.js — Frontend Controller for AI Mock Interviewer
   ============================================================
   Handles:
     • Resume upload via POST /resume/upload  (multipart/form-data)
     • Chat messages  via POST /chat           (JSON)
     • DOM rendering (profile preview, chat bubbles, typing indicator)
     • Drag-and-drop PDF upload
   ============================================================ */

// --------------- Session State ---------------
let currentConversationId = null;
let lastMessageId = null;
let isProcessing = false;

// --------------- API Helper ---------------
/**
 * Resolves the backend base URL.
 * When index.html is served by FastAPI (http://localhost:8000),
 * window.location.origin already points at the backend — no manual config needed.
 */
function getApiBaseUrl() {
    if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {
        return window.location.origin;
    }
    return 'http://localhost:8000';
}

// --------------- Alert Banner ---------------
function showAlert(message, type = 'error') {
    const alertBox = document.getElementById('alert-box');
    const alertMsg = document.getElementById('alert-message');
    alertBox.className = `alert ${type}`;
    alertMsg.textContent = message;
    alertBox.style.display = 'flex';
}

function hideAlert() {
    document.getElementById('alert-box').style.display = 'none';
}

// --------------- File Selection ---------------
function onFileSelected(input) {
    hideAlert();
    if (input.files && input.files[0]) {
        const file = input.files[0];
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            showAlert('Only PDF files are supported. Please select a valid .pdf file.');
            input.value = '';
        }
    }
}

// --------------- Textarea Auto-resize ---------------
function autoResizeTextarea(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 160) + 'px';
}

// --------------- Keyboard Shortcut ---------------
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
        showAlert('Please choose a PDF resume file to upload.');
        return;
    }

    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        showAlert('Please select a PDF file (.pdf extension).');
        return;
    }

    // UI state: uploading
    uploadBtn.disabled = true;
    uploadBtnText.innerHTML = '<span class="spinner"></span> Extracting & Analyzing Resume with Gemini...';
    updateConnectionStatus('Analyzing Resume...', false);

    // Build multipart/form-data payload
    const formData = new FormData();
    formData.append('file', file);
    const targetRoleInput = document.getElementById('target-role');
    if (targetRoleInput && targetRoleInput.value.trim()) {
        formData.append('target_role', targetRoleInput.value.trim());
    }

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
        currentConversationId = data.conversation_id;
        lastMessageId = null;

        // Render structured resume profile
        renderProfilePreview(data.extracted_data);

        // Update session indicators
        const sessionDisplay = document.getElementById('session-id-display');
        if (sessionDisplay) {
            sessionDisplay.textContent = currentConversationId;
        }
        updateConnectionStatus('Active', true);

        // Reveal chat workspace, hide upload form
        document.getElementById('chat-section').style.display = 'flex';
        document.getElementById('setup-section').style.display = 'none';

        // Automatically kick off the interview
        await triggerInterviewKickoff();

    } catch (err) {
        console.error('Upload failed:', err);
        showAlert(`Connection/Upload Error: ${err.message}. Make sure app.py is running on ${apiBase} and Docker Redis is online.`);
        updateConnectionStatus('Connection Error', false);
    } finally {
        uploadBtn.disabled = false;
        uploadBtnText.textContent = 'Upload Resume and Start Interview';
    }
}

// ============================================================
// Auto-kickoff — Sends the first message so the AI starts asking
// ============================================================
async function triggerInterviewKickoff() {
    showTypingIndicator();
    const apiBase = getApiBaseUrl();

    const initialPrompt = "Hello. I have submitted my resume and I'm ready to begin the technical interview.";

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
            const err = await response.json().catch(() => ({ detail: 'Failed to start interview.' }));
            throw new Error(err.detail || 'Initial chat request failed');
        }

        const data = await response.json();
        lastMessageId = data.message_id;

        // Display interviewer's opening question
        appendMessage('ai', data.response);
        document.getElementById('user-input').focus();

    } catch (err) {
        removeTypingIndicator();
        console.error('Kickoff chat failed:', err);
        showAlert(`Failed to initiate conversation with Interviewer: ${err.message}`);
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

    // Display user message in chat immediately (optimistic render)
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

        const response = await fetch(`${apiBase}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        removeTypingIndicator();

        if (!response.ok) {
            let errDetail = 'Chat request failed';
            try {
                const errData = await response.json();
                errDetail = errData.detail || errDetail;
            } catch (e) {
                errDetail = `HTTP ${response.status}: ${response.statusText}`;
            }
            throw new Error(errDetail);
        }

        const data = await response.json();
        lastMessageId = data.message_id;

        // Render interviewer's response
        appendMessage('ai', data.response);

    } catch (err) {
        removeTypingIndicator();
        console.error('Chat error:', err);
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
    if (roleTag) {
        if (data && data.target_role) {
            roleTag.textContent = `Target: ${data.target_role}`;
            roleTag.style.display = 'inline-block';
        } else {
            roleTag.style.display = 'none';
        }
    }

    summaryEl.textContent = data.summary || 'Summary generated from candidate resume.';
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

    previewCard.style.display = 'block';
}

/** Append a message bubble to the chat window */
function appendMessage(role, text) {
    const chatWindow = document.getElementById('chat-window');

    const messageRow = document.createElement('div');
    messageRow.className = `message-row ${role}`;

    const contentWrapper = document.createElement('div');
    contentWrapper.className = 'message-content';

    const senderLabel = document.createElement('div');
    senderLabel.className = 'message-sender';
    senderLabel.textContent = role === 'user' ? 'Candidate' : 'Interviewer';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = formatMarkdown(text);

    contentWrapper.appendChild(senderLabel);
    contentWrapper.appendChild(bubble);

    messageRow.appendChild(contentWrapper);

    chatWindow.appendChild(messageRow);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

// ============================================================
// Typing Indicator
// ============================================================
function showTypingIndicator() {
    removeTypingIndicator();
    const chatWindow = document.getElementById('chat-window');

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
// Connection Status Pill
// ============================================================
function updateConnectionStatus(text, isConnected) {
    const pill = document.getElementById('connection-pill');
    const label = document.getElementById('connection-text');
    label.textContent = text;
    if (isConnected) {
        pill.classList.add('connected');
    } else {
        pill.classList.remove('connected');
    }
}

// ============================================================
// Reset / New Session
// ============================================================
function resetInterviewSession() {
    if (confirm('Start a new interview session? This will reset the current dialogue view.')) {
        currentConversationId = null;
        lastMessageId = null;
        document.getElementById('chat-window').innerHTML = '';
        document.getElementById('chat-section').style.display = 'none';
        document.getElementById('profile-preview').style.display = 'none';
        document.getElementById('setup-section').style.display = 'block';
        document.getElementById('resume-file').value = '';
        const targetRoleInput = document.getElementById('target-role');
        if (targetRoleInput) targetRoleInput.value = '';
        updateConnectionStatus('Standby', false);
        hideAlert();
    }
}

// ============================================================
// Markdown Formatter (lightweight)
// ============================================================
function formatMarkdown(text) {
    if (!text) return '';

    // Escape HTML entities to prevent injection
    let escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Code blocks: ```code```
    escaped = escaped.replace(/```([\s\S]*?)```/g, function (match, code) {
        return '<pre><code>' + code.trim() + '</code></pre>';
    });

    // Inline code: `code`
    escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold: **text**
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Italic: *text*
    escaped = escaped.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Split into paragraphs / lines
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
// Drag & Drop Support for PDF Upload
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    const setupSection = document.getElementById('setup-section');

    ['dragenter', 'dragover'].forEach(eventName => {
        setupSection.addEventListener(eventName, (e) => {
            e.preventDefault();
            setupSection.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        setupSection.addEventListener(eventName, (e) => {
            e.preventDefault();
            setupSection.classList.remove('dragover');
        }, false);
    });

    setupSection.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length > 0) {
            const fileInput = document.getElementById('resume-file');
            fileInput.files = files;
            onFileSelected(fileInput);
        }
    });
});
