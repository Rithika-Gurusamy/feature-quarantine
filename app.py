import os
import sys
import uuid
import json
from typing import List, Optional
from io import BytesIO
from datetime import datetime, UTC

from pydantic import BaseModel, Field
import redis
from pypdf import PdfReader
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

app = FastAPI(title="Gemini Resume Processing Core")

# 1. System Initializations
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY environment variable missing!")
    sys.exit(1)

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.1,
    google_api_key=GEMINI_API_KEY
)

try:
    r = redis.Redis(
        host="localhost",
        port=6379,
        decode_responses=True
    )
    r.ping()
except redis.exceptions.ConnectionError:
    print("ERROR: Redis container is not running!")
    sys.exit(1)


# 2. Schema Definition for the Structured Resume Data
class ProjectItem(BaseModel):
    title: str = Field(description="Name of the project")
    highlights: List[str] = Field(
        description="Key technical achievements or bullet points for this project"
    )


class ResumeSchema(BaseModel):
    summary: str = Field(
        description="A brief professional overview of the individual"
    )
    skills: List[str] = Field(
        description="Core technical languages, frameworks, databases, or tools listed"
    )
    projects: List[ProjectItem] = Field(
        description="List of projects worked on"
    )
    certifications: List[str] = Field(
        description="List of courses, honors, or certificates earned"
    )


# 3. The Auto-Structuring Processing Endpoint
@app.post("/resume/upload")
async def upload_resume(
    conversation_id: Optional[str] = Form(
        None,
        description="Provide an existing conv_id, or leave blank to generate a new one"
    ),
    file: UploadFile = File(
        ...,
        description="Upload candidate resume PDF file"
    )
):
    # Step A: Resolve Session Identity
    conv_id = conversation_id or f"conv_{uuid.uuid4().hex[:6]}"

    # Step B: Verify File Type
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported."
        )

    try:
        # Step C: Extract Raw Text from Binary PDF Stream
        pdf_bytes = await file.read()

        # Read the file from memory without saving it to disk
        reader = PdfReader(BytesIO(pdf_bytes))

        raw_text = ""

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                raw_text += page_text + "\n"

        if not raw_text.strip():
            raise HTTPException(
                status_code=422,
                detail="Failed to extract any text elements from this PDF."
            )

        # Step D: Force Gemini to enforce our Resume Schema structure
        structured_llm = llm.with_structured_output(ResumeSchema)

        extraction_prompt = (
            "Analyze the following raw, messy resume text. Extract and organize "
            "the data cleanly into the requested schema framework. Fix minor "
            "layout spacing issues or broken characters.\n\n"
            f"--- RAW RESUME TEXT ---\n{raw_text}"
        )

        # Gemini executes the structuring task
        structured_data: ResumeSchema = structured_llm.invoke(
            extraction_prompt
        )

        # Step E: Save the parsed JSON data to the Redis Profile Key
        profile_key = f"profile:{conv_id}:resume"

        r.set(
            profile_key,
            json.dumps(structured_data.model_dump())
        )

        return {
            "status": "Success",
            "conversation_id": conv_id,
            "redis_key": profile_key,
            "extracted_data": structured_data
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Processing Pipeline Failed: {str(e)}"
        )

# Request and response validation contracts for the chat
class ChatRequest(BaseModel):
    message: str
    conversation_id: str
    parent_id: Optional[str] = None

class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    parent_id: str
    response: str

# Helper method to format keys consistently within the app context
def get_conversation_list_key(conversation_id: str) -> str:
    return f"conversation:{conversation_id}:messages"

def get_message_key(message_id: str) -> str:
    return f"message:{message_id}"

# Endpoint to carry out the interactive chat using the Redis profile state
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    conv_id = payload.conversation_id
    
    # 1. Pull the structured resume profile from Redis
    profile_key = f"profile:{conv_id}:resume"
    raw_profile = r.get(profile_key)
    
    if not raw_profile:
        raise HTTPException(
            status_code=404, 
            detail=f"No resume profile found for conversation_id '{conv_id}'. Upload a resume first."
        )
    
    resume_context = json.loads(raw_profile)
    
        # 2. Dynamically inject the resume data straight into the System Prompt rulebook
    system_instruction = (
        "You are a seasoned, empathetic, yet highly precise Senior Backend Engineering Manager conducting a technical interview.\n"
        f"Here is the candidate's structured resume data:\n{json.dumps(resume_context, indent=2)}\n\n"
        "YOUR CORE INSTRUCTIONS:\n"
        "1. BE CONVERSATIONAL: Do not act like a static FAQ system or machine gun questions. Acknowledge and briefly evaluate the candidate's previous response naturally (e.g., 'That's a solid approach to OCR caching, but...').\n"
        "2. PROGRESSIVE DIFFICULTY: Test their technical domain skills (Python, FastAPI, SQL, etc.) fluidly. Start with baseline conceptual questions and naturally scale up to intermediate implementation realities based on their responses.\n"
        "3. DEEP PROJECT FOCUS: Anchor your line of questioning heavily onto their specific listed projects (like the Semantic Form Autofill or Smart DevTool). Ask how they handled architectural tradeoffs, security boundaries, breaking changes, or edge cases.\n"
        "4. ASK ONE QUESTION AT A TIME: Never bundle multiple questions together. Wait for their response before moving the dialogue forward.\n"
        "5. DURATION: Continue the interview organically, shifting topics smoothly across their backend/GenAI portfolio, until the user explicitly states they want to stop.\n\n"
        "6.Ask them questions regarding the courses/certifications they have completed , ask them questions on that\nS"
        "Maintain a highly professional, encouraging, yet technically demanding conversational tone."
    )

    # 3. Log the incoming user response into the Redis message tree store
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
    
    # 4. Extract historical dialog logs out of Redis
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
                
    # 5. Fire request payload to Gemini API over network interface
    try:
        ai_response = llm.invoke(llm_payload)
        
        # 6. Save the AI response back into the Redis storage layer
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

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )