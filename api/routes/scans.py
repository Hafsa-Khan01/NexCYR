"""Scan routes — safe, authorized scanning only.

A scan is only executed when the linked Target record is explicitly
authorized. Nmap (when available) is invoked with fixed, non-destructive
arguments; results are never fabricated. When nmap is unavailable the scan
completes with a clean, non-crashing status.
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.routes.assessments import refresh_assessment_risk
from api.routes.findings import serialize_finding
from api.utils import to_iso
from database import get_db
from models.finding import Finding
from models.scan import Scan
from models.target import Target
from services.nmap_service import is_safe_scan_value, nmap_available
from services.recon_service import enumerate_services, run_recon
from services.risk_engine import calculate_finding_risk, calculate_overall_risk
from services.vulnerability_engine import analyze_services

logger = logging.getLogger("nexcyr.scans")

router = APIRouter(prefix="/api/scans", tags=["Scans"])

VALID_SCAN_TYPES = {"basic", "service", "stealth"}


class ScanCreate(BaseModel):
    target_id: int
    scan_type: str = Field(default="service", max_length=50)
    assessment_id: int | None = None
    # Optional execution node. NULL/absent = Cloud Scanner. When set, the
    # scan is queued as an agent job and NOT executed locally.
    agent_id: int | None = None


def serialize_scan(db: Session, scan: Scan) -> dict:
    target = db.get(Target, scan.target_id) if scan.target_id else None
    findings_count = (
        db.query(func.count(Finding.id)).filter(Finding.scan_id == scan.id).scalar() or 0
    )
    result_data = None
    if scan.result_data:
        try:
            result_data = json.loads(scan.result_data)
        except json.JSONDecodeError:
            result_data = None
    return {
        "id": scan.id,
        "assessment_id": scan.assessment_id,
        "target_id": scan.target_id,
        "target_value": target.value if target else None,
        "scan_type": scan.scan_type,
        "status": scan.status,
        "result_summary": scan.result_summary,
        "result_data": result_data,
        "error": scan.error,
        "execution_source": scan.execution_source or "CLOUD",
        "agent_id": scan.agent_id,
        "agent_name": scan.agent_name,
        "agent_version": scan.agent_version,
        "findings_count": findings_count,
        "started_at": to_iso(scan.started_at),
        "completed_at": to_iso(scan.completed_at),
        "created_at": to_iso(scan.created_at),
        "updated_at": to_iso(scan.updated_at),
    }


def get_scan_or_404(db: Session, scan_id: int) -> Scan:
    scan = db.get(Scan, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan


@router.post("", status_code=201)
def create_scan(data: ScanCreate, db: Session = Depends(get_db)):
    target = db.get(Target, data.target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    if not target.authorized:
        raise HTTPException(
            status_code=400,
            detail=(
                "Target is not authorized for scanning. "
                "Record explicit authorization before scanning."
            ),
        )

    scan_type = (data.scan_type or "service").strip().lower()
    if scan_type not in VALID_SCAN_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"scan_type must be one of: {', '.join(sorted(VALID_SCAN_TYPES))}",
        )

    if not is_safe_scan_value(target.value):
        raise HTTPException(
            status_code=400,
            detail="Target value is not a safe scannable IP, hostname or small network.",
        )

    # Prefer the target's configured scanner when the operator did not choose one.
    requested_agent_id = data.agent_id or target.preferred_agent_id

    # When the operator did not pin an Agent, automatically use the first
    # online Agent that supports this scan. This makes Nmap available across
    # all supported scan profiles without requiring the operator to manually
    # select an Agent every time. The target must still be explicitly
    # authorized; the Agent only accepts structured, allowlisted jobs.
    from models.agent import Agent
    from services import agent_service
    from services.agent_service import serialize_agent, serialize_job

    scan_job_type = (
        "NMAP_HOST_DISCOVERY"
        if target.target_type == "network" and scan_type == "basic"
        else {
            "service": "NMAP_SERVICE_ENUMERATION",
            "basic": "NMAP_PORT_SCAN",
            "stealth": "NMAP_PORT_SCAN",
        }[scan_type]
    )

    if requested_agent_id is None:
        online_agents = db.query(Agent).order_by(Agent.id.asc()).all()
        for candidate in online_agents:
            if (
                serialize_agent(candidate)["status"] == "online"
                and agent_service.agent_supports_job(candidate, scan_job_type)
            ):
                requested_agent_id = candidate.id
                break

    # ---- Agent routing: queue a structured job, do NOT run locally ----
    agent = None
    if requested_agent_id:
        data.agent_id = requested_agent_id
        agent = db.get(Agent, data.agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        a_status = serialize_agent(agent)["status"]
        if a_status != "online":
            raise HTTPException(
                status_code=409,
                detail=(
                    "NO AVAILABLE NEXCYR AGENT — the selected agent is not online. "
                    "This target requires an authorized Agent inside the target network."
                ),
            )
        job_type = scan_job_type
        if not agent_service.agent_supports_job(agent, job_type):
            raise HTTPException(
                status_code=409,
                detail="Selected agent lacks the scanner capability for this scan type.",
            )

        scan = Scan(
            assessment_id=data.assessment_id or target.assessment_id,
            target_id=target.id,
            scan_type=scan_type,
            status="queued",
            execution_source="AGENT",
            agent_id=agent.id,
            agent_name=agent.name,
            agent_version=agent.version,
        )
        db.add(scan)
        db.flush()
        job = agent_service.create_job(
            db,
            target,
            agent,
            job_type,
            {
                "target": target.value,
                "ports_profile": "safe_default",
                "discovery": job_type == "NMAP_HOST_DISCOVERY",
            },
            scan,
            scan.assessment_id,
        )
        db.commit()
        db.refresh(scan)
        db.refresh(job)
        logger.info(
            "Scan %s queued for agent %s (job %s); not executed locally",
            scan.id,
            agent.agent_key,
            job.id,
        )
        payload = serialize_scan(db, scan)
        payload["job"] = serialize_job(job, agent)
        return payload

    # A CIDR/network target must be executed from an Agent. The cloud scanner
    # cannot see the operator's private LAN and must never pretend otherwise.
    if target.target_type == "network" and scan_type in {"basic", "service", "stealth"}:
        raise HTTPException(
            status_code=409,
            detail="Network/CIDR targets require an online NexCYR Agent for discovery and scanning.",
        )

    # ---- Cloud Scanner path ----
    scan = Scan(
        assessment_id=data.assessment_id or target.assessment_id,
        target_id=target.id,
        scan_type=scan_type,
        status="running",
        execution_source="CLOUD",
        started_at=datetime.now(timezone.utc),
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    if scan_type == "service":
        recon = enumerate_services(target.value)
        services = recon.get("services", [])
        open_ports = []
    elif scan_type == "basic":
        # Basic cloud scans do not require Nmap. They use safe TCP connect
        # checks against NexCYR's fixed common-port profile.
        recon = run_recon(target.value, "port_discovery")
        services = []
        open_ports = recon.get("open_ports", [])
    else:
        # A true stealth/Nmap profile belongs on an enrolled Agent so the
        # platform never pretends that the cloud scanner performed it.
        recon = {
            "status": "agent_required",
            "services": [],
            "open_ports": [],
            "error": "Stealth Nmap scanning requires an online NexCYR Agent.",
        }
        services = []
        open_ports = []

    created_findings = []
    if services:
        for service, analyzed in zip(services, analyze_services(services)):
            severity = str(analyzed.get("severity", "info")).lower()
            if severity == "informational":
                severity = "info"
            finding = Finding(
                assessment_id=scan.assessment_id,
                target_id=target.id,
                scan_id=scan.id,
                title=analyzed.get("title", "Scan observation"),
                severity=severity,
                status=analyzed.get("status", "open"),
                description=analyzed.get("description"),
                evidence=analyzed.get("evidence"),
                remediation="; ".join(analyzed.get("recommendations", [])) or None,
                source=analyzed.get("source", "nmap-scan"),
                confidence=analyzed.get("confidence"),
            )
            risk = calculate_finding_risk(
                {
                    "title": finding.title,
                    "severity": severity,
                    "port": service.get("port"),
                    "service": service.get("service"),
                    "version": service.get("version"),
                    "state": service.get("state"),
                }
            )
            finding.risk_score = risk["risk_score"]
            finding.risk_level = risk["risk_level"]
            finding.risk_factors = ";".join(
                analyzed.get("risk_factors") or risk.get("risk_factors", [])
            )
            finding.recommendations = ";".join(
                analyzed.get("recommendations") or risk.get("recommendations", [])
            )
            finding.confidence = analyzed.get("confidence") or risk.get("confidence")
            db.add(finding)
            created_findings.append(finding)

    scan.completed_at = datetime.now(timezone.utc)
    if recon.get("status") == "completed":
        scan.status = "completed"
        if scan_type == "service":
            open_services = [s for s in services if s.get("state") == "open"]
            scan.result_summary = (
                f"{len(open_services)} open service(s) detected on {target.value}"
                if services
                else f"No open services detected on {target.value}"
            )
            scan.result_data = json.dumps({"services": services}, default=str)
        else:
            scan.result_summary = (
                f"{len(open_ports)} open port(s) detected on {target.value}"
                if open_ports
                else f"No open ports detected on {target.value}"
            )
            scan.result_data = json.dumps({
                "open_ports": open_ports,
                "checked_ports": recon.get("checked_ports", []),
            }, default=str)
    elif recon.get("status") == "nmap_unavailable":
        scan.status = "nmap_unavailable"
        scan.error = recon.get("error")
        scan.result_summary = "Nmap is not installed; use an online NexCYR Agent for Nmap scans."
    elif recon.get("status") == "agent_required":
        scan.status = "agent_required"
        scan.error = recon.get("error")
        scan.result_summary = "This scan profile must run from an online NexCYR Agent."
    else:
        scan.status = "failed"
        scan.error = recon.get("error") or "Scan did not complete."
        scan.result_summary = "Scan failed; no results were produced."

    db.commit()
    db.refresh(scan)

    if scan.assessment_id:
        from models.assessment import Assessment

        assessment = db.get(Assessment, scan.assessment_id)
        if assessment:
            refresh_assessment_risk(db, assessment)

    logger.info(
        "Scan %s on target %s finished with status %s (%d findings)",
        scan.id,
        target.value,
        scan.status,
        len(created_findings),
    )

    payload = serialize_scan(db, scan)
    payload["findings"] = [serialize_finding(f) for f in created_findings]
    return payload


@router.get("")
def list_scans(
    assessment_id: int | None = None,
    target_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Scan)
    if assessment_id is not None:
        query = query.filter(Scan.assessment_id == assessment_id)
    if target_id is not None:
        query = query.filter(Scan.target_id == target_id)
    if status:
        query = query.filter(Scan.status == status.strip().lower())
    scans = query.order_by(Scan.id.desc()).all()
    return [serialize_scan(db, s) for s in scans]


@router.get("/summary")
def scans_summary(db: Session = Depends(get_db)):
    scans = db.query(Scan).all()
    by_status = {}
    for scan in scans:
        by_status[scan.status] = by_status.get(scan.status, 0) + 1

    findings = db.query(Finding).filter(Finding.scan_id.isnot(None)).all()
    overall = calculate_overall_risk(
        [{"severity": f.severity, "risk_score": f.risk_score} for f in findings]
    )
    from models.agent import Agent
    from services.agent_service import serialize_agent

    agents = db.query(Agent).all()
    online_agent_nmap = any(
        serialize_agent(a)["status"] == "online" and serialize_agent(a)["nmap_available"]
        for a in agents
    )

    return {
        "total_scans": len(scans),
        "by_status": by_status,
        "nmap_available": nmap_available() or online_agent_nmap,
        "cloud_nmap_available": nmap_available(),
        "agent_nmap_available": online_agent_nmap,
        "findings_from_scans": len(findings),
        "overall_risk_level": overall["overall_risk"],
        "overall_risk_score": overall["overall_score"],
    }


@router.get("/{scan_id}")
def get_scan(scan_id: int, db: Session = Depends(get_db)):
    return serialize_scan(db, get_scan_or_404(db, scan_id))


@router.get("/{scan_id}/status")
def get_scan_status(scan_id: int, db: Session = Depends(get_db)):
    scan = get_scan_or_404(db, scan_id)
    return {
        "id": scan.id,
        "status": scan.status,
        "started_at": to_iso(scan.started_at),
        "completed_at": to_iso(scan.completed_at),
        "error": scan.error,
    }


@router.get("/{scan_id}/results")
def get_scan_results(scan_id: int, db: Session = Depends(get_db)):
    scan = get_scan_or_404(db, scan_id)
    findings = db.query(Finding).filter(Finding.scan_id == scan.id).all()
    return {
        "scan": serialize_scan(db, scan),
        "findings": [serialize_finding(f) for f in findings],
    }


@router.delete("/{scan_id}")
def delete_scan(scan_id: int, db: Session = Depends(get_db)):
    scan = get_scan_or_404(db, scan_id)
    assessment_id = scan.assessment_id
    db.query(Finding).filter(Finding.scan_id == scan.id).update({"scan_id": None})
    db.delete(scan)
    db.commit()
    if assessment_id:
        from models.assessment import Assessment

        assessment = db.get(Assessment, assessment_id)
        if assessment:
            refresh_assessment_risk(db, assessment)
    return {"message": "Scan deleted successfully", "id": scan_id}
