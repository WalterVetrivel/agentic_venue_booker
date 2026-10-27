from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_secret: str = "dev-only-secret-change-me-in-backend-env-file"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'storage' / 'app.db'}"
    jwt_ttl_hours: int = 12
    cookie_name: str = "avb_session"
    cookie_secure: bool = False

    groq_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    default_llm_provider: str = "groq"
    # Embeddings for document search: "ollama" (nomic-embed-text) or "off" (keyword search only).
    embeddings: str = "ollama"
    embed_model: str = "nomic-embed-text"

    upload_dir: Path = BACKEND_DIR / "storage" / "uploads"
    mock_data_dir: Path = REPO_DIR / "data" / "mock"
    frontend_build_dir: Path = REPO_DIR / "frontend" / "build"


@lru_cache
def get_settings() -> Settings:
    return Settings()
