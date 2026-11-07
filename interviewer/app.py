import os
import sys
import uuid
import json
import traceback
from datetime import datetime, UTC
from io import BytesIO
from typing import List, Optional
from pydantic import BaseModel, Field
import redis
from pypdf import PdfReader
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from dotenv import load_dotenv

# ── Load environment variables from .env ──────────────────────
# Try root .env, then interviewer/.env, then system environment
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
load_dotenv()

app = FastAPI(
    title="Gemini Resume Interview Platform",
    description="Adaptive AI Technical Interviewer powered by Google Gemini and Redis."
)

# ── Serve static assets & frontend ────────────────────────────
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", tags=["Frontend"])
async def serve_index():
    """Serve index.html at the root URL."""
    index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    return FileResponse(index_path)

# ── CORS Middleware ───────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── HTTP Request Logging Middleware ───────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Logs every incoming HTTP request with method, path, status, and duration."""
    start_time = datetime.now()
    response = await call_next(request)
    duration = (datetime.now() - start_time).total_seconds()
    timestamp = datetime.now().strftime("%H:%M:%S")
    # Avoid cluttering logs with static asset fetches
    if not request.url.path.startswith("/static"):
        print(f"[{timestamp}] [HTTP] {request.method} {request.url.path} -> {response.status_code} ({duration:.2f}s)")
    return response

# ── Validate & Initialize Gemini ──────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("\n" + "=" * 60)
    print(" [ERROR] GEMINI_API_KEY environment variable not found!")
    print(" Please set GEMINI_API_KEY in your .env file or environment.")
    print("=" * 60 + "\n")
    sys.exit(1)

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.7,
    google_api_key=GEMINI_API_KEY
)

# ── Connect to Redis ──────────────────────────────────────────
try:
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    r.ping()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [INIT] Connected successfully to Redis on localhost:6379")
except redis.exceptions.ConnectionError as err:
    print("\n" + "=" * 60)
    print(f" [ERROR] Could not connect to Redis: {err}")
    print(" Please ensure Redis is running (e.g. `docker run -d -p 6379:6379 redis:alpine`)")
    print("=" * 60 + "\n")
    sys.exit(1)

# ── Pydantic Schemas ──────────────────────────────────────────
class ProjectItem(BaseModel):
    title: str = Field(description="Name or title of the project")
    highlights: List[str] = Field(description="Key technical achievements, stack, or bullet points")

class ResumeSchema(BaseModel):
    summary: str = Field(description="A concise professional summary of the candidate")
    skills: List[str] = Field(description="Core technical skills, programming languages, frameworks, or tools")
    projects: List[ProjectItem] = Field(default_factory=list, description="List of key technical projects")
    certifications: List[str] = Field(default_factory=list, description="Courses, certifications, or credentials earned")
    inferred_role: str = Field(
        description=(
            "The primary target job role inferred strictly from the resume content — "
            "e.g. 'Frontend Engineer', 'Full Stack Developer', 'Backend Engineer', 'Data Scientist', 'DevOps Engineer'. "
            "Never assume backend by default; adapt strictly to the actual projects and technologies in the resume."
        )
    )

class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    parent_id: Optional[str] = None

class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    parent_id: str
    response: str

# ── Redis Key Helpers ─────────────────────────────────────────
def get_conversation_list_key(conversation_id: str) -> str:
    return f"conversation:{conversation_id}:messages"

def get_message_key(message_id: str) -> str:
    return f"message:{message_id}"

def get_profile_key(conversation_id: str) -> str:
    return f"profile:{conversation_id}:resume"

# ── GET /api/health ───────────────────────────────────────────
@app.get("/api/health", tags=["System"])
async def health_check():
    """Health check endpoint used by frontend to verify backend & Redis status."""
    redis_alive = False
    try:
        redis_alive = bool(r.ping())
    except Exception:
        pass

    return {
        "status": "healthy" if redis_alive and GEMINI_API_KEY else "degraded",
        "redis_connected": redis_alive,
        "gemini_configured": bool(GEMINI_API_KEY),
        "model": "gemini-2.5-flash",
        "server_time": datetime.now(UTC).isoformat()
    }

# ── POST /resume/upload ───────────────────────────────────────
@app.post("/resume/upload", tags=["Interview"])
async def upload_resume(
    conversation_id: Optional[str] = Form(None, description="Existing conv_id or blank to generate new"),
    file: UploadFile = File(..., description="PDF resume file")
):
    """
    Accepts candidate PDF resume, parses selectable text, extracts structured profile
    (including auto-inferred job role) using Gemini, and saves to Redis.
    """
    conv_id = conversation_id or f"conv_{uuid.uuid4().hex[:6]}"
    timestamp = datetime.now().strftime("%H:%M:%S")

    print("\n" + "─" * 60)
    print(f"[{timestamp}] [RESUME UPLOAD] Received new resume file:")
    print(f"  • Filename        : {file.filename}")
    print(f"  • Content-Type    : {file.content_type}")
    print(f"  • Conversation ID : {conv_id}")

    if not file.filename.lower().endswith('.pdf'):
        print(f"  [ERROR] Upload rejected: File '{file.filename}' is not a PDF.")
        raise HTTPException(status_code=400, detail="Only PDF files (.pdf) are supported.")

    try:
        # Read uploaded binary stream
        pdf_bytes = await file.read()
        file_size_kb = len(pdf_bytes) / 1024
        print(f"  • File size       : {file_size_kb:.1f} KB ({len(pdf_bytes):,} bytes)")

        # Extract text using pypdf
        reader = PdfReader(BytesIO(pdf_bytes))
        total_pages = len(reader.pages)
        print(f"  • Total PDF pages : {total_pages}")

        raw_text = ""
        for page_idx, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                raw_text += page_text + "\n"
                print(f"    - Page {page_idx}: extracted {len(page_text):,} chars")

        total_chars = len(raw_text.strip())
        print(f"  • Total extracted text: {total_chars:,} characters")

        if not raw_text.strip():
            print("  [ERROR] Zero text extracted. The uploaded PDF is likely a scanned image or flattened vector.")
            raise HTTPException(
                status_code=422,
                detail=(
                    "Failed to extract readable text from this PDF. "
                    "The file appears to be a scanned image or flattened document. "
                    "Please upload a PDF with selectable, copyable text."
                )
            )

        # Call Gemini for structured extraction
        print(f"  • Prompting Gemini (gemini-2.5-flash) with structured ResumeSchema (async)...")
        structured_llm = llm.with_structured_output(ResumeSchema)

        extraction_prompt = (
            "Analyze the following raw resume text carefully. "
            "Extract and organize the data cleanly into the requested schema.\n"
            "CRITICAL: Infer the candidate's primary target job role strictly from their actual skills, "
            "projects, and technical achievements. Do not guess or invent a role unsupported by the text.\n\n"
            f"--- RAW RESUME TEXT ---\n{raw_text}"
        )

        t0 = datetime.now()
        structured_data = await structured_llm.ainvoke(extraction_prompt)
        elapsed = (datetime.now() - t0).total_seconds()

        print(f"  • Gemini extraction completed in {elapsed:.2f}s")
        print(f"  • Inferred Role   : '{structured_data.inferred_role}'")
        print(f"  • Skills Found    : {len(structured_data.skills)} skills ({', '.join(structured_data.skills[:6])}...)")
        print(f"  • Projects Found  : {len(structured_data.projects)} project(s)")
        print(f"  • Certifications  : {len(structured_data.certifications)} item(s)")

        # Persist structured profile to Redis
        profile_dict = structured_data.model_dump()
        profile_key = get_profile_key(conv_id)
        r.set(profile_key, json.dumps(profile_dict))
        print(f"  • Profile saved to Redis key: '{profile_key}'")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [RESUME UPLOAD] Pipeline complete. Returning profile to client.")
        print("─" * 60 + "\n")

        return {
            "status": "Success",
            "conversation_id": conv_id,
            "extracted_data": profile_dict
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"  [EXCEPTION] Resume Processing Failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Resume Processing Pipeline Failed: {str(e)}")

# ── POST /chat ────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse, tags=["Interview"])
async def chat_endpoint(payload: ChatRequest):
    """
    Main stateful technical interview conversation endpoint.
    Maintains rolling dialog history in Redis and prompts Gemini with candidate background.
    """
    conv_id = payload.conversation_id
    timestamp = datetime.now().strftime("%H:%M:%S")

    print("\n" + "─" * 60)
    print(f"[{timestamp}] [CHAT REQUEST] conv_id: '{conv_id}'")
    msg_preview = payload.message[:90] + ("..." if len(payload.message) > 90 else "")
    print(f"  • Candidate Message : \"{msg_preview}\"")

    # Fetch candidate profile from Redis
    profile_key = get_profile_key(conv_id)
    raw_profile = r.get(profile_key)

    if not raw_profile:
        print(f"  [ERROR] No resume profile found in Redis for key '{profile_key}'")
        raise HTTPException(
            status_code=404,
            detail="No resume profile found for this conversation. Please upload a resume first."
        )

    resume_context = json.loads(raw_profile)
    inferred_role = resume_context.get("inferred_role", "Software Engineer")
    print(f"  • Inferred Role     : '{inferred_role}'")

    role_clause = f"CANDIDATE'S TARGET DOMAIN & ROLE (inferred from resume): {inferred_role}\n"

    # Construct expert technical interviewer system instructions
    system_instruction = (
        "You are an experienced, adaptive Senior Technical Interviewer conducting a realistic, professional technical assessment.\n\n"
        f"{role_clause}"
        f"CANDIDATE STRUCTURED RESUME DATA:\n{json.dumps(resume_context, indent=2)}\n\n"
        "YOUR CORE OPERATING INSTRUCTIONS:\n"
        "1. ADAPTIVE TECHNICAL PERSONA:\n"
        f"   • Conduct the interview tailored to the candidate's inferred role: {inferred_role}.\n"
        "   • If the resume covers multiple domains (e.g. Full Stack), balance frontend, backend, and architectural topics.\n"
        "   • Calibrate question depth to the candidate's demonstrated project complexity and seniority.\n"
        "   • NEVER assume every candidate is a backend developer. Adapt questions strictly to their stated tech stack.\n\n"
        "2. GROUNDED IN REAL PROJECTS & IMPLEMENTATION DETAILS:\n"
        "   • Anchor technical questions in the actual projects, libraries, frameworks, and architecture described in their resume.\n"
        "   • Ask about specific technical trade-offs, scalability bottlenecks, state management, API designs, or edge cases.\n"
        "   • Do NOT invent fictitious technologies, companies, or experiences absent from their background.\n\n"
        "3. CONVERSATIONAL CONTINUITY & INTERVIEW PROGRESSION:\n"
        "   • Acknowledge and briefly critique/evaluate the candidate's previous response before moving to the next question.\n"
        "   • Ask ONE clear question at a time. Never dump multiple unrelated questions in one turn.\n"
        "   • If the candidate's answer is brief or lacks depth, probe deeper with a relevant follow-up question.\n"
        "   • If the candidate indicates they wish to finish or ask questions, offer constructive feedback and wrap up.\n\n"
        "Maintain an encouraging, highly professional, realistic, and technically rigorous interviewing style."
    )

    # Save user message to Redis
    user_msg_id = f"msg_{uuid.uuid4().hex[:8]}"
    user_message_data = {
        "message_id": user_msg_id,
        "conversation_id": conv_id,
        "parent_id": payload.parent_id or "",
        "role": "user",
        "content": payload.message,
        "timestamp": datetime.now(UTC).isoformat()
    }
    r.set(get_message_key(user_msg_id), json.dumps(user_message_data))
    r.rpush(get_conversation_list_key(conv_id), user_msg_id)

    # Retrieve full conversation history from Redis
    message_ids = r.lrange(get_conversation_list_key(conv_id), 0, -1)
    llm_payload = [SystemMessage(content=system_instruction)]

    for msg_id in message_ids:
        raw_msg = r.get(get_message_key(msg_id))
        if raw_msg:
            msg_data = json.loads(raw_msg)
            if msg_data["role"] == "user":
                llm_payload.append(HumanMessage(content=msg_data["content"]))
            elif msg_data["role"] == "assistant":
                llm_payload.append(AIMessage(content=msg_data["content"]))

    turn_count = len(message_ids)
    print(f"  • Conversation Turn : #{turn_count} ({len(llm_payload)} messages in LLM context)")

    # Call Gemini asynchronously
    try:
        print(f"  • Sending request to Gemini (gemini-2.5-flash)...")
        t0 = datetime.now()
        ai_response = await llm.ainvoke(llm_payload)
        elapsed = (datetime.now() - t0).total_seconds()
        print(f"  • Gemini responded in {elapsed:.2f}s ({len(ai_response.content):,} characters)")

        ai_msg_preview = ai_response.content[:90].replace('\n', ' ') + ("..." if len(ai_response.content) > 90 else "")
        print(f"  • AI Response       : \"{ai_msg_preview}\"")

        # Save AI reply to Redis
        ai_msg_id = f"msg_{uuid.uuid4().hex[:8]}"
        ai_message_data = {
            "message_id": ai_msg_id,
            "conversation_id": conv_id,
            "parent_id": user_msg_id,
            "role": "assistant",
            "content": ai_response.content,
            "timestamp": datetime.now(UTC).isoformat()
        }
        r.set(get_message_key(ai_msg_id), json.dumps(ai_message_data))
        r.rpush(get_conversation_list_key(conv_id), ai_msg_id)
        print(f"  • Stored assistant reply in Redis (key: {get_message_key(ai_msg_id)})")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [CHAT REQUEST] Completed successfully.")
        print("─" * 60 + "\n")

        return ChatResponse(
            conversation_id=conv_id,
            message_id=ai_msg_id,
            parent_id=user_msg_id,
            response=ai_response.content
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"  [EXCEPTION] LLM Chat Error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"LLM Chat Error: {str(e)}")

# ── GET /api/session/{conversation_id} ────────────────────────
@app.get("/api/session/{conversation_id}", tags=["Interview"])
async def get_session_history(conversation_id: str):
    """Fetches full session details including extracted resume profile and all conversation messages."""
    profile_key = get_profile_key(conversation_id)
    raw_profile = r.get(profile_key)

    if not raw_profile:
        raise HTTPException(status_code=404, detail="Session not found.")

    profile = json.loads(raw_profile)
    message_ids = r.lrange(get_conversation_list_key(conversation_id), 0, -1)
    messages = []
    for msg_id in message_ids:
        raw_msg = r.get(get_message_key(msg_id))
        if raw_msg:
            messages.append(json.loads(raw_msg))

    return {
        "conversation_id": conversation_id,
        "profile": profile,
        "messages": messages
    }
