/**
 * NexusInterview - Main Application Controller
 * Handles Screen Routing, API Communication, Chat UI, Real-time Countdown, and Audio/Text coordination.
 */

// Application State
const state = {
  sessionId: null,
  candidateName: "Candidate",
  candidateProfile: null,
  remainingSeconds: 300,
  isPaused: false,
  isFinished: false,
  timerInterval: null,
  conversationHistory: [],
  isSubmitting: false
};

// DOM Elements Cache
const DOM = {
  // Screens
  screens: {
    upload: document.getElementById("screen-upload"),
    interview: document.getElementById("screen-interview"),
    completed: document.getElementById("screen-completed")
  },

  // Header Elements
  headerControls: document.getElementById("interview-header-controls"),
  headerCandidateName: document.getElementById("header-candidate-name"),
  btnToggleMemory: document.getElementById("btn-toggle-memory"),
  aiStatusIndicator: document.getElementById("ai-status-indicator"),
  aiStatusText: document.getElementById("ai-status-text"),
  timerDisplay: document.getElementById("timer-display"),
  timerCard: document.getElementById("timer-display-card"),
  btnFinish: document.getElementById("btn-finish-interview"),

  // Memory Drawer
  memoryDrawer: document.getElementById("memory-drawer"),
  btnCloseMemory: document.getElementById("btn-close-memory"),
  memName: document.getElementById("mem-name"),
  memTitle: document.getElementById("mem-title"),
  memEmail: document.getElementById("mem-email"),
  memSkillsTags: document.getElementById("mem-skills-tags"),
  memProjectsList: document.getElementById("mem-projects-list"),
  memTopics: document.getElementById("mem-topics"),
  memStrengths: document.getElementById("mem-strengths"),
  memRawJson: document.getElementById("mem-raw-json"),

  // Upload Screen
  dropZone: document.getElementById("drop-zone"),
  fileInput: document.getElementById("resume-file-input"),
  btnBrowseFile: document.getElementById("btn-browse-file"),
  btnLoadDemoResume: document.getElementById("btn-load-demo-resume"),
  uploadStatusCard: document.getElementById("upload-status-card"),
  uploadFilename: document.getElementById("upload-filename"),
  uploadProgressText: document.getElementById("upload-progress-text"),
  uploadErrorAlert: document.getElementById("upload-error-alert"),
  uploadErrorText: document.getElementById("upload-error-text"),

  // Interview Screen
  ttsFloatingBar: document.getElementById("tts-floating-bar"),
  ttsStatusLabel: document.getElementById("tts-status-label"),
  speakerWave: document.getElementById("speaker-wave"),
  btnTtsPauseResume: document.getElementById("btn-tts-pause-resume"),
  iconTtsPause: document.getElementById("icon-tts-pause"),
  iconTtsPlay: document.getElementById("icon-tts-play"),
  ttsBtnText: document.getElementById("tts-btn-text"),
  btnTtsToggleMute: document.getElementById("btn-tts-toggle-mute"),
  iconTtsUnmuted: document.getElementById("icon-tts-unmuted"),
  iconTtsMuted: document.getElementById("icon-tts-muted"),
  ttsMuteBtnText: document.getElementById("tts-mute-btn-text"),

  chatContainer: document.getElementById("chat-container"),
  messagesList: document.getElementById("messages-list"),

  sttPreviewCard: document.getElementById("stt-preview-card"),
  sttLiveTranscript: document.getElementById("stt-live-transcript"),

  btnToggleMic: document.getElementById("btn-toggle-mic"),
  candidateTextInput: document.getElementById("candidate-text-input"),
  btnSendMessage: document.getElementById("btn-send-message"),

  // Completed Screen
  statTurnsCount: document.getElementById("stat-turns-count"),
  statDuration: document.getElementById("stat-duration"),
  statCandidateName: document.getElementById("stat-candidate-name"),
  finalTranscriptBody: document.getElementById("final-transcript-body"),
  btnCopyTranscript: document.getElementById("btn-copy-transcript"),
  btnRestartInterview: document.getElementById("btn-restart-interview")
};

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  setupTTSListeners();
  setupSTTListeners();
});

function setupEventListeners() {
  // Screen 1: File Upload events
  DOM.btnBrowseFile.addEventListener("click", () => DOM.fileInput.click());
  DOM.dropZone.addEventListener("click", (e) => {
    if (e.target !== DOM.btnBrowseFile && !DOM.btnLoadDemoResume.contains(e.target)) {
      DOM.fileInput.click();
    }
  });

  DOM.btnLoadDemoResume.addEventListener("click", (e) => {
    e.stopPropagation();
    loadDemoResume();
  });

  DOM.fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) handleFileUpload(e.target.files[0]);
  });

  // Drag & Drop
  ["dragenter", "dragover"].forEach((eventName) => {
    DOM.dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      DOM.dropZone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    DOM.dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      DOM.dropZone.classList.remove("dragover");
    });
  });

  DOM.dropZone.addEventListener("drop", (e) => {
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  });

  // Memory Drawer Toggle
  DOM.btnToggleMemory.addEventListener("click", () => {
    DOM.memoryDrawer.classList.toggle("hidden");
  });
  DOM.btnCloseMemory.addEventListener("click", () => {
    DOM.memoryDrawer.classList.add("hidden");
  });

  // Screen 2: TTS UI Controls
  DOM.btnTtsPauseResume.addEventListener("click", () => {
    window.ttsController.togglePauseResume();
  });

  DOM.btnTtsToggleMute.addEventListener("click", () => {
    const isEnabled = window.ttsController.toggleMute();
    DOM.iconTtsUnmuted.classList.toggle("hidden", !isEnabled);
    DOM.iconTtsMuted.classList.toggle("hidden", isEnabled);
    DOM.ttsMuteBtnText.textContent = isEnabled ? "Voice On" : "Voice Off";
  });

  // STT Microphone Control
  DOM.btnToggleMic.addEventListener("click", () => {
    window.sttController.toggle();
  });

  // Input & Send
  DOM.btnSendMessage.addEventListener("click", () => handleSendMessage());
  DOM.candidateTextInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  });

  // STT text box auto-sync to input if typed in preview
  DOM.sttLiveTranscript.addEventListener("input", (e) => {
    DOM.candidateTextInput.value = e.target.value;
  });

  // Finish button
  DOM.btnFinish.addEventListener("click", () => handleFinishInterview());

  // Screen 3: Completed Actions
  DOM.btnCopyTranscript.addEventListener("click", copyTranscriptToClipboard);
  DOM.btnRestartInterview.addEventListener("click", resetToUploadScreen);
}

// --- TTS INTEGRATION ---
function setupTTSListeners() {
  window.ttsController.onStateChange((status, details) => {
    const dot = DOM.aiStatusIndicator.querySelector(".status-dot");
    dot.className = "status-dot";

    if (status === "SPEAKING") {
      dot.classList.add("speaking");
      DOM.aiStatusText.textContent = "AI SPEAKING";
      DOM.speakerWave.classList.add("active");
      DOM.ttsStatusLabel.textContent = "Speaking...";
      DOM.iconTtsPause.classList.remove("hidden");
      DOM.iconTtsPlay.classList.add("hidden");
      DOM.ttsBtnText.textContent = "Pause Voice";
    } else if (status === "PAUSED") {
      dot.classList.add("paused");
      DOM.aiStatusText.textContent = "AI PAUSED";
      DOM.speakerWave.classList.remove("active");
      DOM.ttsStatusLabel.textContent = "Voice Paused";
      DOM.iconTtsPause.classList.add("hidden");
      DOM.iconTtsPlay.classList.remove("hidden");
      DOM.ttsBtnText.textContent = "Resume Voice";
    } else {
      dot.classList.add("ready");
      DOM.aiStatusText.textContent = "AI READY";
      DOM.speakerWave.classList.remove("active");
      DOM.ttsStatusLabel.textContent = "Voice Ready";
      DOM.iconTtsPause.classList.remove("hidden");
      DOM.iconTtsPlay.classList.add("hidden");
      DOM.ttsBtnText.textContent = "Pause Voice";
    }
  });
}

// --- STT INTEGRATION ---
function setupSTTListeners() {
  window.sttController.onStateChange((stateName, details) => {
    if (stateName === "RECORDING") {
      DOM.btnToggleMic.classList.add("recording");
      DOM.sttPreviewCard.classList.remove("hidden");
      DOM.sttLiveTranscript.value = "";
      // If AI is currently speaking, pause speech to prevent feedback
      window.ttsController.pauseSpeech();
    } else {
      DOM.btnToggleMic.classList.remove("recording");
      // Transfer final transcript to candidate text input
      if (DOM.sttLiveTranscript.value.trim()) {
        DOM.candidateTextInput.value = DOM.sttLiveTranscript.value.trim();
      }
      setTimeout(() => {
        DOM.sttPreviewCard.classList.add("hidden");
      }, 600);
    }
  });

  window.sttController.onTranscriptUpdate((fullText) => {
    DOM.sttLiveTranscript.value = fullText;
    DOM.candidateTextInput.value = fullText;
  });

  window.sttController.onError((userMsg) => {
    alert(userMsg);
  });
}

// --- NAVIGATION / SCREEN SWITCHING ---
function switchScreen(screenName) {
  Object.keys(DOM.screens).forEach((key) => {
    DOM.screens[key].classList.toggle("hidden", key !== screenName);
    DOM.screens[key].classList.toggle("active", key === screenName);
  });

  if (screenName === "interview") {
    DOM.headerControls.classList.remove("hidden");
  } else {
    DOM.headerControls.classList.add("hidden");
  }
}

function loadDemoResume() {
  const sampleContent = `Alex Chen
Senior Distributed Systems Engineer
Email: alex.chen@example.com

Summary:
Full-stack and backend engineer with 6+ years of experience designing real-time distributed microservices, event streaming platforms with Apache Kafka, and RESTful APIs in FastAPI.

Technical Skills:
- Languages & Frameworks: Python, FastAPI, TypeScript, Node.js, Go
- Databases & Messaging: PostgreSQL, Redis, Apache Kafka, DynamoDB
- Infrastructure: Docker, Kubernetes, AWS (ECS, Lambda, S3), Terraform

Key Projects:
1. Real-Time Telemetry Pipeline:
   - Architected an event streaming platform processing 50,000 events/second using Kafka and FastAPI microservices.
   - Reduced p99 query latency from 320ms to 45ms through distributed Redis caching and database indexing.
   - Built automated failover mechanisms and circuit breakers for 99.99% system availability.

2. Cloud-Native Authentication Gateway:
   - Designed OAuth2 / JWT auth service handling 100k daily active users.`;

  const blob = new Blob([sampleContent], { type: "text/plain" });
  const file = new File([blob], "alex_chen_resume.txt", { type: "text/plain" });
  handleFileUpload(file);
}

// --- RESUME UPLOAD FLOW ---
async function handleFileUpload(file) {
  if (!file) return;

  const validExts = [".pdf", ".docx", ".txt"];
  const fileName = file.name.toLowerCase();
  const isValid = validExts.some((ext) => fileName.endsWith(ext));

  if (!isValid) {
    showUploadError("Invalid file type. Please upload a .pdf, .docx, or .txt file.");
    return;
  }

  DOM.uploadErrorAlert.classList.add("hidden");
  DOM.uploadStatusCard.classList.remove("hidden");
  DOM.uploadFilename.textContent = file.name;
  DOM.uploadProgressText.textContent = "Uploading & extracting resume data...";

  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch("/api/resume/upload", {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(err.detail || "Failed to parse resume.");
    }

    const data = await response.json();
    state.sessionId = data.session_id;
    state.candidateName = data.candidate_name || "Candidate";
    state.candidateProfile = data.candidate_profile || null;
    state.remainingSeconds = data.target_duration_seconds || 300;
    state.conversationHistory = [];

    DOM.headerCandidateName.textContent = state.candidateName;
    renderCandidateMemory(state.candidateProfile);

    // Transition to Interview Screen
    switchScreen("interview");

    // Add initial question to chat
    appendMessage("interviewer", data.initial_message, "INITIAL_QUESTION");
    state.conversationHistory.push({
      role: "interviewer",
      content: data.initial_message,
      timestamp: Date.now() / 1000,
      intent: "INITIAL_QUESTION"
    });

    // Speak initial question aloud
    window.ttsController.speak(data.initial_message);

    // Start Timer
    startCountdown();

  } catch (error) {
    console.error("Upload error:", error);
    showUploadError(error.message || "An error occurred while uploading your resume.");
    DOM.uploadStatusCard.classList.add("hidden");
  }
}

function renderCandidateMemory(profile) {
  if (!profile) return;
  state.candidateProfile = profile;

  DOM.memName.textContent = profile.candidate_name || "-";
  DOM.memTitle.textContent = profile.title || "-";
  DOM.memEmail.textContent = profile.email || "Not specified";

  // Skills
  DOM.memSkillsTags.innerHTML = "";
  if (profile.skills && profile.skills.length > 0) {
    profile.skills.forEach((s) => {
      const tag = document.createElement("span");
      tag.className = "skill-tag";
      tag.textContent = s;
      DOM.memSkillsTags.appendChild(tag);
    });
  } else {
    DOM.memSkillsTags.textContent = "None extracted";
  }

  // Projects
  DOM.memProjectsList.innerHTML = "";
  if (profile.projects && profile.projects.length > 0) {
    profile.projects.forEach((p) => {
      const pItem = document.createElement("div");
      pItem.className = "mem-project-item";
      const techBadges = p.technologies.map((t) => `<span class="mem-tech-pill">${escapeHTML(t)}</span>`).join("");
      const metricText = p.metrics ? `<div style="color: #6ee7b7; font-size: 0.75rem; margin-top: 2px;">⚡ ${escapeHTML(p.metrics)}</div>` : "";
      pItem.innerHTML = `
        <strong>${escapeHTML(p.name)}</strong>
        <p style="color: var(--text-muted); font-size: 0.75rem;">${escapeHTML(p.description || '')}</p>
        ${metricText}
        <div>${techBadges}</div>
      `;
      DOM.memProjectsList.appendChild(pItem);
    });
  } else {
    DOM.memProjectsList.textContent = "None extracted";
  }

  // Dynamic State
  DOM.memTopics.textContent = profile.topics_covered && profile.topics_covered.length > 0
    ? profile.topics_covered.join(", ")
    : "None yet";

  DOM.memStrengths.textContent = profile.evaluated_strengths && profile.evaluated_strengths.length > 0
    ? profile.evaluated_strengths.join(", ")
    : "Evaluating...";

  // Raw JSON
  DOM.memRawJson.textContent = JSON.stringify(profile, null, 2);
}

function showUploadError(message) {
  DOM.uploadErrorText.textContent = message;
  DOM.uploadErrorAlert.classList.remove("hidden");
}

// --- LIVE INTERVIEW TIMING ---
function startCountdown() {
  clearInterval(state.timerInterval);
  updateTimerUI();

  state.timerInterval = setInterval(() => {
    if (state.isPaused || state.isFinished) return;

    state.remainingSeconds -= 1;
    updateTimerUI();

    if (state.remainingSeconds <= 0) {
      clearInterval(state.timerInterval);
      state.isFinished = true;
      handleTimeExpired();
    }
  }, 1000);
}

function updateTimerUI() {
  const mins = Math.floor(Math.max(0, state.remainingSeconds) / 60);
  const secs = Math.max(0, state.remainingSeconds) % 60;
  const formatted = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  DOM.timerDisplay.textContent = formatted;

  DOM.timerCard.classList.remove("warning", "danger");
  if (state.remainingSeconds <= 60 && state.remainingSeconds > 20) {
    DOM.timerCard.classList.add("warning");
  } else if (state.remainingSeconds <= 20) {
    DOM.timerCard.classList.add("danger");
  }
}

async function handleTimeExpired() {
  window.ttsController.stopSpeech();
  const timeMsg = "Our 5-minute technical session time is complete. Let's wrap up!";
  appendMessage("interviewer", timeMsg, "INTERVIEW_WRAPUP");
  window.ttsController.speak(timeMsg);

  setTimeout(() => {
    handleFinishInterview();
  }, 3500);
}

// --- CONVERSATION PIPELINE (CANONICAL MESSAGE ENDPOINT) ---
async function handleSendMessage() {
  if (state.isSubmitting || state.isFinished) return;

  const rawMessage = DOM.candidateTextInput.value.trim();
  if (!rawMessage) return;

  // If mic is currently recording, stop it
  if (window.sttController.isRecording) {
    window.sttController.stop();
  }

  // Clear text input & set submitting state
  state.isSubmitting = true;
  DOM.btnSendMessage.disabled = true;
  DOM.candidateTextInput.value = "";
  DOM.candidateTextInput.placeholder = "AI is evaluating response...";

  // 1. Append candidate message to UI immediately
  appendMessage("candidate", rawMessage);
  state.conversationHistory.push({
    role: "candidate",
    content: rawMessage,
    timestamp: Date.now() / 1000
  });

  // 2. Stop any active TTS before getting new response
  window.ttsController.stopSpeech();

  try {
    // 3. Post to canonical endpoint
    const response = await fetch("/api/interview/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId,
        message: rawMessage
      })
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Message failed" }));
      throw new Error(err.detail || "Server error occurred");
    }

    const data = await response.json();

    // 4. Update timer & session memory
    if (typeof data.time_remaining_seconds === "number") {
      state.remainingSeconds = data.time_remaining_seconds;
      updateTimerUI();
    }
    if (data.candidate_memory) {
      renderCandidateMemory(data.candidate_memory);
    }

    // 5. Append interviewer response with intent badge
    appendMessage("interviewer", data.response_text, data.intent_classified, data.agent_used);
    state.conversationHistory.push({
      role: "interviewer",
      content: data.response_text,
      timestamp: Date.now() / 1000,
      intent: data.intent_classified,
      agent_used: data.agent_used
    });

    // 6. Speak response if enabled
    if (data.should_speak) {
      window.ttsController.speak(data.response_text);
    }

    // 7. Check if interview concluded
    if (data.is_finished) {
      state.isFinished = true;
      setTimeout(() => handleFinishInterview(), 4000);
    }

  } catch (error) {
    console.error("Message send error:", error);
    appendMessage("interviewer", `⚠️ Connection Error: ${error.message}. Please try again.`);
  } finally {
    state.isSubmitting = false;
    DOM.btnSendMessage.disabled = false;
    DOM.candidateTextInput.placeholder = "Type your response or click the microphone to speak...";
    DOM.candidateTextInput.focus();
  }
}

// --- UI MESSAGE RENDERING ---
function appendMessage(role, text, intent = null, agent = null) {
  const isInterviewer = role === "interviewer";
  const item = document.createElement("div");
  item.className = `message-item ${isInterviewer ? "interviewer" : "candidate"}`;

  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  let intentBadgeHtml = "";
  if (intent) {
    let badgeClass = "intent-badge";
    let label = intent;
    if (intent === "PROFILE_QUERY") {
      badgeClass += " profile";
      label = "Profile QA";
    } else if (intent === "INTERVIEW_META_QUERY") {
      badgeClass += " meta";
      label = "Meta Query";
    } else if (intent === "TECHNICAL_ANSWER") {
      label = "Tech Deep-Dive";
    } else if (intent === "INITIAL_QUESTION") {
      label = "Opening";
    }
    intentBadgeHtml = `<span class="${badgeClass}">${label}</span>`;
  }

  item.innerHTML = `
    <div class="avatar ${isInterviewer ? "interviewer-avatar" : "candidate-avatar"}">
      ${isInterviewer ? "AI" : "YOU"}
    </div>
    <div class="bubble">
      <div class="bubble-meta">
        <span class="speaker-name">
          ${isInterviewer ? "Technical Interviewer" : state.candidateName}
          ${intentBadgeHtml}
        </span>
        <span class="timestamp">${timeStr}</span>
      </div>
      <div class="message-content">${escapeHTML(text)}</div>
    </div>
  `;

  DOM.messagesList.appendChild(item);
  DOM.chatContainer.scrollTop = DOM.chatContainer.scrollHeight;
}

function escapeHTML(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// --- FINISH & COMPLETION SCREEN ---
async function handleFinishInterview() {
  state.isFinished = true;
  clearInterval(state.timerInterval);
  window.ttsController.stopSpeech();
  if (window.sttController.isRecording) window.sttController.stop();

  try {
    if (state.sessionId) {
      await fetch(`/api/interview/${state.sessionId}/finish`, { method: "POST" });
    }
  } catch (e) {
    console.warn("Could not mark session finished on server:", e);
  }

  // Populate completed stats
  const candidateTurns = state.conversationHistory.filter((m) => m.role === "candidate").length;
  DOM.statTurnsCount.textContent = candidateTurns;
  DOM.statCandidateName.textContent = state.candidateName;

  const elapsedSecs = 300 - Math.max(0, state.remainingSeconds);
  const eMins = Math.floor(elapsedSecs / 60);
  const eSecs = elapsedSecs % 60;
  DOM.statDuration.textContent = `${String(eMins).padStart(2, "0")}:${String(eSecs).padStart(2, "0")}`;

  // Populate transcript review
  DOM.finalTranscriptBody.innerHTML = "";
  state.conversationHistory.forEach((msg) => {
    const entry = document.createElement("div");
    entry.className = `transcript-entry ${msg.role}`;
    entry.innerHTML = `
      <strong>${msg.role === "interviewer" ? "AI Technical Interviewer" : state.candidateName}:</strong>
      <p>${escapeHTML(msg.content)}</p>
    `;
    DOM.finalTranscriptBody.appendChild(entry);
  });

  switchScreen("completed");
}

function copyTranscriptToClipboard() {
  const lines = state.conversationHistory.map((m) => {
    const speaker = m.role === "interviewer" ? "AI Interviewer" : state.candidateName;
    return `[${speaker}]:\n${m.content}\n`;
  });
  const text = lines.join("\n");

  navigator.clipboard.writeText(text).then(() => {
    DOM.btnCopyTranscript.textContent = "Copied!";
    setTimeout(() => {
      DOM.btnCopyTranscript.textContent = "Copy Transcript";
    }, 2000);
  });
}

function resetToUploadScreen() {
  state.sessionId = null;
  state.candidateName = "Candidate";
  state.remainingSeconds = 300;
  state.isPaused = false;
  state.isFinished = false;
  state.conversationHistory = [];
  state.isSubmitting = false;

  DOM.messagesList.innerHTML = "";
  DOM.uploadStatusCard.classList.add("hidden");
  DOM.uploadErrorAlert.classList.add("hidden");
  DOM.fileInput.value = "";

  switchScreen("upload");
}
