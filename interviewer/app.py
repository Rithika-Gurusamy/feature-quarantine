import os
import sys
import uuid
import json
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

app = FastAPI(title="Gemini Resume Interview Platform")

# ── Serve the frontend ──────────────────────────────────────
# Mount the static/ directory so the browser can load style.css and app.js
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pull the Gemini API key from the system environment
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY environment variable not found!")
    sys.exit(1)

# Initialize the Gemini Language Model client
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",  
    temperature=0.7,
    google_api_key=GEMINI_API_KEY
)

# Connect to the local Redis instance running inside Docker
try:
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    r.ping()
except redis.exceptions.ConnectionError:
    print("ERROR: Could not connect to Redis!")
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
    file: UploadFile = File(..., description="Upload candidate resume PDF file")
):
    conv_id = conversation_id or f"conv_{uuid.uuid4().hex[:6]}"
    
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    try:
        # Extract raw text lines from the uploaded binary PDF stream
        pdf_bytes = await file.read()
        reader = PdfReader(BytesIO(pdf_bytes))
        
        raw_text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                raw_text += page_text + "\n"
                
        if not raw_text.strip():
            raise HTTPException(status_code=422, detail="Failed to extract text elements from this PDF.")

        # Bind the strict Pydantic structure layer to the Gemini client
        structured_llm = llm.with_structured_output(ResumeSchema)
        
        extraction_prompt = (
            "Analyze the following raw resume text. Extract and organize the data cleanly "
            "into the requested schema framework.\n\n"
            f"--- RAW RESUME TEXT ---\n{raw_text}"
        )
        
        structured_data = structured_llm.invoke(extraction_prompt)
        
        # Save the structured profile object directly into its own Redis key
        profile_key = f"profile:{conv_id}:resume"
        r.set(profile_key, json.dumps(structured_data.model_dump()))
        
        return {
            "status": "Success",
            "conversation_id": conv_id,
            "extracted_data": structured_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing Pipeline Failed: {str(e)}")

# Endpoint to conduct the stateful mock interview using rolling history and the resume profile
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    conv_id = payload.conversation_id
    
    # Fetch the candidate's structured profile out of the Redis cache store
    profile_key = f"profile:{conv_id}:resume"
    raw_profile = r.get(profile_key)
    
    if not raw_profile:
        raise HTTPException(status_code=404, detail="No resume profile found. Please upload a resume first.")
    
    resume_context = json.loads(raw_profile)
    
    # Establish the senior manager persona and dynamically inject the resume profile context
    system_instruction = (
        "You are a seasoned, empathetic, yet highly precise Senior Backend Engineering Manager conducting a technical interview.\n"
        f"Here is the candidate's structured resume data:\n{json.dumps(resume_context, indent=2)}\n\n"
        "YOUR CORE INSTRUCTIONS:\n"
        "1. BE CONVERSATIONAL: Acknowledge and briefly evaluate the candidate's previous response naturally.\n"
        "2. PROGRESSIVE DIFFICULTY: Test domain skills from baseline concepts up to intermediate implementation realities.\n"
        "3. DEEP PROJECT FOCUS: Anchor your line of questioning heavily onto their specific listed projects and architectural tradeoffs.\n"
        "4. ASK ONE QUESTION AT A TIME: Wait for their response before moving the dialogue forward.\n"
        "5. DURATION: Continue the interview organically until the user explicitly states they want to stop.\n\n"
        "Maintain a highly professional, encouraging, yet technically demanding conversational tone."
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
                
    # Invoke Gemini with complete context and log the final answer string back to Redis
    try:
        ai_response = llm.invoke(llm_payload)
        
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
        
        return ChatResponse(
            conversation_id=conv_id,
            message_id=ai_msg_id,
            parent_id=user_msg_id,
            response=ai_response.content
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Chat Error: {str(e)}")
