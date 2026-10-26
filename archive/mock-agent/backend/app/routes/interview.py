from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status
from app.models.schemas import (
    InterviewMessageRequest,
    InterviewMessageResponse,
    InterviewSessionState,
    AudioTranscribeResponse
)
from app.services.session_store import session_store
from app.services.interview_service import interview_service
from app.services.speech_service import speech_service

router = APIRouter(prefix="/interview", tags=["Interview"])

@router.post("/start", response_model=InterviewSessionState)
async def start_interview(payload: dict):
    """Explicitly starts the timer for the session if not already started."""
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="session_id is required")

    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session.start()
    return session.to_state()

@router.post("/message", response_model=InterviewMessageResponse)
async def send_interview_message(req: InterviewMessageRequest):
    """
    Canonical endpoint for candidate messages.
    Orchestrates intent classification, routes to specialized agent with Candidate JSON Memory,
    updates history, and returns response with intent metadata.
    """
    if not req.session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="session_id is required")

    session = session_store.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or expired")

    clean_message = req.message.strip()
    if not clean_message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Candidate message cannot be empty")

    if session.is_paused:
        session.resume()

    # Record candidate's message
    session.add_message(role="candidate", content=clean_message)

    remaining = session.get_remaining_seconds()
    if remaining <= 0 or session.is_finished:
        session.finish()
        wrap_up_msg = (
            "We have reached the end of our 5-minute technical interview window! "
            "Thank you for sharing your project experiences and architectural tradeoffs. "
            "You can now review our full transcript summary."
        )
        session.add_message(
            role="interviewer",
            content=wrap_up_msg,
            intent="INTERVIEW_WRAPUP",
            agent_used="TechnicalInterviewerAgent"
        )
        return InterviewMessageResponse(
            session_id=session.session_id,
            response_text=wrap_up_msg,
            message_type="interviewer",
            should_speak=True,
            time_remaining_seconds=0,
            is_finished=True,
            intent_classified="INTERVIEW_WRAPUP",
            agent_used="TechnicalInterviewerAgent",
            candidate_memory=session.candidate_profile
        )

    # Multi-Agent Intent Orchestration with Candidate JSON Memory
    response_text, intent_classified, agent_used = interview_service.generate_response(
        session_id=session.session_id,
        candidate_memory=session.candidate_profile,
        resume_text=session.resume_text,
        conversation_history=session.conversation_history,
        candidate_message=clean_message,
        remaining_seconds=remaining
    )

    # Record interviewer's response with agent metadata
    session.add_message(
        role="interviewer",
        content=response_text,
        intent=intent_classified,
        agent_used=agent_used
    )

    return InterviewMessageResponse(
        session_id=session.session_id,
        response_text=response_text,
        message_type="interviewer",
        should_speak=True,
        time_remaining_seconds=session.get_remaining_seconds(),
        is_finished=session.is_finished,
        intent_classified=intent_classified,
        agent_used=agent_used,
        candidate_memory=session.candidate_profile
    )

@router.post("/audio", response_model=AudioTranscribeResponse)
async def process_audio_stt(file: UploadFile = File(...)):
    """Fallback backend audio transcription endpoint."""
    try:
        contents = await file.read()
        text, confidence = speech_service.transcribe(contents, file.content_type or "audio/wav")
        return AudioTranscribeResponse(text=text, confidence=confidence)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Audio transcription failed: {str(e)}")

@router.get("/{session_id}", response_model=InterviewSessionState)
async def get_session_state(session_id: str):
    """Retrieves full real-time session state, candidate JSON memory, and conversation history."""
    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session.to_state()

@router.post("/{session_id}/pause", response_model=InterviewSessionState)
async def toggle_pause_interview(session_id: str):
    """Toggles pause/resume on the interview timer."""
    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.is_paused:
        session.resume()
    else:
        session.pause()

    return session.to_state()

@router.post("/{session_id}/finish", response_model=InterviewSessionState)
async def finish_interview(session_id: str):
    """Explicitly marks the interview session as completed."""
    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session.finish()
    return session.to_state()
