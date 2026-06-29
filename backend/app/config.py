from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    GEMINI_API_KEY: str
    GEMINI_MODEL_NAME: str = "gemini-3.1-flash-lite"
    GEMINI_FLASH_MODEL_NAME: str = "gemini-3.1-flash-lite"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    PDF_UPLOAD_DIR: str = "/tmp/uploads"
    GCS_BUCKET_NAME: str = "vision-rag-uploads-gen-lang-client-0031404090"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://172.20.10.7:3000,http://172.20.10.7:3001,http://192.168.219.109:3000"
    LOG_DIR: str = "logs"
    LOG_LEVEL: str = "INFO"
    USE_LOCAL_STORAGE: bool = False
    GEMINI_TIMEOUT: float = 90.0
    GOOGLE_CLIENT_ID: str = ""
    JWT_SECRET: str = "vision-rag-jwt-secret-key-change-in-production-12345"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # 30분
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30  # 30일

    # Cloud Tasks (미설정 시 로컬 asyncio.create_task 폴백)
    # 형식: projects/{project}/locations/{region}/queues/{queue_name}
    CLOUD_TASKS_QUEUE: str = ""
    # Cloud Run 서비스 URL (Cloud Tasks 콜백용)
    CLOUD_RUN_URL: str = ""
    # /internal/* 엔드포인트 공유 비밀 (Cloud Tasks → Cloud Run)
    INTERNAL_TASK_SECRET: str = ""

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()


