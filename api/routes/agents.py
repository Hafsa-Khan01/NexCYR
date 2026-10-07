"""NexCYR Agents API — management + secure agent-facing endpoints.

Operator endpoints manage enrollment, health, capabilities and jobs.
Agent endpoints authenticate with a bearer/enrollment token and accept
only structured job types — never arbitrary commands.
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models.agent import Agent
from models.scan_job import VALID_JOB_TYPES, ScanJob
from models.target import Target
from services import agent_service
from services.agent_service import serialize_agent, serialize_job

router = APIRouter(prefix="/api/agents", tags=["NexCYR Agents"])


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def _extract_token(
    x_nexcyr_agent_token: str | None, authorization: str | None
) -> str | None:
    if x_nexcyr_agent_token:
        return x_nexcyr_agent_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def require_agent(
    db: Session = Depends(get_db),
    x_nexcyr_agent_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Agent:
    token = _extract_token(x_nexcyr_agent_token, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Agent credential required.")
    agent = (
        db.query(Agent)
        .filter(Agent.token_hash == agent_service.hash_token(token))
        .first()
    )
    if not agent_service.verify_token(agent, token):
        raise HTTPException(status_code=401, detail="Invalid or revoked agent credential.")
    return agent


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AgentEnroll(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    agent_key: str | None = Field(default=None, max_length=60)
    assigned_scope: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    assigned_scope: str | None = None
    enabled: bool | None = None


class AgentRegister(BaseModel):
    hostname: str | None = Field(default=None, max_length=120)
    platform: str | None = Field(default=None, max_length=40)
    os_info: str | None = Field(default=None, max_length=120)
    arch: str | None = Field(default=None, max_length=40)
    version: str | None = Field(default=None, max_length=40)
    capabilities: dict | None = None
    uptime: str | None = None


class AgentHeartbeat(BaseModel):
    version: str | None = Field(default=None, max_length=40)
    capabilities: dict | None = None
    cpu: float | None = None
    memory: float | None = None
    uptime: str | None = None


class JobCreate(BaseModel):
    target_id: int
    job_type: str = Field(..., max_length=40)
    agent_id: int | None = None
    assessment_id: int | None = None
    ports_profile: str = Field(default="safe_default", max_length=30)


class JobResult(BaseModel):
    status: str = Field(..., max_length=20)
    results: dict | None = None
    error: str | None = None


class JobStatusUpdate(BaseModel):
    status: str = Field(..., max_length=20)
    error: str | None = None


# ---------------------------------------------------------------------------
# Agent-facing (token) — declared before /{agent_id} routes
# ---------------------------------------------------------------------------
@router.post("/register")
def agent_register(data: AgentRegister, agent: Agent = Depends(require_agent), db: Session = Depends(get_db)):
    updated = agent_service.register_agent(db, agent, data.model_dump())
    return serialize_agent(updated)


@router.post("/heartbeat")
def agent_heartbeat(data: AgentHeartbeat, agent: Agent = Depends(require_agent), db: Session = Depends(get_db)):
    updated = agent_service.heartbeat(db, agent, data.model_dump())
    return {"status": serialize_agent(updated)["status"], "agent_id": updated.id}


@router.get("/me/jobs/next")
def agent_next_job(agent: Agent = Depends(require_agent), db: Session = Depends(get_db)):
    job = agent_service.claim_next_job(db, agent)
    if not job:
        return {"job": None}
    target = db.get(Target, job.target_id)
    payload = serialize_job(job, agent)
    payload["target"] = target.value if target else None
    payload["target_authorized"] = bool(target.authorized) if target else False
    return {"job": payload}


@router.post("/jobs/{job_id}/result")
def agent_submit_result(
    job_id: int,
    data: JobResult,
    agent: Agent = Depends(require_agent),
    db: Session = Depends(get_db),
):
    job = db.get(ScanJob, job_id)
    if not job or job.agent_id != agent.id:
        raise HTTPException(status_code=404, detail="Job not found for this agent.")
    job = agent_service.submit_job_result(db, job, agent, data.model_dump())
    return serialize_job(job, agent)


@router.post("/jobs/{job_id}/status")
def agent_update_status(
    job_id: int,
    data: JobStatusUpdate,
    agent: Agent = Depends(require_agent),
    db: Session = Depends(get_db),
):
    job = db.get(ScanJob, job_id)
    if not job or job.agent_id != agent.id:
        raise HTTPException(status_code=404, detail="Job not found for this agent.")
    job = agent_service.submit_job_result(db, job, agent, data.model_dump())
    return serialize_job(job, agent)


# ---------------------------------------------------------------------------
# Operator: jobs
# ---------------------------------------------------------------------------
@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(ScanJob).order_by(ScanJob.id.desc()).limit(200).all()
    return [serialize_job(j, db.get(Agent, j.agent_id) if j.agent_id else None) for j in jobs]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(ScanJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return serialize_job(job, db.get(Agent, job.agent_id) if job.agent_id else None)


@router.post("/jobs", status_code=201)
def create_job(data: JobCreate, db: Session = Depends(get_db)):
    if data.job_type not in VALID_JOB_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"job_type must be one of: {', '.join(sorted(VALID_JOB_TYPES))}",
        )
    target = db.get(Target, data.target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    if not target.authorized:
        raise HTTPException(
            status_code=400,
            detail="Target is not authorized. Record explicit authorization first.",
        )
    agent = db.get(Agent, data.agent_id) if data.agent_id else None
    if data.agent_id and not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent:
        status = serialize_agent(agent)["status"]
        if status != "online":
            raise HTTPException(
                status_code=409,
                detail="NO AVAILABLE NEXCYR AGENT — selected agent is not online.",
            )
        if not agent_service.agent_supports_job(agent, data.job_type):
            raise HTTPException(
                status_code=409,
                detail="Selected agent lacks the capability for this job type.",
            )
    job = agent_service.create_job(
        db,
        target,
        agent,
        data.job_type,
        {"target": target.value, "ports_profile": data.ports_profile},
        None,
        data.assessment_id,
    )
    db.commit()
    db.refresh(job)
    return serialize_job(job, agent)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(ScanJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job = agent_service.cancel_job(db, job)
    return serialize_job(job, db.get(Agent, job.agent_id) if job.agent_id else None)


# ---------------------------------------------------------------------------
# Operator: agent management
# ---------------------------------------------------------------------------
@router.post("", status_code=201)
def enroll_agent(data: AgentEnroll, db: Session = Depends(get_db)):
    existing = None
    if data.agent_key:
        existing = db.query(Agent).filter(Agent.agent_key == data.agent_key.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="agent_key already exists")
    agent, token = agent_service.create_enrollment(
        db, data.name, data.agent_key, data.assigned_scope
    )
    payload = serialize_agent(agent)
    # The plaintext token is returned exactly once and never stored/logged.
    payload["enrollment_token"] = token
    return payload


@router.get("")
def list_agents(db: Session = Depends(get_db)):
    agents = db.query(Agent).order_by(Agent.id.asc()).all()
    return [serialize_agent(a) for a in agents]


@router.get("/audit")
def audit_trail(limit: int = 100, db: Session = Depends(get_db)):
    from models.audit_event import AuditEvent

    limit = max(1, min(500, limit))
    events = db.query(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "actor": e.actor,
            "agent_id": e.agent_id,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "detail": e.detail,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


@router.get("/{agent_id}")
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return serialize_agent(agent)


@router.put("/{agent_id}")
def update_agent(agent_id: int, data: AgentUpdate, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if data.name is not None:
        agent.name = data.name.strip()
    if data.assigned_scope is not None:
        agent.assigned_scope = data.assigned_scope
    if data.enabled is not None:
        agent.enabled = data.enabled
        agent_service.record_audit(
            db,
            "agent_enabled" if data.enabled else "agent_disabled",
            actor="operator",
            entity_type="agent",
            entity_id=agent.id,
            agent_id=agent.id,
        )
    db.commit()
    db.refresh(agent)
    return serialize_agent(agent)


@router.get("/{agent_id}/health")
def agent_health(agent_id: int, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    s = serialize_agent(agent)
    return {
        "agent_id": agent.id,
        "status": s["status"],
        "last_seen": s["last_seen"],
        "last_seen_seconds_ago": s["last_seen_seconds_ago"],
        "version": agent.version,
        "health": s["health"],
    }


@router.get("/{agent_id}/capabilities")
def agent_capabilities(agent_id: int, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"agent_id": agent.id, "capabilities": agent_service.capabilities_of(agent)}


@router.get("/{agent_id}/jobs")
def agent_jobs(agent_id: int, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    jobs = (
        db.query(ScanJob)
        .filter(ScanJob.agent_id == agent.id)
        .order_by(ScanJob.id.desc())
        .limit(100)
        .all()
    )
    return [serialize_job(j, agent) for j in jobs]


@router.post("/{agent_id}/revoke")
def revoke_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.status = "revoked"
    agent.enabled = False
    agent.token_hash = None  # invalidate credential
    agent.current_job_id = None
    agent_service.record_audit(
        db,
        "agent_revoked",
        actor="operator",
        entity_type="agent",
        entity_id=agent.id,
        detail=f"{agent.agent_key} revoked; credential invalidated",
        agent_id=agent.id,
    )
    db.commit()
    db.refresh(agent)
    return serialize_agent(agent)
