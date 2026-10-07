"""Aggregates real database records into report data.

Never fabricates findings, scans or events — sections simply state that no
data was recorded when the database is empty.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.ai_analysis import AIAnalysis
from models.assessment import Assessment
from models.finding import Finding
from models.purple_team import PurpleTeamTest
from models.scan import Scan
from models.soc_event import SOCEvent
from models.target import Target
from models.wifi_assessment import WiFiAssessment
from services.correlation_service import correlate_events
from services.risk_engine import calculate_overall_risk

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info", "informational"]


def _normalize_severity(value):
    value = (value or "info").lower()
    return "info" if value == "informational" else value


def build_report_data(db: Session, assessment_id: int | None = None) -> dict:
    assessment = db.get(Assessment, assessment_id) if assessment_id else None

    query_targets = db.query(Target)
    query_scans = db.query(Scan)
    query_findings = db.query(Finding)
    query_events = db.query(SOCEvent)
    query_tests = db.query(PurpleTeamTest)
    query_wifi = db.query(WiFiAssessment)

    if assessment:
        query_targets = query_targets.filter(Target.assessment_id == assessment.id)
        query_scans = query_scans.filter(Scan.assessment_id == assessment.id)
        query_findings = query_findings.filter(Finding.assessment_id == assessment.id)
        query_events = query_events.filter(SOCEvent.assessment_id == assessment.id)
        query_tests = query_tests.filter(PurpleTeamTest.assessment_id == assessment.id)

    targets = query_targets.order_by(Target.id).all()
    scans = query_scans.order_by(Scan.id).all()
    findings = (
        query_findings.order_by(
            Finding.risk_score.desc(), Finding.id.desc()
        ).all()
    )
    events = query_events.order_by(SOCEvent.id.desc()).all()
    tests = query_tests.order_by(PurpleTeamTest.id).all()
    wifi = query_wifi.order_by(WiFiAssessment.id).all()

    severity_distribution = {key: 0 for key in ["critical", "high", "medium", "low", "info"]}
    for finding in findings:
        key = _normalize_severity(finding.severity)
        if key in severity_distribution:
            severity_distribution[key] += 1

    overall = calculate_overall_risk(
        [
            {
                "title": f.title,
                "severity": _normalize_severity(f.severity),
                "risk_score": f.risk_score,
                "status": f.status,
            }
            for f in findings
        ]
    )

    if assessment:
        risk_level = assessment.risk_level or overall["overall_risk"]
        risk_score = assessment.risk_score or overall["overall_score"]
    else:
        risk_level = overall["overall_risk"]
        risk_score = overall["overall_score"]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "assessment": (
            {
                "id": assessment.id,
                "name": assessment.name,
                "description": assessment.description or "",
                "assessment_type": assessment.assessment_type,
                "status": assessment.status,
                "created_at": assessment.created_at.isoformat() if assessment.created_at else None,
            }
            if assessment
            else None
        ),
        "risk": {
            "level": risk_level,
            "score": risk_score,
            "severity_distribution": severity_distribution,
            "open_findings": sum(1 for f in findings if f.status == "open"),
            "total_findings": len(findings),
        },
        "targets": [
            {
                "id": t.id,
                "name": t.name or "",
                "value": t.value,
                "target_type": t.target_type,
                "authorized": bool(t.authorized),
                "status": t.status,
            }
            for t in targets
        ],
        "scans": [
            {
                "id": s.id,
                "scan_type": s.scan_type,
                "status": s.status,
                "target": (db.get(Target, s.target_id).value if s.target_id else ""),
                "target_authorized": (
                    bool(db.get(Target, s.target_id).authorized) if s.target_id else False
                ),
                "execution_source": s.execution_source or "CLOUD",
                "agent_name": s.agent_name or ("Cloud Scanner" if not s.agent_id else ""),
                "agent_version": s.agent_version,
                "summary": s.result_summary or "",
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in scans
        ],
        "findings": [
            {
                "id": f.id,
                "title": f.title,
                "severity": _normalize_severity(f.severity),
                "status": f.status,
                "description": f.description or "",
                "evidence": f.evidence or "",
                "remediation": f.remediation or f.recommendations or "",
                "risk_score": f.risk_score,
                "target": (db.get(Target, f.target_id).value if f.target_id else ""),
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in findings
        ],
        "soc_events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "source": e.source,
                "severity": e.severity,
                "message": e.message,
                "status": e.status,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        "purple_team_tests": [
            {
                "id": t.id,
                "name": t.name,
                "technique": t.technique or "",
                "objective": t.objective or "",
                "status": t.status,
                "detection_status": t.detection_status,
                "notes": t.notes or "",
            }
            for t in tests
        ],
        "wifi_assessments": [
            {
                "id": w.id,
                "ssid": w.ssid,
                "security_type": w.security_type or "",
                "channel": w.channel or "",
                "status": w.status,
                "assessment": w.assessment or "",
                "notes": w.notes or "",
            }
            for w in wifi
        ],
        "correlation": correlate_events(db),
        "intelligence_summaries": [
            {
                "id": a.id,
                "question": a.question or "",
                "summary": (a.summary or "")[:600],
                "provider": a.provider,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in db.query(AIAnalysis)
            .order_by(AIAnalysis.id.desc())
            .limit(5)
            .all()
        ],
    }
