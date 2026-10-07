"""Dashboard aggregate metrics — all values from real stored data."""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.utils import to_iso
from database import get_db
from models.agent import Agent
from models.assessment import Assessment
from models.finding import Finding
from models.purple_team import PurpleTeamTest
from models.scan import Scan
from models.soc_event import SOCEvent
from models.target import Target
from models.wifi_assessment import WiFiAssessment
from services.agent_service import serialize_agent
from services.correlation_service import correlate_events
from services.risk_engine import calculate_overall_risk

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    findings = db.query(Finding).all()
    overall = calculate_overall_risk(
        [{"severity": f.severity, "risk_score": f.risk_score, "status": f.status} for f in findings]
    )

    severity_distribution = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        key = f.severity if f.severity != "informational" else "info"
        if key in severity_distribution:
            severity_distribution[key] += 1

    recent_findings = (
        db.query(Finding).order_by(Finding.id.desc()).limit(6).all()
    )
    recent_events = (
        db.query(SOCEvent).order_by(SOCEvent.id.desc()).limit(6).all()
    )
    recent_assessments = (
        db.query(Assessment).order_by(Assessment.id.desc()).limit(5).all()
    )

    purple_status = {
        "total": db.query(func.count(PurpleTeamTest.id)).scalar() or 0,
        "detected": (
            db.query(func.count(PurpleTeamTest.id))
            .filter(PurpleTeamTest.detection_status == "detected")
            .scalar()
            or 0
        ),
        "missed": (
            db.query(func.count(PurpleTeamTest.id))
            .filter(PurpleTeamTest.detection_status == "missed")
            .scalar()
            or 0
        ),
        "pending": (
            db.query(func.count(PurpleTeamTest.id))
            .filter(PurpleTeamTest.detection_status == "pending")
            .scalar()
            or 0
        ),
    }

    agents = db.query(Agent).order_by(Agent.id.asc()).all()
    agent_rows = [serialize_agent(a) for a in agents]
    agents_online = sum(1 for a in agent_rows if a["status"] == "online")

    activity = []
    for f in recent_findings[:3]:
        activity.append(
            {"kind": "finding", "id": f.id, "label": f.title, "severity": f.severity, "at": to_iso(f.created_at)}
        )
    for e in recent_events[:3]:
        activity.append(
            {"kind": "soc_event", "id": e.id, "label": e.message[:120], "severity": e.severity, "at": to_iso(e.created_at)}
        )
    activity.sort(key=lambda item: item["at"] or "", reverse=True)

    correlation = correlate_events(db)

    return {
        "counts": {
            "assessments": db.query(func.count(Assessment.id)).scalar() or 0,
            "targets": db.query(func.count(Target.id)).scalar() or 0,
            "active_targets": (
                db.query(func.count(Target.id)).filter(Target.status == "active").scalar() or 0
            ),
            "authorized_targets": (
                db.query(func.count(Target.id)).filter(Target.authorized.is_(True)).scalar() or 0
            ),
            "scans": db.query(func.count(Scan.id)).scalar() or 0,
            "findings": len(findings),
            "open_findings": sum(1 for f in findings if f.status == "open"),
            "critical_findings": severity_distribution["critical"],
            "high_findings": severity_distribution["high"],
            "soc_alerts": db.query(func.count(SOCEvent.id)).scalar() or 0,
            "open_soc_alerts": (
                db.query(func.count(SOCEvent.id)).filter(SOCEvent.status == "open").scalar() or 0
            ),
            "purple_team_tests": purple_status["total"],
            "wifi_assessments": db.query(func.count(WiFiAssessment.id)).scalar() or 0,
            "agents": len(agent_rows),
            "agents_online": agents_online,
        },
        "risk": {
            "level": overall["overall_risk"],
            "score": overall["overall_score"],
            "severity_distribution": severity_distribution,
            "has_data": len(findings) > 0,
            "empty_message": (
                None
                if findings
                else "No recorded security findings or activity yet."
            ),
        },
        "purple_team": purple_status,
        "agents": agent_rows,
        "recent_findings": [
            {
                "id": f.id,
                "title": f.title,
                "severity": f.severity,
                "status": f.status,
                "risk_score": f.risk_score,
                "created_at": to_iso(f.created_at),
            }
            for f in recent_findings
        ],
        "recent_soc_events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "message": e.message,
                "severity": e.severity,
                "status": e.status,
                "created_at": to_iso(e.created_at),
            }
            for e in recent_events
        ],
        "recent_assessments": [
            {
                "id": a.id,
                "name": a.name,
                "status": a.status,
                "risk_level": a.risk_level,
                "risk_score": a.risk_score,
            }
            for a in recent_assessments
        ],
        "recent_activity": activity,
        "correlation": {
            "clusters": correlation["clusters"][:6],
            "by_category": correlation["by_category"],
        },
    }
