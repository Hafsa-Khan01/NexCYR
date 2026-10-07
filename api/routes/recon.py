"""Recon routes — authorized, non-destructive reconnaissance only."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.utils import to_iso
from database import get_db
from models.recon_result import ReconResult, RECON_TYPES
from models.target import Target
from services import recon_service

logger = logging.getLogger("nexcyr.recon.routes")

router = APIRouter(prefix="/api/recon", tags=["Recon"])


class ReconRequest(BaseModel):
    target_id: int
    recon_type: str = Field(..., max_length=50)
    assessment_id: int | None = None


def serialize_recon(result: ReconResult) -> dict:
    data = None
    if result.result_data:
        try:
            data = json.loads(result.result_data)
        except json.JSONDecodeError:
            data = None
    return {
        "id": result.id,
        "target_id": result.target_id,
        "assessment_id": result.assessment_id,
        "recon_type": result.recon_type,
        "value": result.value,
        "status": result.status,
        "result": data,
        "created_at": to_iso(result.created_at),
    }


@router.post("", status_code=201)
def start_recon(data: ReconRequest, db: Session = Depends(get_db)):
    target = db.get(Target, data.target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    if not target.authorized:
        raise HTTPException(
            status_code=400,
            detail=(
                "Target is not authorized for reconnaissance. "
                "Record explicit authorization first."
            ),
        )

    recon_type = data.recon_type.strip().lower()
    if recon_type not in RECON_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"recon_type must be one of: {', '.join(sorted(RECON_TYPES))}",
        )

    try:
        result_data = recon_service.run_recon(target.value, recon_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Recon failed for target %s", target.value)
        raise HTTPException(status_code=500, detail="Reconnaissance failed unexpectedly.")

    record = ReconResult(
        target_id=target.id,
        assessment_id=data.assessment_id or target.assessment_id,
        recon_type=recon_type,
        value=target.value,
        status=result_data.get("status", "completed"),
        result_data=recon_service.dump_result(result_data),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return serialize_recon(record)


@router.get("")
def list_recon_results(
    target_id: int | None = None,
    assessment_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(ReconResult)
    if target_id is not None:
        query = query.filter(ReconResult.target_id == target_id)
    if assessment_id is not None:
        query = query.filter(ReconResult.assessment_id == assessment_id)
    results = query.order_by(ReconResult.id.desc()).all()
    return [serialize_recon(r) for r in results]


@router.get("/{recon_id}")
def get_recon_result(recon_id: int, db: Session = Depends(get_db)):
    result = db.get(ReconResult, recon_id)
    if not result:
        raise HTTPException(status_code=404, detail="Recon result not found")
    return serialize_recon(result)
