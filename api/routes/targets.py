import ipaddress
import re
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.utils import VALID_TARGET_TYPES, to_iso
from database import get_db
from models.target import Target

router = APIRouter(prefix="/api/targets", tags=["Targets"])

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)
_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?$")


def is_valid_target_value(value: str, target_type: str) -> bool:
    value = value.strip()
    if not value:
        return False

    if target_type == "ip":
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False

    if target_type == "network":
        try:
            ipaddress.ip_network(value, strict=False)
            return True
        except ValueError:
            return False

    if target_type == "domain":
        return bool(_DOMAIN_RE.match(value))

    if target_type == "url":
        parsed = urlparse(value)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    if target_type == "host":
        return bool(_HOSTNAME_RE.match(value))

    return False


class TargetCreate(BaseModel):
    assessment_id: int | None = None
    name: str | None = Field(default=None, max_length=255)
    target_type: str = Field(..., max_length=20)
    value: str = Field(..., min_length=1, max_length=255)
    authorized: bool = False
    status: str = Field(default="active", max_length=30)
    notes: str | None = None
    preferred_agent_id: int | None = None


class TargetUpdate(BaseModel):
    assessment_id: int | None = None
    name: str | None = Field(default=None, max_length=255)
    target_type: str | None = Field(default=None, max_length=20)
    value: str | None = Field(default=None, min_length=1, max_length=255)
    authorized: bool | None = None
    status: str | None = Field(default=None, max_length=30)
    notes: str | None = None
    preferred_agent_id: int | None = None


def serialize_target(target: Target) -> dict:
    return {
        "id": target.id,
        "assessment_id": target.assessment_id,
        "name": target.name,
        "target_type": target.target_type,
        "value": target.value,
        "authorized": bool(target.authorized),
        "status": target.status,
        "notes": target.notes,
        "preferred_agent_id": target.preferred_agent_id,
        "created_at": to_iso(target.created_at),
        "updated_at": to_iso(target.updated_at),
    }


def get_target_or_404(db: Session, target_id: int) -> Target:
    target = db.get(Target, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


@router.post("", status_code=201)
def create_target(data: TargetCreate, db: Session = Depends(get_db)):
    value = data.value.strip()
    target_type = data.target_type.strip().lower()

    if target_type not in VALID_TARGET_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"target_type must be one of: {', '.join(sorted(VALID_TARGET_TYPES))}",
        )
    if not is_valid_target_value(value, target_type):
        raise HTTPException(status_code=400, detail=f"Invalid {target_type} value")

    target = Target(
        assessment_id=data.assessment_id,
        name=(data.name or "").strip() or None,
        target_type=target_type,
        value=value,
        authorized=data.authorized,
        status=(data.status or "active").strip().lower(),
        notes=data.notes,
        preferred_agent_id=data.preferred_agent_id,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return serialize_target(target)


@router.get("")
def list_targets(
    assessment_id: int | None = None,
    authorized: bool | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Target)
    if assessment_id is not None:
        query = query.filter(Target.assessment_id == assessment_id)
    if authorized is not None:
        query = query.filter(Target.authorized.is_(authorized))
    targets = query.order_by(Target.id.desc()).all()
    return [serialize_target(t) for t in targets]


@router.get("/{target_id}")
def get_target(target_id: int, db: Session = Depends(get_db)):
    return serialize_target(get_target_or_404(db, target_id))


@router.put("/{target_id}")
def update_target(target_id: int, data: TargetUpdate, db: Session = Depends(get_db)):
    target = get_target_or_404(db, target_id)
    updates = data.model_dump(exclude_unset=True)

    new_type = updates.get("target_type") or target.target_type
    new_value = updates.get("value") or target.value
    if "target_type" in updates or "value" in updates:
        new_type = (new_type or "").strip().lower()
        if new_type not in VALID_TARGET_TYPES:
            raise HTTPException(status_code=400, detail="Invalid target_type")
        if not is_valid_target_value(str(new_value).strip(), new_type):
            raise HTTPException(status_code=400, detail=f"Invalid {new_type} value")
        target.target_type = new_type
        target.value = str(new_value).strip()

    for field in ("assessment_id", "name", "authorized", "status", "notes", "preferred_agent_id"):
        if field in updates:
            setattr(target, field, updates[field])

    db.commit()
    db.refresh(target)
    return serialize_target(target)


@router.delete("/{target_id}")
def delete_target(target_id: int, db: Session = Depends(get_db)):
    target = get_target_or_404(db, target_id)
    db.delete(target)
    db.commit()
    return {"message": "Target deleted successfully", "id": target_id}
