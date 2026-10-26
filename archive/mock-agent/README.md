# Real-Time AI Mock Interview Platform (FastAPI + Standalone Frontend)

A real-time, interactive technical mock interview application built with **FastAPI** and a modern **Vanilla JavaScript & CSS** frontend.

The system features:
- Dynamic resume upload & parsing (`.pdf`, `.docx`, `.txt`)
- Browser Text-to-Speech (TTS) with interactive Pause, Resume, and Mute
- Speech-to-Text (STT) voice input with editable live transcription preview
- Real-time 5-minute countdown timer with backend state synchronization
- Canonical unified message pipeline where both typed and voice inputs are normalized to text
- Modular AI conversation engine designed for drop-in replacement with **n8n / LLMs / LangGraph** without changing frontend code.

---

## 1. Project Structure

```text
mock-agent/
│
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   └── config.py              # Global settings, duration, and CORS config
│   │   ├── models/
│   │   │   └── schemas.py             # Pydantic models for request/response & state
│   │   ├── routes/
│   │   │   ├── resume.py              # POST /api/resume/upload endpoint
│   │   │   └── interview.py           # /api/interview endpoints (message, audio, state, finish)
│   │   ├── services/
│   │   │   ├── resume_service.py      # File parsing & candidate profile extractor
│   │   │   ├── session_store.py       # Thread-safe in-memory session manager
│   │   │   ├── interview_service.py   # Modular AI conversation engine (Mock & n8n)
│   │   │   └── speech_service.py      # Backend audio STT abstraction
│   │   └── main.py                    # FastAPI app initialization & static mount
│   └── requirements.txt
│
├── frontend/
│   ├── index.html                     # 3-screen interactive UI (Upload, Live Room, Completed)
│   ├── css/
│   │   └── style.css                  # Dark-mode glassmorphism styling & animations
│   └── js/
│       ├── tts.js                     # Isolated browser Text-to-Speech engine with pause/resume
│       ├── stt.js                     # Isolated Speech-to-Text engine with fallback abstraction
│       └── app.js                     # Main application controller & state coordinator
│
└── README.md
```

---

## 2. Frontend-to-FastAPI Communication Architecture

All communication occurs over REST JSON endpoints with standard HTTP `multipart/form-data` for file uploads:

```text
 ┌────────────────────────────────────────────────────────┐
 │                      FRONTEND                          │
 │  (Upload Screen ───► Live Room ───► Completed Screen)  │
 └──────────────────────────┬─────────────────────────────┘
                            │
               REST APIs (Fetch API / JSON)
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │                  FASTAPI BACKEND                       │
 │  ├── POST /api/resume/upload                           │
 │  ├── POST /api/interview/message  (Canonical Pipeline) │
 │  ├── POST /api/interview/audio    (Fallback STT)       │
 │  ├── GET  /api/interview/{id}     (Timer / State Sync) │
 │  └── POST /api/interview/{id}/finish                   │
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │               CONVERSATION ENGINE LAYER                │
 │  ├── MockInterviewService (Active Now)                 │
 │  └── N8NInterviewService  (Future Drop-in)             │
 └────────────────────────────────────────────────────────┘
```

---

## 3. Resume Data Storage

- When a resume (`.pdf`, `.docx`, or `.txt`) is uploaded to `POST /api/resume/upload`, `ResumeParserService` extracts plain text and extracts the candidate's name.
- A unique `session_id` (UUIDv4) is minted.
- The resume text is stored in the `InMemorySessionStore` keyed by `session_id`.
- The resume text persists in memory for the entire interview session. It is **never re-extracted** on each chat message.
- Later, when switching to persistent storage, `InMemorySessionStore` can be swapped with Redis or PostgreSQL without changing API signatures.

---

## 4. Conversation History Storage

- Each session object maintains an ordered list of `MessageItem` models:
  ```json
  [
    {
      "role": "interviewer",
      "content": "Let's start with your most challenging project...",
      "timestamp": 1740800000.0
    },
    {
      "role": "candidate",
      "content": "I designed an asynchronous microservice...",
      "timestamp": 1740800030.0
    }
  ]
  ```
- Every exchange (candidate message + interviewer reply) is appended to `conversation_history`.
- In the next phase, the complete history will be dispatched to n8n to provide context-aware LLM memory.

---

## 5. Text Input Pipeline

1. Candidate types an answer into `#candidate-text-input`.
2. Pressing <kbd>Enter</kbd> (or clicking Send) disables duplicate submission.
3. The message is immediately rendered in the UI conversation bubble.
4. The client dispatches `POST /api/interview/message` with `{ session_id, message }`.
5. FastAPI updates session history, queries `interview_service`, and returns `{ response_text, should_speak, time_remaining_seconds }`.
6. The frontend displays the AI response and triggers TTS speech.

---

## 6. Audio Input & 7. STT (Speech-to-Text)

- Microphones capture candidate voice using the dedicated `STTController` (`frontend/js/stt.js`).
- Speech is converted to text in real time:
  ```text
  Microphone ──► STTController (Web Speech API) ──► Live Transcript Preview ──► Candidate Text
  ```
- The candidate sees a live recording indicator (`🎙 Recording Voice Response...`) with a live editable transcript box.
- The candidate can edit the transcript before submitting.
- **Unified Pipeline**: Once submitted, the transcribed text is posted to the exact same `POST /api/interview/message` endpoint. The AI conversation engine only processes canonical text.

---

## 8. TTS (Text-to-Speech) & 9. Pause / Resume

- Isolated in `TTSController` (`frontend/js/tts.js`).
- When an AI response arrives, `ttsController.speak(response_text)` initiates speech.
- **True Pause & Resume**:
  - Clicking the **Pause Voice** button triggers `speechSynthesis.pause()`. The AI state indicator changes to `AI PAUSED` and the button changes to `Resume Voice`.
  - Clicking **Resume Voice** triggers `speechSynthesis.resume()`, continuing playback from the paused position without restarting from the beginning.
- **Safety**: If a new response arrives or candidate sends a message while speech is ongoing, `ttsController.stopSpeech()` cancels earlier speech cleanly to avoid overlapping voices.

---

## 10. How & Where to Connect n8n Later

The backend was specifically architected for instant n8n plug-in without touching any frontend code.

In `backend/app/services/interview_service.py`:
1. Change `INTERVIEW_ENGINE=n8n` in your environment (or `.env`).
2. Provide `N8N_WEBHOOK_URL=http://localhost:5678/webhook/interview-chat`.
3. `N8NInterviewService` will automatically send the full payload to your n8n workflow:
   ```json
   {
     "action": "next_message",
     "session_id": "...",
     "candidate_name": "...",
     "resume_text": "...",
     "conversation_history": [ ... ],
     "latest_candidate_message": "..."
   }
   ```
4. n8n processes the request with LLM/Memory and responds with `{ "response_text": "..." }`.
5. FastAPI returns this directly to the frontend.

---

## 11. Running the System Locally

### Step 1: Install Python Dependencies

```powershell
cd backend
python -m pip install -r requirements.txt
```

### Step 2: Start the FastAPI Server

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Step 3: Open in Browser

Visit: `http://127.0.0.1:8000` (FastAPI automatically mounts and serves the `frontend/` directory).

---

## 12. End-to-End Test Workflow

1. **Resume Upload**:
   - Drag & drop a `.pdf`, `.docx`, or `.txt` resume onto the upload card.
   - Observe parsing animation and automatic transition to the **Live Interview Screen**.
2. **Opening Question & TTS**:
   - The opening technical question appears in the chat and is spoken aloud.
   - Status pill displays `AI SPEAKING`.
3. **Pause & Resume TTS**:
   - Click `Pause Voice` -> Speech pauses, status pill displays `AI PAUSED`.
   - Click `Resume Voice` -> Speech resumes from where it was paused.
4. **Typed Candidate Answer**:
   - Type an architectural description into the text area and press <kbd>Enter</kbd>.
   - Candidate bubble appears, AI analyzes and replies with a deep-dive tradeoff follow-up.
5. **Voice Input (STT)**:
   - Click the microphone button -> Speak your answer -> Watch live transcription appear in the preview card.
   - Click Send -> Voice transcript is submitted via the canonical message pipeline.
6. **Countdown Timer**:
   - Observe countdown timer (`05:00` counting down) with color changes at warning/danger thresholds.
7. **Interview Wrap-Up**:
   - Click `Finish` (or let the 5-minute timer elapse) -> View the **Interview Completed** screen with session statistics and full formatted transcript.
