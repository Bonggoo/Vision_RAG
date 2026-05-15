from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    GEMINI_API_KEY: str
    GEMINI_MODEL_NAME: str = "gemini-3.1-flash"
    GEMINI_FLASH_MODEL_NAME: str = "gemini-3.1-flash-lite"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    PDF_UPLOAD_DIR: str = "/tmp/uploads"
    GCS_BUCKET_NAME: str = "vision-rag-uploads-gen-lang-client-0031404090"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://172.20.10.7:3000,http://172.20.10.7:3001,http://192.168.219.109:3000"

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
