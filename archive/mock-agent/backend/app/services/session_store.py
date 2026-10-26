import time
import threading
from typing import Dict, Optional, List
from app.models.schemas import MessageItem, InterviewSessionState, CandidateProfile
from app.core.config import settings

class SessionData:
    def __init__(
        self,
        session_id: str,
        candidate_name: str,
        resume_text: str,
        candidate_profile: Optional[CandidateProfile] = None,
        target_duration: int = 300
    ):
        self.session_id = session_id
        self.candidate_name = candidate_name
        self.resume_text = resume_text
        self.candidate_profile: CandidateProfile = candidate_profile or CandidateProfile(candidate_name=candidate_name)
        self.target_duration_seconds = target_duration
        self.start_time: Optional[float] = None
        self.paused_at: Optional[float] = None
        self.total_paused_duration: float = 0.0
        self.is_paused: bool = False
        self.is_finished: bool = False
        self.conversation_history: List[MessageItem] = []

    def start(self):
        if self.start_time is None:
            self.start_time = time.time()

    def get_elapsed_seconds(self) -> int:
        if self.start_time is None:
            return 0
        
        if self.is_finished:
            return min(self.target_duration_seconds, int(self.target_duration_seconds))

        current_time = time.time()
        effective_time = self.paused_at if self.is_paused and self.paused_at else current_time
        raw_elapsed = (effective_time - self.start_time) - self.total_paused_duration
        return max(0, int(raw_elapsed))

    def get_remaining_seconds(self) -> int:
        elapsed = self.get_elapsed_seconds()
        remaining = self.target_duration_seconds - elapsed
        if remaining <= 0:
            self.is_finished = True
            return 0
        return remaining

    def pause(self):
        if not self.is_paused and not self.is_finished:
            self.is_paused = True
            self.paused_at = time.time()

    def resume(self):
        if self.is_paused and not self.is_finished:
            if self.paused_at:
                self.total_paused_duration += (time.time() - self.paused_at)
                self.paused_at = None
            self.is_paused = False

    def finish(self):
        self.is_finished = True

    def add_message(self, role: str, content: str, intent: Optional[str] = None, agent_used: Optional[str] = None) -> MessageItem:
        msg = MessageItem(
            role=role,
            content=content,
            timestamp=time.time(),
            intent=intent,
            agent_used=agent_used
        )
        self.conversation_history.append(msg)
        return msg

    def to_state(self) -> InterviewSessionState:
        return InterviewSessionState(
            session_id=self.session_id,
            candidate_name=self.candidate_name,
            start_time=self.start_time,
            target_duration_seconds=self.target_duration_seconds,
            elapsed_seconds=self.get_elapsed_seconds(),
            time_remaining_seconds=self.get_remaining_seconds(),
            is_paused=self.is_paused,
            is_finished=self.is_finished or (self.get_remaining_seconds() <= 0),
            conversation_history=self.conversation_history,
            candidate_profile=self.candidate_profile
        )


class InMemorySessionStore:
    """
    Thread-safe in-memory session store holding candidate JSON memory.
    """
    def __init__(self):
        self._sessions: Dict[str, SessionData] = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        session_id: str,
        candidate_name: str,
        resume_text: str,
        candidate_profile: Optional[CandidateProfile] = None,
        target_duration: int = 300
    ) -> SessionData:
        with self._lock:
            session = SessionData(
                session_id=session_id,
                candidate_name=candidate_name,
                resume_text=resume_text,
                candidate_profile=candidate_profile,
                target_duration=target_duration or settings.DEFAULT_INTERVIEW_DURATION_SECONDS
            )
            self._sessions[session_id] = session
            return session

    def get_session(self, session_id: str) -> Optional[SessionData]:
        with self._lock:
            return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

session_store = InMemorySessionStore()
