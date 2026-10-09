import os
import sys
import uuid
import json
from typing import List, Optional
from io import BytesIO

from pydantic import BaseModel, Field
import redis
from pypdf import PdfReader
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from langchain_google_genai import ChatGoogleGenerativeAI

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )