import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Real-Time AI Mock Interviewer"
    API_V1_STR: str = "/api"
    DEFAULT_INTERVIEW_DURATION_SECONDS: int = 300  # 5 minutes
    
    # AI Engine mode: "mock" or "n8n"
    INTERVIEW_ENGINE: str = os.getenv("INTERVIEW_ENGINE", "mock")
    N8N_WEBHOOK_URL: str = os.getenv("N8N_WEBHOOK_URL", "")

    # CORS settings
    ALLOWED_ORIGINS: list[str] = ["*"]

    # Maximum file size (10 MB)
    MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024

settings = Settings()
