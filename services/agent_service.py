"""NexCYR Agent service — enrollment, authentication, jobs, results.

Security model:
  * The Cloud never sends shell commands; jobs carry structured params only.
  * Agent credentials are stored as SHA-256 hashes; plaintext is returned once.
  * Every job is validated for job type, target authorization, agent
    enablement/online state and scanner capability before it is queued.
  * Incoming agent results are validated structurally; findings are derived
    by the central risk/vulnerability engines, never trusted verbatim.
"""

import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.agent import (
    AGENT_STATUS_ONLINE,
    Agent,
    compute_agent_status,
)
from models.audit_event import AuditEvent
from models.finding import Finding
from models.scan import Scan
from models.scan_job import (
    EXECUTION_AGENT,
    JOB_STATUS_CANCELLED,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    VALID_JOB_TYPES,
    ScanJob,
)
from models.target import Target
from services.risk_engine import calculate_finding_risk
from services.vulnerability_engine import analyze_services

logger = logging.getLogger("nexcyr.agents")

# Capability keys an agent may report.
CAPABILITY_KEYS = (
    "nmap",
    "host_discovery",
    "port_scan",
    "service_enumeration",
    "wifi",
)

# Map job type -> capability required on the agent.
JOB_CAPABILITY = {
    "NMAP_HOST_DISCOVERY": "host_discovery",
    "NMAP_PORT_SCAN": "port_scan",
    "NMAP_SERVICE_ENUMERATION": "service_enumeration",
    "AUTHORIZED_RECON": "host_discovery",
    "WIFI_DISCOVERY": "wifi",
}


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(agent: Agent | None, token: str | None) -> bool:
    if agent is None or not token or not agent.token_hash:
        return False
    if agent.status == "revoked" or not agent.enabled:
        return False
    return secrets.compare_digest(agent.token_hash, hash_token(token))


def default_capabilities() -> dict:
    return {k: False for k in CAPABILITY_KEYS}


def parse_json(text: str | None) -> dict:
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def capabilities_of(agent: Agent) -> dict:
    caps = default_capabilities()
    caps.update(parse_json(agent.capabilities))
    return caps


def agent_supports_job(agent: Agent, job_type: str) -> bool:
    needed = JOB_CAPABILITY.get(job_type)
    if not needed:
        return False
    caps = capabilities_of(agent)
    if needed == "host_discovery":
        return bool(caps.get("host_discovery")) or bool(caps.get("nmap"))
    return bool(caps.get(needed)) or bool(caps.get("nmap"))


def record_audit(
    db: Session,
    action: str,
    actor: str = "operator",
    entity_type: str | None = None,
    entity_id: int | None = None,
    detail: str | None = None,
    agent_id: int | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor=actor,
        agent_id=agent_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=(detail or "")[:2000] or None,
    )
    db.add(event)
    return event


def serialize_agent(agent: Agent, now: datetime | None = None) -> dict:
    status = compute_agent_status(agent, now)
    caps = capabilities_of(agent)
    health = parse_json(agent.health)
    last_seen = agent.last_seen
    age = None
    if last_seen is not None:
        ref = now or datetime.now(timezone.utc)
        seen = last_seen if last_seen.tzinfo else last_seen.replace(tzinfo=ref.tzinfo)
        age = max(0, int((ref - seen).total_seconds()))
    return {
        "id": agent.id,
        "agent_key": agent.agent_key,
        "name": agent.name,
        "hostname": agent.hostname,
        "platform": agent.platform,
        "os_info": agent.os_info,
        "arch": agent.arch,
        "version": agent.version,
        "status": status,
        "enabled": bool(agent.enabled),
        "capabilities": caps,
        "nmap_available": bool(caps.get("nmap")),
        "health": health,
        "assigned_scope": agent.assigned_scope,
        "current_job_id": agent.current_job_id,
        "last_seen": last_seen.isoformat() if last_seen else None,
        "last_seen_seconds_ago": age,
        "registered_at": agent.registered_at.isoformat() if agent.registered_at else None,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
    }


def serialize_job(job: ScanJob, agent: Agent | None = None) -> dict:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "params": parse_json(job.params),
        "status": job.status,
        "execution_source": job.execution_source,
        "agent_id": job.agent_id,
        "agent_name": agent.name if agent else None,
        "scan_id": job.scan_id,
        "target_id": job.target_id,
        "assessment_id": job.assessment_id,
        "result": parse_json(job.result) if job.result else None,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "claimed_at": job.claimed_at.isoformat() if job.claimed_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def create_enrollment(db: Session, name: str, agent_key: str | None = None, assigned_scope: str | None = None):
    """Operator creates an agent enrollment; returns (agent, one_time_token)."""
    key = (agent_key or "").strip() or f"AGENT-{secrets.token_hex(3).upper()}"
    agent = Agent(
        agent_key=key,
        name=(name or key).strip(),
        status="enrolled",
        enabled=True,
        assigned_scope=assigned_scope,
    )
    token = generate_token()
    agent.token_hash = hash_token(token)
    db.add(agent)
    db.flush()
    record_audit(
        db,
        "agent_enrolled",
        actor="operator",
        entity_type="agent",
        entity_id=agent.id,
        detail=f"Enrollment created for {agent.agent_key}",
        agent_id=agent.id,
    )
    db.commit()
    db.refresh(agent)
    return agent, token


def register_agent(db: Session, agent: Agent, payload: dict) -> Agent:
    """Agent (already credential-verified) reports system info to register."""
    now = datetime.now(timezone.utc)
    agent.hostname = (payload.get("hostname") or agent.hostname or "")[:120] or None
    agent.platform = (payload.get("platform") or "")[:40] or None
    agent.os_info = (payload.get("os_info") or "")[:120] or None
    agent.arch = (payload.get("arch") or "")[:40] or None
    agent.version = (payload.get("version") or "")[:40] or None
    caps = default_capabilities()
    reported = payload.get("capabilities") or {}
    if isinstance(reported, dict):
        for k in CAPABILITY_KEYS:
            caps[k] = bool(reported.get(k))
    agent.capabilities = json.dumps(caps)
    agent.health = json.dumps({
        "registered_via": "token",
        "uptime": payload.get("uptime"),
        "wifi_snapshot": payload.get("wifi_snapshot") if isinstance(payload.get("wifi_snapshot"), dict) else {},
    })
    agent.registered_at = agent.registered_at or now
    agent.last_seen = now
    agent.status = AGENT_STATUS_ONLINE
    record_audit(
        db,
        "agent_registered",
        actor="agent",
        entity_type="agent",
        entity_id=agent.id,
        detail=f"{agent.agent_key} identity verified and registered",
        agent_id=agent.id,
    )
    db.commit()
    db.refresh(agent)
    return agent


def heartbeat(db: Session, agent: Agent, payload: dict) -> Agent:
    now = datetime.now(timezone.utc)
    agent.last_seen = now
    if payload.get("version"):
        agent.version = str(payload["version"])[:40]
    reported = payload.get("capabilities")
    if isinstance(reported, dict):
        caps = capabilities_of(agent)
        for k in CAPABILITY_KEYS:
            if k in reported:
                caps[k] = bool(reported[k])
        agent.capabilities = json.dumps(caps)
    health = {
        "cpu": payload.get("cpu"),
        "memory": payload.get("memory"),
        "uptime": payload.get("uptime"),
        "reported_at": now.isoformat(),
        "wifi_snapshot": payload.get("wifi_snapshot") if isinstance(payload.get("wifi_snapshot"), dict) else {},
    }
    agent.health = json.dumps(health)
    agent.status = AGENT_STATUS_ONLINE
    db.commit()
    db.refresh(agent)
    return agent


def create_job(
    db: Session,
    target: Target,
    agent: Agent | None,
    job_type: str,
    params: dict,
    scan: Scan | None = None,
    assessment_id: int | None = None,
) -> ScanJob:
    job = ScanJob(
        job_type=job_type,
        params=json.dumps(params, default=str),
        status=JOB_STATUS_QUEUED if agent else JOB_STATUS_PENDING,
        execution_source=EXECUTION_AGENT if agent else "CLOUD",
        agent_id=agent.id if agent else None,
        scan_id=scan.id if scan else None,
        target_id=target.id,
        assessment_id=assessment_id,
    )
    db.add(job)
    db.flush()
    if agent:
        agent.current_job_id = job.id
    record_audit(
        db,
        "scan_job_created",
        actor="operator",
        entity_type="scan_job",
        entity_id=job.id,
        detail=f"{job_type} on target #{target.id} via "
        + (agent.agent_key if agent else "Cloud Scanner"),
        agent_id=agent.id if agent else None,
    )
    return job


def claim_next_job(db: Session, agent: Agent) -> ScanJob | None:
    job = (
        db.query(ScanJob)
        .filter(ScanJob.agent_id == agent.id)
        .filter(ScanJob.status.in_([JOB_STATUS_PENDING, JOB_STATUS_QUEUED]))
        .order_by(ScanJob.id.asc())
        .first()
    )
    if not job:
        return None
    job.status = JOB_STATUS_RUNNING
    job.claimed_at = datetime.now(timezone.utc)
    agent.current_job_id = job.id
    record_audit(
        db,
        "scan_job_started",
        actor="agent",
        entity_type="scan_job",
        entity_id=job.id,
        detail=f"{agent.agent_key} claimed job #{job.id}",
        agent_id=agent.id,
    )
    db.commit()
    db.refresh(job)
    return job


def _validated_services(raw) -> list:
    """Validate an agent-submitted services list into a safe structure."""
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            port = int(item.get("port"))
        except (TypeError, ValueError):
            continue
        if not (0 < port <= 65535):
            continue
        out.append(
            {
                "port": port,
                "state": str(item.get("state") or "open")[:20],
                "service": str(item.get("service") or "unknown")[:60],
                "version": str(item.get("version") or "")[:120],
            }
        )
    return out[:500]


def _validated_hosts(raw) -> list:
    """Validate agent-reported host discovery records."""
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        address = str(item.get("address") or item.get("ip") or "").strip()
        if not address or len(address) > 64:
            continue
        out.append({
            "address": address,
            "state": str(item.get("state") or "up")[:20],
            "hostname": str(item.get("hostname") or "")[:255],
        })
    return out[:1024]


def _validated_wifi_networks(raw) -> list:
    """Validate passive Wi-Fi observations returned by a local agent."""
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ssid = str(item.get("ssid") or "").strip()[:255]
        if not ssid:
            continue
        out.append({
            "ssid": ssid,
            "authentication": str(item.get("authentication") or "Unknown")[:80],
            "encryption": str(item.get("encryption") or "")[:80],
            "channel": str(item.get("channel") or "")[:20],
            "signal": str(item.get("signal") or "")[:20],
            "bssid": str(item.get("bssid") or "")[:80],
        })
    return out[:200]


def submit_job_result(db: Session, job: ScanJob, agent: Agent, payload: dict) -> ScanJob:
    """Ingest a structured agent result; derive findings centrally."""
    status = str(payload.get("status") or "").strip().lower()
    if status == JOB_STATUS_COMPLETED:
        results = payload.get("results") or {}
        services = _validated_services(results.get("services"))
        hosts = _validated_hosts(results.get("hosts"))
        wifi_networks = _validated_wifi_networks(results.get("wifi_networks"))
        job.result = json.dumps(
            {
                "hosts": hosts,
                "ports": results.get("ports") or [],
                "services": services,
                "wifi_networks": wifi_networks,
                "wifi_interface": str(results.get("wifi_interface") or "")[:120],
                "local_network": str(results.get("local_network") or "")[:64],
            },
            default=str,
        )
        job.status = JOB_STATUS_COMPLETED
        job.completed_at = datetime.now(timezone.utc)

        scan = db.get(Scan, job.scan_id) if job.scan_id else None
        if scan is not None:
            scan.status = "completed"
            scan.completed_at = datetime.now(timezone.utc)
            scan.execution_source = "AGENT"
            scan.agent_id = agent.id
            scan.agent_name = agent.name
            scan.agent_version = agent.version

            if job.job_type == "NMAP_HOST_DISCOVERY":
                scan.result_summary = (
                    f"{len(hosts)} live host(s) discovered via {agent.agent_key}"
                    if hosts
                    else f"No live hosts discovered via {agent.agent_key}"
                )
                scan.result_data = json.dumps({"hosts": hosts}, default=str)
                scan.error = None
            else:
                open_services = [s for s in services if s.get("state") == "open"]
                scan.result_summary = (
                    f"{len(open_services)} open service(s) detected via {agent.agent_key}"
                    if services
                    else f"No open services detected via {agent.agent_key}"
                )
                scan.result_data = json.dumps({
                    "services": services,
                    "hosts": hosts,
                }, default=str)

                created = 0
                for service, analyzed in zip(services, analyze_services(services)):
                    severity = str(analyzed.get("severity", "info")).lower()
                    if severity == "informational":
                        severity = "info"
                    finding = Finding(
                        assessment_id=scan.assessment_id,
                        target_id=scan.target_id,
                        scan_id=scan.id,
                        title=analyzed.get("title", "Scan observation"),
                        severity=severity,
                        status=analyzed.get("status", "open"),
                        description=analyzed.get("description"),
                        evidence=analyzed.get("evidence"),
                        remediation="; ".join(analyzed.get("recommendations", [])) or None,
                        source=f"agent:{agent.agent_key}",
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
                    db.add(finding)
                    created += 1
                logger.info("Agent job %s produced %d finding(s)", job.id, created)

        # Wi-Fi discovery is passive and non-disruptive. Persist the latest
        # observation on the linked assessment when the job carries an ID.
        if job.job_type == "WIFI_DISCOVERY":
            params = parse_json(job.params)
            wifi_id = params.get("wifi_assessment_id")
            if wifi_id:
                from models.wifi_assessment import WiFiAssessment
                record = db.get(WiFiAssessment, int(wifi_id))
                if record:
                    selected = next(
                        (n for n in wifi_networks if n["ssid"].lower() == record.ssid.lower()),
                        None,
                    )
                    if selected:
                        record.security_type = selected.get("authentication") or record.security_type
                        record.channel = selected.get("channel") or record.channel
                    record.assessment = json.dumps({
                        "agent": agent.name,
                        "interface": str(results.get("wifi_interface") or "")[:120],
                        "local_network": str(results.get("local_network") or "")[:64],
                        "networks": wifi_networks,
                    }, default=str)
                    record.findings_count = 0
                    if selected := next((n for n in wifi_networks if n["ssid"].lower() == record.ssid.lower()), None):
                        record.security_summary = (
                            f"{selected.get('authentication', 'Unknown')} "
                            f"{selected.get('encryption', '')}".strip()
                        )
                    else:
                        record.security_summary = "SSID not observed by the Agent."
                    record.status = "completed"

        record_audit(
            db,
            "scan_job_completed",
            actor="agent",
            entity_type="scan_job",
            entity_id=job.id,
            detail=f"{agent.agent_key} completed job #{job.id}",
            agent_id=agent.id,
        )
    elif status == JOB_STATUS_FAILED:
        job.status = JOB_STATUS_FAILED
        job.error = str(payload.get("error") or "Agent reported failure")[:2000]
        job.completed_at = datetime.now(timezone.utc)
        scan = db.get(Scan, job.scan_id) if job.scan_id else None
        if scan is not None:
            scan.status = "failed"
            scan.error = job.error
            scan.completed_at = datetime.now(timezone.utc)
        record_audit(
            db,
            "scan_job_failed",
            actor="agent",
            entity_type="scan_job",
            entity_id=job.id,
            detail=job.error,
            agent_id=agent.id,
        )
    else:
        # Unknown statuses are treated as progress updates, not completion.
        if status == JOB_STATUS_RUNNING:
            job.status = JOB_STATUS_RUNNING
    agent.current_job_id = None if job.status in (JOB_STATUS_COMPLETED, JOB_STATUS_FAILED) else job.id
    db.commit()
    db.refresh(job)
    return job


def cancel_job(db: Session, job: ScanJob) -> ScanJob:
    job.status = JOB_STATUS_CANCELLED
    job.completed_at = datetime.now(timezone.utc)
    record_audit(
        db,
        "scan_job_cancelled",
        actor="operator",
        entity_type="scan_job",
        entity_id=job.id,
        detail=f"Job #{job.id} cancelled",
        agent_id=job.agent_id,
    )
    db.commit()
    db.refresh(job)
    return job
