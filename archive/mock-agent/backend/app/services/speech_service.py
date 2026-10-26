import abc
from typing import Tuple

class BaseSpeechToTextService(abc.ABC):
    @abc.abstractmethod
    def transcribe(self, audio_bytes: bytes, content_type: str) -> Tuple[str, float]:
        """Transcribes raw audio bytes into text."""
        pass

class MockSpeechToTextService(BaseSpeechToTextService):
    """
    Fallback mock STT service.
    Can later be replaced with Whisper, Deepgram, or Google Cloud Speech.
    """
    def transcribe(self, audio_bytes: bytes, content_type: str) -> Tuple[str, float]:
        # Return mock transcription if backend audio processing is called
        return ("I built a distributed microservices backend using FastAPI and Docker.", 0.95)

speech_service = MockSpeechToTextService()
