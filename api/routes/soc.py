"""SOC monitoring routes — real stored events only, never fabricated."""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.utils import normalize_severity, to_iso
from database import get_db
from models.soc_event import SOCEvent
from services.correlation_service import correlate_events

router = APIRouter(prefix="/api/soc", tags=["SOC Monitoring"])

VALID_EVENT_STATUSES = {"open", "investigating", "contained", "resolved", "closed"}


class SOCEventCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=100)
    source: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1)
    severity: str = Field(default="low", max_length=20)
    status: str = Field(default="open", max_length=30)
    assessment_id: int | None = None
    target_id: int | None = None
    source_ip: str | None = Field(default=None, max_length=50)
    destination_ip: str | None = Field(default=None, max_length=50)
    raw_data: dict | None = None
    detected_by: str | None = Field(default=None, max_length=100)


class SOCEventUpdate(BaseModel):
    event_type: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, max_length=100)
    message: str | None = None
    severity: str | None = Field(default=None, max_length=20)
    status: str | None = Field(default=None, max_length=30)
    source_ip: str | None = None
    destination_ip: str | None = None
    detected_by: str | None = None


def serialize_event(event: SOCEvent) -> dict:
    raw = None
    if event.raw_data:
        try:
            raw = json.loads(event.raw_data)
        except json.JSONDecodeError:
            raw = event.raw_data
    return {
        "id": event.id,
        "event_type": event.event_type,
        "source": event.source,
        "message": event.message,
        "severity": event.severity,
        "status": event.status,
        "assessment_id": event.assessment_id,
        "target_id": event.target_id,
        "source_ip": event.source_ip,
        "destination_ip": event.destination_ip,
        "raw_data": raw,
        "detected_by": event.detected_by,
        "created_at": to_iso(event.created_at),
        "updated_at": to_iso(event.updated_at),
    }


def get_event_or_404(db: Session, event_id: int) -> SOCEvent:
    event = db.get(SOCEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="SOC event not found")
    return event


@router.post("/events", status_code=201)
def create_event(data: SOCEventCreate, db: Session = Depends(get_db)):
    event = SOCEvent(
        event_type=data.event_type.strip(),
        source=data.source.strip(),
        message=data.message.strip(),
        severity=normalize_severity(data.severity, "low"),
        status=(data.status or "open").strip().lower(),
        assessment_id=data.assessment_id,
        target_id=data.target_id,
        source_ip=data.source_ip,
        destination_ip=data.destination_ip,
        raw_data=json.dumps(data.raw_data) if data.raw_data else None,
        detected_by=data.detected_by or "NexCYR SOC",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return serialize_event(event)


@router.get("/events")
def list_events(
    assessment_id: int | None = None,
    severity: str | None = None,
    status: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    query = db.query(SOCEvent)
    if assessment_id is not None:
        query = query.filter(SOCEvent.assessment_id == assessment_id)
    if severity:
        query = query.filter(SOCEvent.severity == normalize_severity(severity, "low"))
    if status:
        query = query.filter(SOCEvent.status == status.strip().lower())
    events = query.order_by(SOCEvent.id.desc()).limit(min(max(limit, 1), 500)).all()
    return [serialize_event(e) for e in events]


@router.get("/summary")
def soc_summary(db: Session = Depends(get_db)):
    events = db.query(SOCEvent).all()
    by_severity = {}
    by_status = {}
    by_type = {}
    for event in events:
        by_severity[event.severity] = by_severity.get(event.severity, 0) + 1
        by_status[event.status] = by_status.get(event.status, 0) + 1
        by_type[event.event_type] = by_type.get(event.event_type, 0) + 1

    recent = (
        db.query(SOCEvent).order_by(SOCEvent.id.desc()).limit(5).all()
    )
    return {
        "total": len(events),
        "open": by_status.get("open", 0),
        "critical": by_severity.get("critical", 0),
        "high": by_severity.get("high", 0),
        "by_severity": by_severity,
        "by_status": by_status,
        "by_type": by_type,
        "recent": [serialize_event(e) for e in recent],
    }


@router.get("/correlation")
def soc_correlation(window_hours: int = 24, db: Session = Depends(get_db)):
    return correlate_events(db, window_hours=min(max(window_hours, 1), 168))


@router.get("/events/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)):
    return serialize_event(get_event_or_404(db, event_id))


@router.put("/events/{event_id}")
def update_event(event_id: int, data: SOCEventUpdate, db: Session = Depends(get_db)):
    event = get_event_or_404(db, event_id)
    updates = data.model_dump(exclude_unset=True)

    if "severity" in updates and updates["severity"] is not None:
        event.severity = normalize_severity(updates["severity"], event.severity)
    if "status" in updates and updates["status"] is not None:
        status = updates["status"].strip().lower()
        if status not in VALID_EVENT_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"status must be one of: {', '.join(sorted(VALID_EVENT_STATUSES))}",
            )
        event.status = status
    for field in ("event_type", "source", "message", "source_ip", "destination_ip", "detected_by"):
        if field in updates and updates[field] is not None:
            setattr(event, field, updates[field])

    db.commit()
    db.refresh(event)
    return serialize_event(event)


@router.delete("/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = get_event_or_404(db, event_id)
    db.delete(event)
    db.commit()
    return {"message": "SOC event deleted successfully", "id": event_id}
