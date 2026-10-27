"""The Director's Settings page: which LLM the assistant uses, and the Groq key."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent import settings as llm_store
from app.agent.llm import LLMError, check_connection, make_llm, ollama_models
from app.auth import require
from app.db import get_db
from app.models import User
from app.schemas import LLMSettingsIn, LLMSettingsOut, LLMTestIn, LLMTestOut
from app.services import audit

router = APIRouter(prefix="/api/settings", tags=["settings"])


def settings_out(db: Session) -> LLMSettingsOut:
    cfg = llm_store.llm_settings(db)
    return LLMSettingsOut(
        provider=cfg.provider,
        groq_model=cfg.groq_model,
        groq_fallback_model=cfg.groq_fallback_model,
        groq_key_set=bool(cfg.groq_api_key),
        groq_key_masked=llm_store.mask(cfg.groq_api_key),
        groq_key_source=cfg.groq_key_source,
        ollama_base_url=cfg.ollama_base_url,
        ollama_model=cfg.ollama_model,
    )


@router.get("/llm", response_model=LLMSettingsOut)
def get_llm_settings(
    db: Session = Depends(get_db), _: User = Depends(require("manage_settings"))
) -> LLMSettingsOut:
    return settings_out(db)


@router.put("/llm", response_model=LLMSettingsOut)
def update_llm_settings(
    body: LLMSettingsIn,
    db: Session = Depends(get_db),
    user: User = Depends(require("manage_settings")),
) -> LLMSettingsOut:
    changes = body.model_dump(exclude_unset=True)
    if "provider" in changes:
        changes["llm_provider"] = changes.pop("provider")
    llm_store.save(db, changes)
    # Never write the key itself to the audit log.
    logged = {k: ("(changed)" if k == "groq_api_key" else v) for k, v in changes.items()}
    audit.record(db, user, "update", "settings", None, after=logged)
    db.commit()
    return settings_out(db)


@router.post("/llm/test", response_model=LLMTestOut)
async def test_llm(
    body: LLMTestIn,
    db: Session = Depends(get_db),
    _: User = Depends(require("manage_settings")),
) -> LLMTestOut:
    cfg = llm_store.llm_settings(db)
    cfg.fake = False  # the point is to test the real thing
    try:
        llm = make_llm(cfg, body.provider, body.model)
    except LLMError as e:
        return LLMTestOut(ok=False, message=str(e))
    return LLMTestOut(**await check_connection(llm))


@router.get("/ollama-models", response_model=list[str])
async def list_ollama_models(
    db: Session = Depends(get_db), _: User = Depends(require("manage_settings"))
) -> list[str]:
    return await ollama_models(llm_store.llm_settings(db).ollama_base_url)
