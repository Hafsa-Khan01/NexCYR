from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from services.settings_service import (
    get_ai_runtime_status,
    get_or_create_settings,
    update_settings,
)

router = APIRouter(prefix="/api/settings", tags=["Settings"])


class SettingsUpdate(BaseModel):
    platform_name: str | None = None
    environment: str | None = None
    ai_enabled: bool | None = None
    automatic_analysis: bool | None = None
    soc_event_analysis: bool | None = None
    finding_analysis: bool | None = None
    purple_team_analysis: bool | None = None
    voice_enabled: bool | None = None
    speak_critical_alerts: bool | None = None
    speak_high_alerts: bool | None = None
    speak_medium_alerts: bool | None = None
    voice_language: str | None = None
    voice_name: str | None = None
    voice_rate: float | None = None
    voice_volume: float | None = None


def serialize_settings(settings) -> dict:
    return {
        "platform": {
            "platform_name": settings.platform_name,
            "environment": settings.environment,
        },
        "ai": {
            "ai_enabled": settings.ai_enabled,
            "ai_provider": settings.ai_provider,
            "ai_model": settings.ai_model,
            "automatic_analysis": settings.automatic_analysis,
            "soc_event_analysis": settings.soc_event_analysis,
            "finding_analysis": settings.finding_analysis,
            "purple_team_analysis": settings.purple_team_analysis,
        },
        "voice": {
            "voice_enabled": settings.voice_enabled,
            "speak_critical_alerts": settings.speak_critical_alerts,
            "speak_high_alerts": settings.speak_high_alerts,
            "speak_medium_alerts": settings.speak_medium_alerts,
            "voice_language": settings.voice_language,
            "voice_name": settings.voice_name,
            "voice_rate": settings.voice_rate,
            "voice_volume": settings.voice_volume,
        },
        "ai_runtime": get_ai_runtime_status(),
    }


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    return serialize_settings(get_or_create_settings(db))


@router.put("")
def put_settings(data: SettingsUpdate, db: Session = Depends(get_db)):
    updates = data.model_dump(exclude_unset=True)
    settings = update_settings(db, updates)
    return serialize_settings(settings)
