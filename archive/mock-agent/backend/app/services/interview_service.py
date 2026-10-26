import abc
from typing import List, Dict, Any, Optional, Tuple
import requests
from app.models.schemas import MessageItem, CandidateProfile, IntentType
from app.services.orchestrator import agent_orchestrator
from app.core.config import settings

class BaseInterviewService(abc.ABC):
    """
    Abstract contract for the AI/Conversation Engine with Agent Orchestration.
    """

    @abc.abstractmethod
    def get_initial_question(self, session_id: str, candidate_memory: CandidateProfile, resume_text: str) -> str:
        """Returns opening interview question tailored to Candidate JSON Memory."""
        pass

    @abc.abstractmethod
    def generate_response(
        self,
        session_id: str,
        candidate_memory: CandidateProfile,
        resume_text: str,
        conversation_history: List[MessageItem],
        candidate_message: str,
        remaining_seconds: int = 300
    ) -> Tuple[str, IntentType, str]:
        """
        Orchestrates intent classification, queries specialized agent, and returns
        (response_text, intent_classified, agent_used).
        """
        pass


class MockInterviewService(BaseInterviewService):
    """
    Multi-Agent conversational orchestrator with structured Candidate JSON Memory.
    """

    def get_initial_question(self, session_id: str, candidate_memory: CandidateProfile, resume_text: str) -> str:
        first_name = candidate_memory.candidate_name.split()[0] if candidate_memory.candidate_name else "there"
        primary_project = candidate_memory.projects[0].name if candidate_memory.projects else "your primary system"
        skills_summary = ", ".join(candidate_memory.skills[:3]) if candidate_memory.skills else "system design"

        return (
            f"Hello {first_name}! Welcome to your technical mock interview. "
            f"I've reviewed your background as a {candidate_memory.title} working with {skills_summary}. "
            f"Let's start with **{primary_project}**. "
            "Could you give me an architectural overview of this system and your direct engineering role in building it?"
        )

    def generate_response(
        self,
        session_id: str,
        candidate_memory: CandidateProfile,
        resume_text: str,
        conversation_history: List[MessageItem],
        candidate_message: str,
        remaining_seconds: int = 300
    ) -> Tuple[str, IntentType, str]:
        # Delegate to Agent Orchestrator for intent classification and specialized routing
        return agent_orchestrator.process_message(
            session_id=session_id,
            candidate_memory=candidate_memory,
            conversation_history=conversation_history,
            candidate_message=candidate_message,
            remaining_seconds=remaining_seconds
        )


class N8NInterviewService(BaseInterviewService):
    """
    Integration layer sending Candidate JSON Memory + conversation history to n8n Webhook.
    """

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or settings.N8N_WEBHOOK_URL

    def get_initial_question(self, session_id: str, candidate_memory: CandidateProfile, resume_text: str) -> str:
        if not self.webhook_url:
            return f"Hello {candidate_memory.candidate_name}! Let's discuss your experience in {candidate_memory.title}."

        try:
            payload = {
                "action": "start_interview",
                "session_id": session_id,
                "candidate_profile": candidate_memory.model_dump(),
                "resume_text": resume_text
            }
            resp = requests.post(self.webhook_url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response_text", "Welcome! Let's discuss your technical background.")
        except Exception:
            return f"Welcome {candidate_memory.candidate_name}! Could you introduce your primary technical project?"

    def generate_response(
        self,
        session_id: str,
        candidate_memory: CandidateProfile,
        resume_text: str,
        conversation_history: List[MessageItem],
        candidate_message: str,
        remaining_seconds: int = 300
    ) -> Tuple[str, IntentType, str]:
        if not self.webhook_url:
            return "n8n Webhook URL is not configured. Please set N8N_WEBHOOK_URL.", "TECHNICAL_ANSWER", "N8NInterviewService"

        try:
            payload = {
                "action": "next_message",
                "session_id": session_id,
                "candidate_profile": candidate_memory.model_dump(),
                "resume_text": resume_text,
                "conversation_history": [msg.model_dump() for msg in conversation_history],
                "latest_candidate_message": candidate_message,
                "remaining_seconds": remaining_seconds
            }
            resp = requests.post(self.webhook_url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            response_text = data.get("response_text", "Thank you. Could you elaborate further?")
            intent = data.get("intent", "TECHNICAL_ANSWER")
            agent_used = data.get("agent_used", "N8NAgent")
            return response_text, intent, agent_used
        except Exception as e:
            return f"Error communicating with AI engine: {str(e)}", "TECHNICAL_ANSWER", "N8NInterviewService"


def get_interview_service() -> BaseInterviewService:
    engine = settings.INTERVIEW_ENGINE.lower()
    if engine == "n8n":
        return N8NInterviewService()
    return MockInterviewService()

interview_service = get_interview_service()
