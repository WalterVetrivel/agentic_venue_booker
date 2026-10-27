"""Assistant settings: the Director's choices on the Settings page, falling back to backend/.env."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting

KEYS = (
    "llm_provider",
    "groq_api_key",
    "groq_model",
    "groq_fallback_model",
    "ollama_base_url",
    "ollama_model",
)
PROVIDERS = ("groq", "ollama")


@dataclass
class LLMSettings:
    provider: str  # the default for new chats
    groq_api_key: str
    groq_key_source: str  # settings | env | none
    groq_model: str
    groq_fallback_model: str
    ollama_base_url: str
    ollama_model: str
    fake: bool  # scripted assistant for tests; never talks to a real model


def stored(db: Session) -> dict[str, str]:
    rows = db.scalars(select(AppSetting).where(AppSetting.key.in_(KEYS))).all()
    return {r.key: r.value for r in rows}


def save(db: Session, changes: dict[str, str | None]) -> None:
    """Store settings; an empty value removes the setting so the .env value applies again."""
    for key, value in changes.items():
        if key not in KEYS:
            raise KeyError(key)
        row = db.get(AppSetting, key)
        value = (value or "").strip()
        if not value:
            if row is not None:
                db.delete(row)
        elif row is None:
            db.add(AppSetting(key=key, value=value))
        else:
            row.value = value


def llm_settings(db: Session) -> LLMSettings:
    env = get_settings()
    own = stored(db)
    key = own.get("groq_api_key") or env.groq_api_key
    source = "settings" if own.get("groq_api_key") else "env" if env.groq_api_key else "none"
    provider = own.get("llm_provider") or env.default_llm_provider
    return LLMSettings(
        provider=provider if provider in PROVIDERS else "groq",
        groq_api_key=key,
        groq_key_source=source,
        groq_model=own.get("groq_model") or env.groq_model,
        groq_fallback_model=own.get("groq_fallback_model") or env.groq_fallback_model,
        ollama_base_url=(own.get("ollama_base_url") or env.ollama_base_url).rstrip("/"),
        ollama_model=own.get("ollama_model") or env.ollama_model,
        fake=env.llm_fake,
    )


def mask(key: str) -> str:
    if not key:
        return ""
    return f"{key[:4]}…{key[-4:]}" if len(key) > 12 else "…"
