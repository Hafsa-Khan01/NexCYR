"""Wi-Fi security routes — safe configuration assessment only.

Discovery uses the operating system's own passive WLAN information
(netsh on Windows). No deauthentication, injection or any unauthorized
Wi-Fi attack is ever performed.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.utils import to_iso
from database import get_db
from models.agent import Agent, compute_agent_status
from models.wifi_assessment import WiFiAssessment
from services import agent_service, wifi_service

router = APIRouter(prefix="/api/wifi", tags=["Wi-Fi Security"])


class WiFiCreate(BaseModel):
    ssid: str = Field(..., min_length=1, max_length=255)
    security_type: str | None = Field(default=None, max_length=50)
    channel: str | None = Field(default=None, max_length=50)
    assessment: str | None = None
    status: str = Field(default="created", max_length=30)
    notes: str | None = None


class WiFiUpdate(BaseModel):
    ssid: str | None = Field(default=None, min_length=1, max_length=255)
    security_type: str | None = None
    channel: str | None = None
    assessment: str | None = None
    status: str | None = None
    notes: str | None = None


def serialize_wifi(w: WiFiAssessment) -> dict:
    return {
        "id": w.id,
        "ssid": w.ssid,
        "security_type": w.security_type,
        "channel": w.channel,
        "assessment": w.assessment,
        "status": w.status,
        "notes": w.notes,
        "findings_count": w.findings_count,
        "security_summary": w.security_summary,
        "created_at": to_iso(w.created_at),
        "updated_at": to_iso(w.updated_at),
    }


def get_wifi_or_404(db: Session, wifi_id: int) -> WiFiAssessment:
    record = db.get(WiFiAssessment, wifi_id)
    if not record:
        raise HTTPException(status_code=404, detail="Wi-Fi assessment not found")
    return record


@router.post("/assessments", status_code=201)
def create_wifi_assessment(data: WiFiCreate, db: Session = Depends(get_db)):
    record = WiFiAssessment(
        ssid=data.ssid.strip(),
        security_type=(data.security_type or "").strip() or None,
        channel=(data.channel or "").strip() or None,
        assessment=data.assessment,
        status=(data.status or "created").strip().lower(),
        notes=data.notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return serialize_wifi(record)


@router.get("/assessments")
def list_wifi_assessments(db: Session = Depends(get_db)):
    records = db.query(WiFiAssessment).order_by(WiFiAssessment.id.desc()).all()
    return [serialize_wifi(r) for r in records]


@router.get("/sensor/status")
def sensor_status(db: Session = Depends(get_db)):
    local = wifi_service.get_wifi_sensor_status()

    online_agents = []
    for agent in db.query(Agent).all():
        if compute_agent_status(agent) != "online":
            continue
        caps = agent_service.capabilities_of(agent)
        if not caps.get("wifi"):
            continue
        health = agent_service.parse_json(agent.health)
        snapshot = health.get("wifi_snapshot") if isinstance(health, dict) else None
        online_agents.append({
            "id": agent.id,
            "name": agent.name,
            "interface": (snapshot or {}).get("interface"),
            "current_ssid": (snapshot or {}).get("current_ssid"),
            "local_network": (snapshot or {}).get("local_network"),
            "networks": (snapshot or {}).get("networks") or [],
        })

    if local.get("sensor_status") == "available":
        local["source"] = "CLOUD"
        local["agents"] = online_agents
        return local

    if online_agents:
        selected = online_agents[0]
        return {
            "sensor_status": "available",
            "source": "AGENT",
            "interface": selected.get("interface"),
            "reason": f"Wi-Fi sensor available through NexCYR Agent · {selected['name']}",
            "agent_id": selected["id"],
            "agent_name": selected["name"],
            "current_ssid": selected.get("current_ssid"),
            "local_network": selected.get("local_network"),
            "networks": selected.get("networks") or [],
            "agents": online_agents,
        }

    return {
        **local,
        "source": "CLOUD",
        "agents": [],
        "networks": [],
    }


@router.get("/assessments/{wifi_id}")
def get_wifi_assessment(wifi_id: int, db: Session = Depends(get_db)):
    return serialize_wifi(get_wifi_or_404(db, wifi_id))


@router.put("/assessments/{wifi_id}")
def update_wifi_assessment(wifi_id: int, data: WiFiUpdate, db: Session = Depends(get_db)):
    record = get_wifi_or_404(db, wifi_id)
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if value is not None:
            setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return serialize_wifi(record)


@router.delete("/assessments/{wifi_id}")
def delete_wifi_assessment(wifi_id: int, db: Session = Depends(get_db)):
    record = get_wifi_or_404(db, wifi_id)
    db.delete(record)
    db.commit()
    return {"message": "Wi-Fi assessment deleted successfully", "id": wifi_id}


@router.post("/assessments/{wifi_id}/discover")
def discover_for_assessment(wifi_id: int, db: Session = Depends(get_db)):
    """Passive discovery using Cloud local sensor or the first online Wi-Fi-capable Agent."""
    record = get_wifi_or_404(db, wifi_id)
    discovery = wifi_service.discover_windows_wifi_networks()
    networks = discovery.get("networks", [])
    source = "CLOUD"
    agent_name = None
    interface = None
    local_network = None

    if not discovery.get("success"):
        selected = None
        for agent in db.query(Agent).all():
            if compute_agent_status(agent) != "online":
                continue
            caps = agent_service.capabilities_of(agent)
            if not caps.get("wifi"):
                continue
            snapshot = agent_service.parse_json(agent.health).get("wifi_snapshot")
            if isinstance(snapshot, dict) and snapshot.get("networks") is not None:
                selected = (agent, snapshot)
                break

        if selected:
            agent, snapshot = selected
            networks = snapshot.get("networks") or []
            source = "AGENT"
            agent_name = agent.name
            interface = snapshot.get("interface")
            local_network = snapshot.get("local_network")
            discovery = {"success": bool(networks), "reason": None if networks else "Agent returned no visible Wi-Fi networks."}

    if not discovery.get("success"):
        return {
            "success": False,
            "reason": discovery.get("reason"),
            "networks": [],
            "assessment": serialize_wifi(record),
        }

    assessment = wifi_service.assess_wifi_security(networks)
    matched = next(
        (n for n in networks if (n.get("ssid") or "").strip().lower() == record.ssid.strip().lower()),
        None,
    )
    if matched:
        record.security_type = matched.get("authentication") or record.security_type
        record.channel = str(matched.get("channel") or record.channel or "")
    if assessment:
        record.security_summary = str(assessment)[:2000]
    record.assessment = json.dumps({
        "source": source,
        "agent": agent_name,
        "interface": interface,
        "local_network": local_network,
        "networks": networks,
    }, default=str)
    record.status = "completed"
    db.commit()
    db.refresh(record)

    return {
        "success": True,
        "reason": None,
        "source": source,
        "agent_name": agent_name,
        "interface": interface,
        "local_network": local_network,
        "networks": networks,
        "assessment": serialize_wifi(record),
    }
