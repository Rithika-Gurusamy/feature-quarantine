from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

IntentType = Literal[
    "PROFILE_QUERY",         # Candidate asks about their own resume, skills, name, projects
    "TECHNICAL_ANSWER",      # Candidate answers technical question / system design
    "INTERVIEW_META_QUERY",  # Candidate asks about time left, interview format, repeating question
    "GENERAL_CONVERSATION"   # Greetings, thanks, or general remarks
]

class CandidateProject(BaseModel):
    name: str
    technologies: List[str] = []
    metrics: str = ""
    description: str = ""

class CandidateProfile(BaseModel):
    candidate_name: str = "Candidate"
    title: str = "Software Engineer"
    email: Optional[str] = None
    summary: str = ""
    skills: List[str] = []
    projects: List[CandidateProject] = []
    experience_highlights: List[str] = []
    topics_covered: List[str] = []
    evaluated_strengths: List[str] = []

class MessageItem(BaseModel):
    role: Literal["interviewer", "candidate", "system"]
    content: str
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())
    intent: Optional[str] = None
    agent_used: Optional[str] = None

class ResumeUploadResponse(BaseModel):
    session_id: str
    candidate_name: str
    resume_uploaded: bool
    initial_message: str
    target_duration_seconds: int = 300
    candidate_profile: Optional[CandidateProfile] = None

class InterviewMessageRequest(BaseModel):
    session_id: str
    message: str

class InterviewMessageResponse(BaseModel):
    session_id: str
    response_text: str
    message_type: str = "interviewer"
    should_speak: bool = True
    time_remaining_seconds: int
    is_finished: bool = False
    intent_classified: Optional[str] = None
    agent_used: Optional[str] = None
    candidate_memory: Optional[CandidateProfile] = None

class InterviewSessionState(BaseModel):
    session_id: str
    candidate_name: str
    start_time: Optional[float] = None
    target_duration_seconds: int = 300
    elapsed_seconds: int = 0
    time_remaining_seconds: int = 300
    is_paused: bool = False
    is_finished: bool = False
    conversation_history: List[MessageItem] = []
    candidate_profile: Optional[CandidateProfile] = None

class AudioTranscribeResponse(BaseModel):
    text: str
    confidence: float = 1.0
