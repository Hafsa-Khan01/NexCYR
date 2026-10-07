"""Report routes — professional PDF generation with ReportLab."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.utils import to_iso
from config import Config
from database import get_db
from models.assessment import Assessment
from models.report import SecurityReport
from services.pdf_service import REPORT_FILENAME, generate_assessment_pdf
from services.report_service import build_report_data

logger = logging.getLogger("nexcyr.reports")

router = APIRouter(prefix="/api/reports", tags=["Reports"])


class ReportGenerateRequest(BaseModel):
    assessment_id: int | None = None


def serialize_report(report: SecurityReport) -> dict:
    return {
        "id": report.id,
        "assessment_id": report.assessment_id,
        "report_name": report.report_name,
        "report_type": report.report_type,
        "status": report.status,
        "risk_level": report.risk_level,
        "summary": report.summary,
        "download_url": f"/api/reports/{report.id}/download",
        "created_at": to_iso(report.created_at),
        "updated_at": to_iso(report.updated_at),
    }


def _generate_and_record(db: Session, assessment_id: int | None) -> tuple[SecurityReport, Path]:
    if assessment_id is not None and not db.get(Assessment, assessment_id):
        raise HTTPException(status_code=404, detail="Assessment not found")

    data = build_report_data(db, assessment_id)
    try:
        pdf_path = generate_assessment_pdf(data, Config.REPORTS_DIR)
    except Exception:
        logger.exception("PDF generation failed")
        raise HTTPException(status_code=500, detail="PDF generation failed.")

    assessment = data.get("assessment")
    report = SecurityReport(
        assessment_id=assessment_id,
        report_name=REPORT_FILENAME,
        report_type="security_assessment",
        status="generated",
        risk_level=str(data["risk"]["level"]),
        summary=(
            f'{assessment["name"]}: {data["risk"]["total_findings"]} finding(s), '
            f'risk {data["risk"]["level"]} ({data["risk"]["score"]}/100)'
            if assessment
            else f'Platform-wide: {data["risk"]["total_findings"]} finding(s), '
            f'risk {data["risk"]["level"]} ({data["risk"]["score"]}/100)'
        ),
        file_path=str(pdf_path),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report, pdf_path


@router.get("/pdf")
def download_pdf(assessment_id: int | None = None, db: Session = Depends(get_db)):
    """Generate a fresh PDF from live data and stream it back."""
    report, pdf_path = _generate_and_record(db, assessment_id)
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=REPORT_FILENAME,
    )


@router.post("", status_code=201)
def generate_report(data: ReportGenerateRequest, db: Session = Depends(get_db)):
    report, pdf_path = _generate_and_record(db, data.assessment_id)
    payload = serialize_report(report)
    payload["file_path"] = str(pdf_path)
    return payload


@router.get("")
def list_reports(db: Session = Depends(get_db)):
    reports = db.query(SecurityReport).order_by(SecurityReport.id.desc()).all()
    return [serialize_report(r) for r in reports]


@router.get("/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)):
    report = db.get(SecurityReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return serialize_report(report)


@router.get("/{report_id}/download")
def download_report(report_id: int, db: Session = Depends(get_db)):
    report = db.get(SecurityReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if not report.file_path or not Path(report.file_path).is_file():
        raise HTTPException(status_code=404, detail="Report file no longer exists on disk.")
    return FileResponse(
        path=report.file_path,
        media_type="application/pdf",
        filename=REPORT_FILENAME,
    )


@router.delete("/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db)):
    report = db.get(SecurityReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    db.delete(report)
    db.commit()
    return {"message": "Report metadata deleted successfully", "id": report_id}
