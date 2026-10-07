from sqlalchemy.orm import Session

from config import Config
from models.settings import NexCYRSettings


def get_or_create_settings(db: Session) -> NexCYRSettings:
    settings = db.query(NexCYRSettings).first()
    if settings:
        return settings

    settings = NexCYRSettings(
        platform_name="NexCYR",
        environment="local",
        ai_enabled=True,
        ai_provider=Config.AI_PROVIDER or "not_configured",
        ai_model=Config.AI_MODEL or "not_configured",
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def update_settings(db: Session, updates: dict) -> NexCYRSettings:
    settings = get_or_create_settings(db)

    for key, value in updates.items():
        if value is not None and hasattr(settings, key):
            setattr(settings, key, value)

    db.commit()
    db.refresh(settings)
    return settings


def get_ai_runtime_status() -> dict:
    return {
        "engine": "openai-compatible" if Config.ai_enabled() else "fallback",
        "provider": Config.AI_PROVIDER if Config.ai_enabled() else "not_configured",
        "model": Config.AI_MODEL if Config.ai_enabled() else "not_configured",
        "external_key_configured": bool(Config.OPENAI_API_KEY),
        "fallback_available": True,
    }
