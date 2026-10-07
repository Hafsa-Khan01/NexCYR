"""NexCYR Intelligence — contextual AI assistant routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.utils import to_iso
from config import Config
from database import get_db
from models.ai_analysis import AIAnalysis
from services import intelligence_service
from services.settings_service import get_ai_runtime_status

logger = logging.getLogger("nexcyr.ai")

router = APIRouter(prefix="/api/ai", tags=["NexCYR Intelligence"])


class AIQuestion(BaseModel):
    question: str = Field(..., min_length=1)
    context_type: str | None = Field(default=None, max_length=50)
    context_id: int | None = None


@router.post("")
def ask_ai(data: AIQuestion, db: Session = Depends(get_db)):
    context_type = (data.context_type or "").strip().lower() or None
    if context_type and context_type not in {"finding", "assessment", "scan", "soc_event", "target"}:
        raise HTTPException(
            status_code=400,
            detail="context_type must be one of: finding, assessment, scan, soc_event, target",
        )

    try:
        result = intelligence_service.answer_question(
            db,
            question=data.question,
            context_type=context_type,
            context_id=data.context_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("AI request failed")
        raise HTTPException(status_code=500, detail="AI analysis failed unexpectedly.")

    return result


@router.get("/status")
def ai_status():
    return {
        "external_provider_configured": Config.ai_enabled(),
        "fallback_engine": "NexCYR Intelligence Fallback Engine (always available)",
        **get_ai_runtime_status(),
    }


def serialize_analysis(analysis: AIAnalysis) -> dict:
    return {
        "id": analysis.id,
        "question": analysis.question,
        "analysis_type": analysis.analysis_type,
        "source_type": analysis.source_type,
        "source_id": analysis.source_id,
        "risk_level": analysis.risk_level,
        "summary": analysis.summary,
        "provider": analysis.provider,
        "status": analysis.status,
        "created_at": to_iso(analysis.created_at),
    }


@router.get("/history")
def ai_history(limit: int = 50, db: Session = Depends(get_db)):
    analyses = (
        db.query(AIAnalysis)
        .order_by(AIAnalysis.id.desc())
        .limit(min(max(limit, 1), 200))
        .all()
    )
    return [serialize_analysis(a) for a in analyses]
