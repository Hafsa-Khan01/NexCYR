from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.utils import to_iso
from database import get_db
from models.assessment import Assessment
from models.finding import Finding
from models.scan import Scan
from models.soc_event import SOCEvent
from models.target import Target
from services.risk_engine import calculate_overall_risk

router = APIRouter(prefix="/api/assessments", tags=["Assessments"])


class AssessmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    assessment_type: str = Field(default="general", max_length=50)
    status: str = Field(default="created", max_length=30)


class AssessmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    assessment_type: str | None = Field(default=None, max_length=50)
    status: str | None = Field(default=None, max_length=30)
    risk_level: str | None = Field(default=None, max_length=20)
    risk_score: int | None = Field(default=None, ge=0, le=100)


def refresh_assessment_risk(db: Session, assessment: Assessment) -> Assessment:
    findings = (
        db.query(Finding).filter(Finding.assessment_id == assessment.id).all()
    )
    overall = calculate_overall_risk(
        [
            {
                "title": f.title,
                "severity": f.severity,
                "risk_score": f.risk_score,
                "status": f.status,
            }
            for f in findings
        ]
    )
    assessment.risk_score = overall["overall_score"]
    assessment.risk_level = overall["overall_risk"]
    db.commit()
    db.refresh(assessment)
    return assessment


def serialize_assessment(db: Session, assessment: Assessment) -> dict:
    stats = {
        "targets": db.query(Target).filter(Target.assessment_id == assessment.id).count(),
        "scans": db.query(Scan).filter(Scan.assessment_id == assessment.id).count(),
        "findings": db.query(Finding).filter(Finding.assessment_id == assessment.id).count(),
        "open_findings": (
            db.query(Finding)
            .filter(Finding.assessment_id == assessment.id, Finding.status == "open")
            .count()
        ),
        "critical": (
            db.query(Finding)
            .filter(Finding.assessment_id == assessment.id, Finding.severity == "critical")
            .count()
        ),
        "high": (
            db.query(Finding)
            .filter(Finding.assessment_id == assessment.id, Finding.severity == "high")
            .count()
        ),
        "soc_events": (
            db.query(SOCEvent).filter(SOCEvent.assessment_id == assessment.id).count()
        ),
    }
    return {
        "id": assessment.id,
        "name": assessment.name,
        "description": assessment.description,
        "assessment_type": assessment.assessment_type,
        "status": assessment.status,
        "risk_level": assessment.risk_level,
        "risk_score": assessment.risk_score,
        "created_at": to_iso(assessment.created_at),
        "updated_at": to_iso(assessment.updated_at),
        "stats": stats,
    }


def get_assessment_or_404(db: Session, assessment_id: int) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment


@router.post("", status_code=201)
def create_assessment(data: AssessmentCreate, db: Session = Depends(get_db)):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Assessment name cannot be empty.")

    assessment = Assessment(
        name=name,
        description=(data.description or "").strip() or None,
        assessment_type=(data.assessment_type or "general").strip().lower(),
        status=(data.status or "created").strip().lower(),
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return serialize_assessment(db, assessment)


@router.get("")
def list_assessments(db: Session = Depends(get_db)):
    assessments = db.query(Assessment).order_by(Assessment.id.desc()).all()
    return [serialize_assessment(db, a) for a in assessments]


@router.get("/{assessment_id}")
def get_assessment(assessment_id: int, db: Session = Depends(get_db)):
    assessment = get_assessment_or_404(db, assessment_id)
    return serialize_assessment(db, assessment)


@router.put("/{assessment_id}")
def update_assessment(
    assessment_id: int, data: AssessmentUpdate, db: Session = Depends(get_db)
):
    assessment = get_assessment_or_404(db, assessment_id)
    updates = data.model_dump(exclude_unset=True)

    if "name" in updates and updates["name"] is not None:
        if not updates["name"].strip():
            raise HTTPException(status_code=400, detail="Assessment name cannot be empty.")
        assessment.name = updates["name"].strip()
    for field in ("description", "assessment_type", "status", "risk_level", "risk_score"):
        if field in updates and updates[field] is not None:
            value = updates[field]
            setattr(assessment, field, value.strip().lower() if isinstance(value, str) and field != "description" else value)

    db.commit()
    db.refresh(assessment)
    return serialize_assessment(db, assessment)


@router.delete("/{assessment_id}")
def delete_assessment(assessment_id: int, db: Session = Depends(get_db)):
    assessment = get_assessment_or_404(db, assessment_id)
    db.delete(assessment)
    db.commit()
    return {"message": "Assessment deleted successfully", "id": assessment_id}
