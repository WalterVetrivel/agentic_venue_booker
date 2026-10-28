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
    groq_model: str = "openai/gpt-oss-20b"
    groq_fallback_model: str = "llama-3.3-70b-versatile"
    ollama_model: str = "qwen3.5:4b"
    # Tests and the browser tests use a scripted assistant instead of a real LLM.
    llm_fake: bool = False
    # Embeddings for document search: "ollama" (nomic-embed-text) or "off" (keyword search only).
    embeddings: str = "ollama"
    embed_model: str = "nomic-embed-text"

    # Email for student requests. With no SMTP host, emails are saved to `outbox_dir` instead.
    # The Director can also set these on the Settings page.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    # Links in emails point here (the address students open the app at).
    public_url: str = "http://localhost:5173"
    # Only accept student contact emails on this domain, e.g. "kiot.ac.in". Empty accepts any.
    student_email_domain: str = ""
    # Our own limits on visitors: chat questions per IP, student requests per IP and per email.
    # Off for the prototype demo; turn on (RATE_LIMITS=true) before real use. Groq's own limits
    # still apply either way.
    rate_limits: bool = False

    upload_dir: Path = BACKEND_DIR / "storage" / "uploads"
    outbox_dir: Path = BACKEND_DIR / "storage" / "outbox"
    mock_data_dir: Path = REPO_DIR / "data" / "mock"
    frontend_build_dir: Path = REPO_DIR / "frontend" / "build"


@lru_cache
def get_settings() -> Settings:
    return Settings()
