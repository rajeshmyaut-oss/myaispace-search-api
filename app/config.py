from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    APP_NAME: str = "MyAISpace Search API"
    APP_VERSION: str = "1.0.0"
    SECRET_KEY: str = "change-this-in-production"
    ALGORITHM: str = "HS256"
    ALLOWED_ORIGINS: str = "https://myaispace.in,http://localhost:3000"
    RATE_LIMIT_PER_MINUTE: int = 30
    RATE_LIMIT_PER_DAY: int = 500
    DATABASE_URL: str = "sqlite+aiosqlite:///./myaispace_search.db"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:32b"
    MAX_RESULTS: int = 20
    DEFAULT_RESULTS: int = 10

    def get_allowed_origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"

settings = Settings()
