"""Create idempotent SOC records from real NexCYR operations only."""
import json
from sqlalchemy.orm import Session
from models.finding import Finding
from models.recon_result import ReconResult
from models.scan import Scan
from models.soc_event import SOCEvent
from models.target import Target

VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}

def _severity(value: str | None, fallback: str = "info") -> str:
    cleaned = (value or fallback).strip().lower()
    if cleaned == "informational":
        return "info"
    return cleaned if cleaned in VALID_SEVERITIES else fallback

def _add_event(db: Session, *, event_type: str, source: str, message: str,
               severity: str, status: str, assessment_id: int | None,
               target_id: int | None, detected_by: str, raw_data: dict) -> SOCEvent:
    raw_text = json.dumps(raw_data, sort_keys=True, separators=(",", ":"))
    existing = (db.query(SOCEvent).filter(
        SOCEvent.event_type == event_type, SOCEvent.source == source,
        SOCEvent.raw_data == raw_text).first())
    if existing:
        return existing
    event = SOCEvent(event_type=event_type, source=source, message=message[:4000],
        severity=_severity(severity), status=status, assessment_id=assessment_id,
        target_id=target_id, detected_by=detected_by, raw_data=raw_text)
    db.add(event)
    db.flush()
    return event

def record_finding_event(db: Session, finding: Finding, target: Target | None = None) -> SOCEvent:
    """Record a real manual finding or scanner-derived vulnerability."""
    db.flush()
    severity = _severity(finding.severity)
    origin = (finding.source or "manual").strip().lower()
    target_label = target.value if target else (
        f"target #{finding.target_id}" if finding.target_id else "unlinked target")
    if origin in {"manual", "operator", "manual-entry"}:
        event_type, source, detected_by = "finding_recorded", "NexCYR Findings", "NexCYR operator"
        message = f"Finding #{finding.id} recorded by the operator: {finding.title} ({severity}) on {target_label}."
    else:
        event_type = "vulnerability_detected"
        source = "NexCYR Agent" if origin.startswith("agent:") else "NexCYR Scanner"
        detected_by = finding.source or source
        message = f"{severity.title()} finding #{finding.id} detected: {finding.title} on {target_label}."
    return _add_event(db, event_type=event_type, source=source, message=message,
        severity=severity, status="open" if severity in {"critical","high","medium"} else "closed",
        assessment_id=finding.assessment_id, target_id=finding.target_id, detected_by=detected_by,
        raw_data={"finding_id": int(finding.id), "scan_id": finding.scan_id})

def record_scan_event(db: Session, scan: Scan, target: Target | None) -> SOCEvent:
    """Record scan state/result without falsely calling the scan itself a vulnerability."""
    status = (scan.status or "unknown").strip().lower()
    label = target.value if target else f"target #{scan.target_id}"
    if status in {"queued","pending"}:
        event_type, message, event_status, severity = "scan_queued", f"Authorized {scan.scan_type} scan #{scan.id} queued for {label}.", "closed", "info"
    elif status == "running":
        event_type, message, event_status, severity = "scan_started", f"Authorized {scan.scan_type} scan #{scan.id} started for {label}.", "closed", "info"
    elif status == "completed":
        event_type, message, event_status, severity = "scan_completed", f"Authorized {scan.scan_type} scan #{scan.id} completed for {label}. {scan.result_summary or 'Results are stored in NexCYR.'}", "closed", "info"
    else:
        detail = scan.error or scan.result_summary or f"status: {status}"
        event_type, message, event_status, severity = "scan_failed", f"Authorized {scan.scan_type} scan #{scan.id} did not complete for {label}. {detail}", "open", "low"
    source = "NexCYR Agent" if (scan.execution_source or "").upper() == "AGENT" else "NexCYR Scanner"
    return _add_event(db, event_type=event_type, source=source, message=message, severity=severity,
        status=event_status, assessment_id=scan.assessment_id, target_id=scan.target_id,
        detected_by=scan.agent_name or source, raw_data={"scan_id": int(scan.id), "status": status})

def record_recon_event(db: Session, record: ReconResult, target: Target | None,
                       result: dict | None = None) -> SOCEvent:
    """Summarize the actual saved output of an authorized reconnaissance operation."""
    data = result if isinstance(result, dict) else {}
    status = (record.status or "unknown").strip().lower()
    label = target.value if target else record.value
    recon_label = (record.recon_type or "recon").replace("_", " ")
    if record.recon_type == "host_discovery":
        found = data.get("resolved_ips") or []
        summary = f"{len(found)} resolved address(es)" + (": " + ", ".join(str(x) for x in found[:6]) if found else "")
        if not found and status in {"unresolved","failed"}: summary = "no address was resolved"
    elif record.recon_type == "port_discovery":
        found = data.get("open_ports") or []
        summary = f"{len(found)} open TCP port(s) observed" + (": " + ", ".join(str(x) for x in found[:12]) if found else "")
    elif record.recon_type == "service_enumeration":
        found = data.get("services") or []
        labels = [f"{x.get('port','?')}/{x.get('service','unknown')}" for x in found[:6] if isinstance(x,dict)]
        summary = f"{len(found)} service record(s) returned" + (": " + ", ".join(labels) if labels else "")
    else:
        summary = f"operation status: {status}"
    completed = status in {"completed","unresolved","unreachable"}
    return _add_event(db, event_type="recon_completed" if completed else "recon_failed",
        source="NexCYR Recon", message=f"Authorized {recon_label} on {label}: {summary}.",
        severity="info" if completed else "low", status="closed" if completed else "open",
        assessment_id=record.assessment_id, target_id=record.target_id,
        detected_by="NexCYR Recon Engine", raw_data={"recon_id": int(record.id)})
