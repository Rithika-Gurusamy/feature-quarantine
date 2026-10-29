
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
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from dotenv import load_dotenv

# ── Load environment variables (.env in workspace root or current dir) ──
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
load_dotenv()

app = FastAPI(title="Gemini Resume Interview Platform")

# ── Serve the frontend ──────────────────────────────────────
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def serve_index():
    """Serve index.html at the root URL."""
    index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    return FileResponse(index_path)

# ── CORS ────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pull the Gemini API key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY environment variable not found in system or .env file!")
    sys.exit(1)

# Initialize the Gemini Language Model client
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",  
    temperature=0.7,
    google_api_key=GEMINI_API_KEY
)

# Connect to the local Redis instance
try:
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    r.ping()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [INIT] Connected to Redis on localhost:6379")
except redis.exceptions.ConnectionError as err:
    print(f"ERROR: Could not connect to Redis: {err}")
    sys.exit(1)

# Pydantic schemas to strictly enforce Gemini's data extraction output
class ProjectItem(BaseModel):
    title: str = Field(description="Name of the project")
    highlights: List[str] = Field(description="Key technical achievements or bullet points")

class ResumeSchema(BaseModel):
    summary: str = Field(description="A brief professional overview of the individual")
    skills: List[str] = Field(description="Core technical languages, frameworks, or tools")
    projects: List[ProjectItem] = Field(description="List of projects worked on")
    certifications: List[str] = Field(description="List of courses or certificates earned")

# Request and response data schemas for the interview endpoint
class ChatRequest(BaseModel):
    message: str
    conversation_id: str
    parent_id: Optional[str] = None
    target_role: Optional[str] = None

class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    parent_id: str
    response: str

# Helper methods to format key namespaces consistently in Redis
def get_conversation_list_key(conversation_id: str) -> str:
    return f"conversation:{conversation_id}:messages"

def get_message_key(message_id: str) -> str:
    return f"message:{message_id}"

# Endpoint to upload a PDF resume, extract text, and save structured JSON to Redis
@app.post("/resume/upload")
async def upload_resume(
    conversation_id: Optional[str] = Form(None, description="Existing conv_id, or leave blank to generate a new one"),
    target_role: Optional[str] = Form(None, description="Optional target job role specified by candidate"),
    file: UploadFile = File(..., description="Upload candidate resume PDF file")
):
    conv_id = conversation_id or f"conv_{uuid.uuid4().hex[:6]}"
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{timestamp}] [RESUME UPLOAD] New upload request:")
    print(f"  • Filename: {file.filename}")
    print(f"  • Target Role: {target_role or '(None specified)'}")
    print(f"  • Session ID: {conv_id}")
    
    if not file.filename.lower().endswith('.pdf'):
        print(f"  [ERROR] Rejected non-PDF file: {file.filename}")
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    try:
        # Extract raw text lines from the uploaded binary PDF stream
        pdf_bytes = await file.read()
        print(f"  • Read {len(pdf_bytes):,} bytes. Extracting text from PDF pages...")
        
        reader = PdfReader(BytesIO(pdf_bytes))
        total_pages = len(reader.pages)
        
        raw_text = ""
        for i, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                raw_text += page_text + "\n"
                
        print(f"  • Extracted {len(raw_text):,} characters of text from {total_pages} page(s).")
                
        if not raw_text.strip():
            print(f"  [ERROR] No text extracted. File may be an image scan or flattened PDF.")
            raise HTTPException(
                status_code=422,
                detail="Failed to extract readable text elements from this PDF. Please ensure the PDF is text-selectable and not a scanned image."
            )

        # Bind the strict Pydantic structure layer to the Gemini client
        print(f"  • Prompting Gemini (gemini-2.5-flash) for structured extraction (async)...")
        structured_llm = llm.with_structured_output(ResumeSchema)
        
        extraction_prompt = (
            "Analyze the following raw resume text. Extract and organize the data cleanly "
            "into the requested schema framework.\n\n"
            f"--- RAW RESUME TEXT ---\n{raw_text}"
        )
        
        t0 = datetime.now()
        # Using asynchronous ainvoke so FastAPI event loop is NOT blocked
        structured_data = await structured_llm.ainvoke(extraction_prompt)
        elapsed = (datetime.now() - t0).total_seconds()
        print(f"  • Structured profile extracted by Gemini in {elapsed:.1f}s")
        
        # Save the structured profile object directly into its own Redis key
        profile_dict = structured_data.model_dump()
        if target_role and target_role.strip():
            profile_dict["target_role"] = target_role.strip()

        profile_key = f"profile:{conv_id}:resume"
        r.set(profile_key, json.dumps(profile_dict))
        print(f"  • Saved profile to Redis key '{profile_key}' successfully.")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [RESUME UPLOAD] Complete! Returning success to client.\n")
        
        return {
            "status": "Success",
            "conversation_id": conv_id,
            "extracted_data": profile_dict
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"  [EXCEPTION] Processing Pipeline Failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Processing Pipeline Failed: {str(e)}")

# Endpoint to conduct the stateful mock interview using rolling history and the resume profile
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    conv_id = payload.conversation_id
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{timestamp}] [CHAT REQUEST] conv_id: '{conv_id}'")
    print(f"  • User message: \"{payload.message[:80]}{'...' if len(payload.message) > 80 else ''}\"")
    
    # Fetch the candidate's structured profile out of the Redis cache store
    profile_key = f"profile:{conv_id}:resume"
    raw_profile = r.get(profile_key)
    
    if not raw_profile:
        print(f"  [ERROR] No profile found in Redis for key '{profile_key}'")
        raise HTTPException(status_code=404, detail="No resume profile found. Please upload a resume first.")
    
    resume_context = json.loads(raw_profile)
    
    # If a target role was explicitly supplied in this request, persist it to the session profile
    if payload.target_role and payload.target_role.strip():
        resume_context["target_role"] = payload.target_role.strip()
        r.set(profile_key, json.dumps(resume_context))
    
    target_role_clause = ""
    if resume_context.get("target_role"):
        target_role_clause = f"TARGET ROLE SPECIFIED BY CANDIDATE: {resume_context['target_role']}\n"

    # Adaptive, domain-aware technical interviewer system instruction
    system_instruction = (
        "You are an experienced, adaptive Technical Interviewer conducting a realistic, professional technical assessment.\n\n"
        f"{target_role_clause}"
        f"CANDIDATE STRUCTURED RESUME DATA:\n{json.dumps(resume_context, indent=2)}\n\n"
        "YOUR CORE OPERATING INSTRUCTIONS:\n"
        "1. ADAPTIVE TECHNICAL PERSONA:\n"
        "   • If a target role is specified above, conduct the interview strictly aligned with that technical domain.\n"
        "   • If no target role is explicitly provided, infer the candidate's primary technical focus (e.g., Frontend, Backend, Full Stack, Data Science, AI/ML, DevOps, Mobile, QA) directly from their listed skills, projects, and technologies.\n"
        "   • If the resume covers multiple domains (e.g., Full Stack), explore both frontend and backend concepts relevant to their experience.\n"
        "   • If the resume information is ambiguous or insufficient to determine an intended technical focus, ask the candidate at the beginning to clarify their target role rather than assuming or inventing one.\n"
        "   • NEVER assume every candidate is a backend developer or default to backend systems. Adapt your expertise to match the candidate's domain.\n\n"
        "2. GROUNDED IN REAL PROJECTS & SKILLS:\n"
        "   • Anchor your technical questions directly to the actual projects, technical stacks, tools, and design decisions detailed in the resume.\n"
        "   • Do NOT invent technologies, tools, metrics, libraries, or experiences absent from the candidate's background.\n"
        "   • Calibrate question complexity to the candidate's demonstrated experience level; avoid assigning an unsupported seniority level.\n\n"
        "3. CONVERSATIONAL CONTINUITY & INTERVIEW PROGRESSION:\n"
        "   • Actively acknowledge and briefly evaluate the candidate's previous response naturally before asking your next question.\n"
        "   • Ask insightful, relevant follow-up questions that probe technical trade-offs, edge cases, implementation decisions, and architectural rationales.\n"
        "   • Do NOT repeat questions that have already been asked or answered in the conversation history.\n"
        "   • Ask ONE question at a time. Wait for the candidate's response before moving forward.\n"
        "   • Continue the interview organically until the candidate indicates they wish to conclude.\n\n"
        "Maintain an encouraging, highly professional, realistic, and technically demanding interviewing style."
    )
    
    # Save the user's incoming statement to the tracking tree inside Redis
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
    
    # Extract the historical transaction logs array from Redis
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
                
    # Invoke Gemini asynchronously with complete context and log the final answer string back to Redis
    try:
        print(f"  • Prompting Gemini with conversation history ({len(llm_payload)} messages)...")
        t0 = datetime.now()
        ai_response = await llm.ainvoke(llm_payload)
        elapsed = (datetime.now() - t0).total_seconds()
        print(f"  • AI response generated in {elapsed:.1f}s")
        
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
        print(f"  • Message stored in Redis. Returning response to client.\n")
        
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
