from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.assessment import utcnow


class SecurityReport(Base):
    __tablename__ = "security_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessments.id"), nullable=True, index=True
    )
    report_name: Mapped[str] = mapped_column(String(255), nullable=False)
    report_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="security_assessment"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="generated"
    )
    risk_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown"
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
