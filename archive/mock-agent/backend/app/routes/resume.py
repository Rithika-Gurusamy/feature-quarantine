import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from app.models.schemas import ResumeUploadResponse
from app.services.resume_service import resume_service
from app.services.session_store import session_store
from app.services.interview_service import interview_service
from app.core.config import settings

router = APIRouter(prefix="/resume", tags=["Resume"])

@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(file: UploadFile = File(...)):
    """
    Receives candidate resume, extracts structured CandidateProfile JSON memory,
    creates in-memory session, initializes conversation, and returns the opening question.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required."
        )

    filename = file.filename
    filename_lower = filename.lower()
    if not (filename_lower.endswith(".pdf") or filename_lower.endswith(".docx") or filename_lower.endswith(".txt")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload a PDF (.pdf), Word Document (.docx), or Text file (.txt)."
        )

    try:
        contents = await file.read()
        if len(contents) > settings.MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum allowed size of {settings.MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB."
            )

        resume_text = resume_service.extract_text(contents, filename)
        if not resume_text or len(resume_text.strip()) < 20:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not extract readable text from the uploaded resume. Please verify the file content."
            )

        # Extract structured CandidateProfile JSON Memory
        candidate_profile = resume_service.extract_candidate_profile(resume_text, filename)
        session_id = str(uuid.uuid4())

        # Create session with candidate memory
        session = session_store.create_session(
            session_id=session_id,
            candidate_name=candidate_profile.candidate_name,
            resume_text=resume_text,
            candidate_profile=candidate_profile,
            target_duration=settings.DEFAULT_INTERVIEW_DURATION_SECONDS
        )

        # Generate tailored opening question based on candidate JSON memory
        initial_question = interview_service.get_initial_question(
            session_id=session_id,
            candidate_memory=candidate_profile,
            resume_text=resume_text
        )
        session.add_message(
            role="interviewer",
            content=initial_question,
            intent="INITIAL_QUESTION",
            agent_used="TechnicalInterviewerAgent"
        )
        session.start()

        return ResumeUploadResponse(
            session_id=session_id,
            candidate_name=candidate_profile.candidate_name,
            resume_uploaded=True,
            initial_message=initial_question,
            target_duration_seconds=session.target_duration_seconds,
            candidate_profile=candidate_profile
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error parsing resume: {str(e)}"
        )
