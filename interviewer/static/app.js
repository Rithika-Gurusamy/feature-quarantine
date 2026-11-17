/* ============================================================
   AI Mock Interviewer — Frontend Controller
   ============================================================ */

// ── State ─────────────────────────────────────────────────────
let currentConversationId = null;
let lastMessageId = null;
let isBusy = false;
let activeBackendUrl = null;

// ── Voice Input State ──────────────────────────────────────────
let recognition = null;
let isListening = false;

// ── Voice Input (Web Speech API) ──────────────────────────────
function toggleVoiceInput() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        showAlert('Voice input is not supported in this browser. Please use Chrome or Edge.');
        console.warn('[Voice] SpeechRecognition API not available in this browser.');
        return;
    }
    if (isListening) {
        console.log('[Voice] Stopping recording...');
        stopVoiceInput();
    } else {
        console.log('[Voice] Starting recording...');
        startVoiceInput(SpeechRecognition);
    }
}

function startVoiceInput(SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = true;   // show partial results live in textarea
    recognition.continuous = false;       // auto-stop after pause

    const micBtn = document.getElementById('mic-btn');
    const textarea = document.getElementById('user-input');

    isListening = true;
    if (micBtn) {
        micBtn.classList.add('recording');
        micBtn.title = 'Listening… click to stop';
        micBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="12" r="8" opacity="0.3"/>
            <circle cx="12" cy="12" r="4"/>
        </svg>`;
    }
    console.log('[Voice] Listening started. Speak now...');

    // Track the text that was already in the textarea before speech
    const priorText = textarea ? textarea.value : '';

    recognition.onstart = () => {
        console.log('[Voice] Speech recognition started.');
    };

    recognition.onresult = (event) => {
        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
            const result = event.results[i];
            if (result.isFinal) {
                finalTranscript += result[0].transcript;
            } else {
                interimTranscript += result[0].transcript;
            }
        }

        // Show live interim result in textarea so user can see what's captured
        const captured = finalTranscript || interimTranscript;
        if (textarea) {
            // Append to any prior text, with a space separator if needed
            const separator = priorText && !priorText.endsWith(' ') ? ' ' : '';
            textarea.value = priorText + separator + captured;
            autoGrow(textarea);
        }
        console.log(`[Voice] Captured (interim=${!finalTranscript}): "${captured}"`);
    };

    recognition.onend = () => {
        console.log('[Voice] Speech recognition ended.');
        stopVoiceInput();
        // Focus textarea so user can review/edit before sending
        if (textarea) textarea.focus();
    };

    recognition.onerror = (event) => {
        console.error(`[Voice] Recognition error: ${event.error}`);
        stopVoiceInput();
        if (event.error !== 'aborted' && event.error !== 'no-speech') {
            showAlert(`Voice recognition error: ${event.error}. Try again or type your response.`);
        }
    };

    recognition.start();
}

function stopVoiceInput() {
    if (recognition) {
        try { recognition.stop(); } catch (_) {}
        recognition = null;
    }
    isListening = false;
    const micBtn = document.getElementById('mic-btn');
    if (micBtn) {
        micBtn.classList.remove('recording');
        micBtn.title = 'Speak your response';
        micBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="2" width="6" height="11" rx="3"></rect>
            <path d="M5 10a7 7 0 0 0 14 0"></path>
            <line x1="12" y1="17" x2="12" y2="21"></line>
            <line x1="8" y1="21" x2="16" y2="21"></line>
        </svg>`;
    }
    console.log('[Voice] Listening stopped.');
}

// ── Dynamic Backend URL Resolution ────────────────────────────
async function resolveBackendUrl() {
    // If opened directly from the FastAPI server (e.g. http://127.0.0.1:8000 or http://localhost:8000)
    if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {
        if (window.location.port !== '5500') {
            activeBackendUrl = window.location.origin;
            return activeBackendUrl;
        }
    }

    // If opened via file:/// or Live Server (5500), probe 127.0.0.1:8000 first (Uvicorn default IPv4)
    const candidates = ['http://127.0.0.1:8000', 'http://localhost:8000'];
    for (const url of candidates) {
        try {
            const res = await fetch(`${url}/api/health`, { method: 'GET' });
            if (res.ok) {
                activeBackendUrl = url;
                console.log(`[Backend] Successfully connected to ${url}`);
                return activeBackendUrl;
            }
        } catch (_) {}
    }

    // Default to 127.0.0.1:8000
    activeBackendUrl = 'http://127.0.0.1:8000';
    return activeBackendUrl;
}

function getBackendUrl() {
    return activeBackendUrl || 'http://127.0.0.1:8000';
}

// ── Health Check on Load ──────────────────────────────────────
async function pingBackend() {
    const backend = await resolveBackendUrl();
    console.log(`[Init] Checking backend health at ${backend}/api/health...`);

    try {
        const res = await fetch(`${backend}/api/health`, { method: 'GET' });
        if (res.ok) {
            const data = await res.json();
            console.log('[Init] Server response:', data);
            if (data.redis_connected) {
                setStatus('Ready', true);
                hideAlert();
            } else {
                setStatus('Redis Offline', false);
                showAlert('Redis is offline! Please start Redis on localhost:6379.');
            }
        } else {
            setStatus('Degraded', false);
        }
    } catch (e) {
        console.warn(`[Init] Could not reach backend:`, e.message);
        setStatus('Offline', false);
        showAlert(
            `Cannot connect to FastAPI backend. Please open http://127.0.0.1:8000 directly in your browser.`
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

    if (!fileInput.files || fileInput.files.length === 0) {
        showAlert('Please choose or drop your PDF resume to start.');
        return;
    }

    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        showAlert('Only PDF files are supported.');
        return;
    }

    // Ensure backend URL is resolved
    const backend = await resolveBackendUrl();

    startBtn.disabled = true;
    startBtnText.innerHTML = '<span class="spinner"></span> Analyzing Resume with Gemini...';
    setStatus('Analyzing...', false);

    const formData = new FormData();
    formData.append('file', file);

    const uploadUrl = `${backend}/resume/upload`;
    console.log(`[Upload] Sending ${file.name} to ${uploadUrl}...`);

    try {
        const res = await fetch(uploadUrl, {
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

            if (res.status === 404) {
                detail = `404 Not Found from ${uploadUrl}. Please open http://127.0.0.1:8000 in your browser.`;
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
    const chatUrl = `${backend}/chat`;

    const kickoffPrompt = "Hello. I have submitted my resume and I'm ready to begin the technical interview.";
    console.log(`[Chat] Sending kickoff prompt to ${chatUrl}...`);

    try {
        const res = await fetch(chatUrl, {
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
    const chatUrl = `${backend}/chat`;

    if (!message) return;
    if (!currentConversationId) {
        showAlert('No active interview session found. Please upload a resume.');
        return;
    }

    hideAlert();

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

        const res = await fetch(chatUrl, {
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

    // Add read-aloud button only on AI messages
    if (role === 'ai') {
        const actionsRow = document.createElement('div');
        actionsRow.className = 'message-actions';

        const speakBtn = document.createElement('button');
        speakBtn.type = 'button';
        speakBtn.className = 'btn-speak';
        speakBtn.title = 'Read this question aloud';
        speakBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
            </svg>
            <span>Read aloud</span>`;

        speakBtn.addEventListener('click', () => toggleReadAloud(text, speakBtn));
        actionsRow.appendChild(speakBtn);
        content.appendChild(actionsRow);
    }

    row.appendChild(content);
    feed.appendChild(row);
    feed.scrollTop = feed.scrollHeight;
}

// ── Text-to-Speech (Read AI Messages Aloud) ───────────────────
let currentUtterance = null;

function stripMarkdown(text) {
    // Remove markdown so TTS reads clean prose
    return text
        .replace(/```[\s\S]*?```/g, '')   // code blocks
        .replace(/`[^`]+`/g, '')           // inline code
        .replace(/\*\*([^*]+)\*\*/g, '$1') // bold
        .replace(/\*([^*]+)\*/g, '$1')     // italic
        .replace(/^[-*]\s+/gm, '')         // list bullets
        .replace(/\n+/g, ' ')              // newlines → spaces
        .trim();
}

function toggleReadAloud(rawText, btn) {
    if (!window.speechSynthesis) {
        console.warn('[TTS] speechSynthesis not supported in this browser.');
        return;
    }

    // If already speaking THIS button's utterance — stop it
    if (btn.classList.contains('speaking')) {
        window.speechSynthesis.cancel();
        currentUtterance = null;
        resetSpeakBtn(btn);
        console.log('[TTS] Stopped.');
        return;
    }

    // Cancel any other ongoing speech first
    window.speechSynthesis.cancel();
    document.querySelectorAll('.btn-speak.speaking').forEach(resetSpeakBtn);

    const cleanText = stripMarkdown(rawText);
    if (!cleanText) return;

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = 'en-US';
    utterance.rate = 0.95;
    utterance.pitch = 1.0;

    console.log('[TTS] Reading aloud:', cleanText.substring(0, 80) + '...');

    // Visual state: speaking
    btn.classList.add('speaking');
    btn.title = 'Click to stop reading';
    btn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="4" width="4" height="16" rx="1"></rect>
            <rect x="14" y="4" width="4" height="16" rx="1"></rect>
        </svg>
        <span>Stop</span>`;

    utterance.onend = () => {
        currentUtterance = null;
        resetSpeakBtn(btn);
        console.log('[TTS] Finished reading.');
    };

    utterance.onerror = (e) => {
        currentUtterance = null;
        resetSpeakBtn(btn);
        console.warn('[TTS] Error:', e.error);
    };

    currentUtterance = utterance;
    window.speechSynthesis.speak(utterance);
}

function resetSpeakBtn(btn) {
    btn.classList.remove('speaking');
    btn.title = 'Read this question aloud';
    btn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
            <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
        </svg>
        <span>Read aloud</span>`;
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

    escaped = escaped.replace(/```([\s\S]*?)```/g, (_, code) => {
        return '<pre><code>' + code.trim() + '</code></pre>';
    });

    escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    escaped = escaped.replace(/\*([^*]+)\*/g, '<em>$1</em>');

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
