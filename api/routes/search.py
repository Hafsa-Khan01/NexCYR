"""Global search across all real stored entities."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db
from models.assessment import Assessment
from models.finding import Finding
from models.purple_team import PurpleTeamTest
from models.scan import Scan
from models.soc_event import SOCEvent
from models.target import Target

router = APIRouter(prefix="/api/search", tags=["Search"])

MAX_RESULTS = 20


@router.get("")
def global_search(q: str, db: Session = Depends(get_db)):
    term = (q or "").strip()
    if not term:
        raise HTTPException(status_code=400, detail="Query parameter 'q' cannot be empty.")

    like = f"%{term}%"

    assessments = (
        db.query(Assessment)
        .filter(or_(Assessment.name.ilike(like), Assessment.description.ilike(like)))
        .limit(MAX_RESULTS)
        .all()
    )
    targets = (
        db.query(Target)
        .filter(or_(Target.value.ilike(like), Target.name.ilike(like)))
        .limit(MAX_RESULTS)
        .all()
    )
    scans = (
        db.query(Scan)
        .filter(or_(Scan.scan_type.ilike(like), Scan.result_summary.ilike(like)))
        .limit(MAX_RESULTS)
        .all()
    )
    findings = (
        db.query(Finding)
        .filter(
            or_(
                Finding.title.ilike(like),
                Finding.description.ilike(like),
                Finding.evidence.ilike(like),
            )
        )
        .limit(MAX_RESULTS)
        .all()
    )
    events = (
        db.query(SOCEvent)
        .filter(
            or_(
                SOCEvent.event_type.ilike(like),
                SOCEvent.message.ilike(like),
                SOCEvent.source.ilike(like),
            )
        )
        .limit(MAX_RESULTS)
        .all()
    )
    tests = (
        db.query(PurpleTeamTest)
        .filter(
            or_(
                PurpleTeamTest.name.ilike(like),
                PurpleTeamTest.technique.ilike(like),
                PurpleTeamTest.objective.ilike(like),
            )
        )
        .limit(MAX_RESULTS)
        .all()
    )

    return {
        "query": term,
        "assessments": [
            {"id": a.id, "label": a.name, "detail": a.status, "type": "assessment"}
            for a in assessments
        ],
        "targets": [
            {"id": t.id, "label": t.value, "detail": t.target_type, "type": "target"}
            for t in targets
        ],
        "scans": [
            {"id": s.id, "label": f"Scan #{s.id}", "detail": s.status, "type": "scan"}
            for s in scans
        ],
        "findings": [
            {"id": f.id, "label": f.title, "detail": f.severity, "type": "finding"}
            for f in findings
        ],
        "soc_events": [
            {"id": e.id, "label": e.event_type, "detail": e.severity, "type": "soc_event"}
            for e in events
        ],
        "purple_team_tests": [
            {"id": t.id, "label": t.name, "detail": t.detection_status, "type": "purple_team"}
            for t in tests
        ],
    }
