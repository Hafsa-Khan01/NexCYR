import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.routes.assessments import refresh_assessment_risk
from api.utils import split_list_text, to_iso
from database import get_db
from models.assessment import Assessment
from models.finding import Finding
from models.scan import Scan
from models.target import Target
from services.risk_engine import calculate_finding_risk

router = APIRouter(prefix="/api/findings", tags=["Findings"])

VALID_FINDING_STATUSES = {"open", "in_progress", "resolved", "accepted", "closed"}


class FindingCreate(BaseModel):
    assessment_id: int | None = None
    target_id: int | None = None
    scan_id: int | None = None
    title: str = Field(..., min_length=1, max_length=255)
    severity: str = Field(default="info", max_length=20)
    status: str = Field(default="open", max_length=30)
    description: str | None = None
    evidence: str | None = None
    remediation: str | None = None


class FindingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    severity: str | None = Field(default=None, max_length=20)
    status: str | None = Field(default=None, max_length=30)
    description: str | None = None
    evidence: str | None = None
    remediation: str | None = None


def serialize_finding(finding: Finding) -> dict:
    return {
        "id": finding.id,
        "assessment_id": finding.assessment_id,
        "target_id": finding.target_id,
        "scan_id": finding.scan_id,
        "title": finding.title,
        "severity": finding.severity,
        "status": finding.status,
        "description": finding.description,
        "evidence": finding.evidence,
        "remediation": finding.remediation,
        "source": finding.source,
        "risk_score": finding.risk_score,
        "risk_level": finding.risk_level,
        "risk_factors": split_list_text(finding.risk_factors),
        "recommendations": split_list_text(finding.recommendations),
        "confidence": finding.confidence,
        "created_at": to_iso(finding.created_at),
        "updated_at": to_iso(finding.updated_at),
    }


def apply_risk_engine(finding: Finding) -> None:
    result = calculate_finding_risk(
        {
            "title": finding.title,
            "severity": finding.severity,
            "description": finding.description or "",
        }
    )
    finding.risk_score = result["risk_score"]
    finding.risk_level = result["risk_level"]
    finding.risk_factors = ";".join(result.get("risk_factors", []))
    finding.recommendations = ";".join(result.get("recommendations", []))
    finding.confidence = result.get("confidence", "medium")


def get_finding_or_404(db: Session, finding_id: int) -> Finding:
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


def _refresh_linked_assessment(db: Session, finding: Finding) -> None:
    if finding.assessment_id:
        assessment = db.get(Assessment, finding.assessment_id)
        if assessment:
            refresh_assessment_risk(db, assessment)


@router.post("", status_code=201)
def create_finding(data: FindingCreate, db: Session = Depends(get_db)):
    severity = (data.severity or "info").strip().lower()
    if severity == "informational":
        severity = "info"
    if severity not in {"critical", "high", "medium", "low", "info"}:
        raise HTTPException(
            status_code=400,
            detail="severity must be one of: critical, high, medium, low, info",
        )

    if data.target_id and not db.get(Target, data.target_id):
        raise HTTPException(status_code=400, detail="Linked target does not exist")
    if data.scan_id and not db.get(Scan, data.scan_id):
        raise HTTPException(status_code=400, detail="Linked scan does not exist")
    if data.assessment_id and not db.get(Assessment, data.assessment_id):
        raise HTTPException(status_code=400, detail="Linked assessment does not exist")

    finding = Finding(
        assessment_id=data.assessment_id,
        target_id=data.target_id,
        scan_id=data.scan_id,
        title=data.title.strip(),
        severity=severity,
        status=(data.status or "open").strip().lower(),
        description=data.description,
        evidence=data.evidence,
        remediation=data.remediation,
        source="manual",
    )
    apply_risk_engine(finding)
    db.add(finding)
    db.commit()
    db.refresh(finding)
    _refresh_linked_assessment(db, finding)
    return serialize_finding(finding)


@router.get("")
def list_findings(
    assessment_id: int | None = None,
    target_id: int | None = None,
    scan_id: int | None = None,
    severity: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Finding)
    if assessment_id is not None:
        query = query.filter(Finding.assessment_id == assessment_id)
    if target_id is not None:
        query = query.filter(Finding.target_id == target_id)
    if scan_id is not None:
        query = query.filter(Finding.scan_id == scan_id)
    if severity:
        query = query.filter(Finding.severity == severity.strip().lower())
    if status:
        query = query.filter(Finding.status == status.strip().lower())
    findings = query.order_by(Finding.risk_score.desc(), Finding.id.desc()).all()
    return [serialize_finding(f) for f in findings]


@router.get("/{finding_id}")
def get_finding(finding_id: int, db: Session = Depends(get_db)):
    return serialize_finding(get_finding_or_404(db, finding_id))


@router.put("/{finding_id}")
def update_finding(finding_id: int, data: FindingUpdate, db: Session = Depends(get_db)):
    finding = get_finding_or_404(db, finding_id)
    updates = data.model_dump(exclude_unset=True)

    if "severity" in updates and updates["severity"] is not None:
        severity = updates["severity"].strip().lower()
        if severity == "informational":
            severity = "info"
        if severity not in {"critical", "high", "medium", "low", "info"}:
            raise HTTPException(
                status_code=400,
                detail="severity must be one of: critical, high, medium, low, info",
            )
        finding.severity = severity

    if "status" in updates and updates["status"] is not None:
        status = updates["status"].strip().lower()
        if status not in VALID_FINDING_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"status must be one of: {', '.join(sorted(VALID_FINDING_STATUSES))}",
            )
        finding.status = status

    for field in ("title", "description", "evidence", "remediation"):
        if field in updates and updates[field] is not None:
            setattr(finding, field, updates[field])

    apply_risk_engine(finding)
    db.commit()
    db.refresh(finding)
    _refresh_linked_assessment(db, finding)
    return serialize_finding(finding)


@router.delete("/{finding_id}")
def delete_finding(finding_id: int, db: Session = Depends(get_db)):
    finding = get_finding_or_404(db, finding_id)
    assessment_id = finding.assessment_id
    db.delete(finding)
    db.commit()
    if assessment_id:
        assessment = db.get(Assessment, assessment_id)
        if assessment:
            refresh_assessment_risk(db, assessment)
    return {"message": "Finding deleted successfully", "id": finding_id}
