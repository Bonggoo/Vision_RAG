from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    GEMINI_API_KEY: str
    # Cloud Run 에는 이 두 값의 환경변수가 설정돼 있지 않으므로, 배포 환경은 이 기본값을
    # 그대로 사용한다 — 모델을 바꾸려면 여기를 고치는 것이 배포 경로다.
    # GEMINI_MODEL_NAME 은 Phase 3 Vision 답변, FLASH 쪽은 나머지 전 단계에 쓰인다.
    # 지금은 같은 모델이지만 분리돼 있어 Vision 만 상위 모델로 올릴 수 있다.
    GEMINI_MODEL_NAME: str = "gemini-3.5-flash-lite"
    GEMINI_FLASH_MODEL_NAME: str = "gemini-3.5-flash-lite"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    PDF_UPLOAD_DIR: str = "/tmp/uploads"
    GCS_BUCKET_NAME: str = "vision-rag-uploads-gen-lang-client-0031404090"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://172.20.10.7:3000,http://172.20.10.7:3001,http://192.168.219.109:3000"
    LOG_DIR: str = "logs"
    LOG_LEVEL: str = "INFO"
    USE_LOCAL_STORAGE: bool = False
    GEMINI_TIMEOUT: float = 90.0
    # 리소스 고갈 방어용 상한 (병적인 파일만 거르고 실제 대용량 매뉴얼은 통과하도록 관대하게 설정)
    MAX_PDF_PAGES: int = 3000          # PyMuPDF/Vision 처리 전 페이지 수 상한
    MAX_UPLOAD_MB: int = 100           # 업로드 파일 크기 상한 (MB)
    PIPELINE_TIMEOUT: float = 240.0    # 채팅 파이프라인 1회 요청 종합 타임아웃 (초)
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


