"""Purple team routes — simulation planning, detection validation and results.

Records are safe, non-destructive test metadata; NexCYR never executes
attacks itself.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.utils import to_iso
from database import get_db
from models.finding import Finding
from models.purple_team import PurpleTeamTest
from models.target import Target

router = APIRouter(prefix="/api/purple-team/tests", tags=["Purple Team"])

VALID_STATUSES = {"planned", "in_progress", "executed", "completed", "cancelled"}
VALID_DETECTION = {"pending", "detected", "missed", "partial"}


class PurpleTeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    technique: str | None = Field(default=None, max_length=255)
    objective: str | None = None
    status: str = Field(default="planned", max_length=30)
    detection_status: str = Field(default="pending", max_length=30)
    notes: str | None = None
    evidence: str | None = None
    assessment_id: int | None = None
    target_id: int | None = None
    finding_id: int | None = None


class PurpleTeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    technique: str | None = None
    objective: str | None = None
    status: str | None = None
    detection_status: str | None = None
    notes: str | None = None
    evidence: str | None = None


def serialize_test(db: Session, test: PurpleTeamTest) -> dict:
    target = db.get(Target, test.target_id) if test.target_id else None
    finding = db.get(Finding, test.finding_id) if test.finding_id else None
    recommendation = None
    if test.detection_status == "missed":
        recommendation = (
            "Detection gap: add or tune SIEM/EDR rules covering this technique "
            "and re-run the validation."
        )
    elif test.detection_status == "partial":
        recommendation = (
            "Partial detection: improve alert fidelity and enrich telemetry for "
            "this technique, then re-validate."
        )
    elif test.detection_status == "detected":
        recommendation = "Detection validated. Keep the rule set under regression testing."

    return {
        "id": test.id,
        "name": test.name,
        "technique": test.technique,
        "objective": test.objective,
        "status": test.status,
        "detection_status": test.detection_status,
        "notes": test.notes,
        "evidence": test.evidence,
        "assessment_id": test.assessment_id,
        "target_id": test.target_id,
        "target_value": target.value if target else None,
        "finding_id": test.finding_id,
        "finding_title": finding.title if finding else None,
        "recommendation": recommendation,
        "created_at": to_iso(test.created_at),
        "updated_at": to_iso(test.updated_at),
    }


def get_test_or_404(db: Session, test_id: int) -> PurpleTeamTest:
    test = db.get(PurpleTeamTest, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Purple team test not found")
    return test


@router.post("", status_code=201)
def create_test(data: PurpleTeamCreate, db: Session = Depends(get_db)):
    status = (data.status or "planned").strip().lower()
    if status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )
    detection = (data.detection_status or "pending").strip().lower()
    if detection not in VALID_DETECTION:
        raise HTTPException(
            status_code=400,
            detail=f"detection_status must be one of: {', '.join(sorted(VALID_DETECTION))}",
        )

    test = PurpleTeamTest(
        name=data.name.strip(),
        technique=(data.technique or "").strip() or None,
        objective=data.objective,
        status=status,
        detection_status=detection,
        notes=data.notes,
        evidence=data.evidence,
        assessment_id=data.assessment_id,
        target_id=data.target_id,
        finding_id=data.finding_id,
    )
    db.add(test)
    db.commit()
    db.refresh(test)
    return serialize_test(db, test)


@router.get("")
def list_tests(
    assessment_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(PurpleTeamTest)
    if assessment_id is not None:
        query = query.filter(PurpleTeamTest.assessment_id == assessment_id)
    if status:
        query = query.filter(PurpleTeamTest.status == status.strip().lower())
    tests = query.order_by(PurpleTeamTest.id.desc()).all()
    return [serialize_test(db, t) for t in tests]


@router.get("/{test_id}")
def get_test(test_id: int, db: Session = Depends(get_db)):
    return serialize_test(db, get_test_or_404(db, test_id))


@router.put("/{test_id}")
def update_test(test_id: int, data: PurpleTeamUpdate, db: Session = Depends(get_db)):
    test = get_test_or_404(db, test_id)
    updates = data.model_dump(exclude_unset=True)

    if "status" in updates and updates["status"] is not None:
        status = updates["status"].strip().lower()
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        test.status = status
    if "detection_status" in updates and updates["detection_status"] is not None:
        detection = updates["detection_status"].strip().lower()
        if detection not in VALID_DETECTION:
            raise HTTPException(status_code=400, detail="Invalid detection_status")
        test.detection_status = detection
    for field in ("name", "technique", "objective", "notes", "evidence"):
        if field in updates and updates[field] is not None:
            setattr(test, field, updates[field])

    db.commit()
    db.refresh(test)
    return serialize_test(db, test)


@router.delete("/{test_id}")
def delete_test(test_id: int, db: Session = Depends(get_db)):
    test = get_test_or_404(db, test_id)
    db.delete(test)
    db.commit()
    return {"message": "Purple team test deleted successfully", "id": test_id}
