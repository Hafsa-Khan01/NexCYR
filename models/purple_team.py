from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.assessment import utcnow


class PurpleTeamTest(Base):
    __tablename__ = "purple_team_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    technique: Mapped[str | None] = mapped_column(String(255), nullable=True)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="planned", index=True
    )
    detection_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)

    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessments.id"), nullable=True, index=True
    )
    target_id: Mapped[int | None] = mapped_column(
        ForeignKey("targets.id"), nullable=True, index=True
    )
    finding_id: Mapped[int | None] = mapped_column(
        ForeignKey("findings.id"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    assessment: Mapped["Assessment | None"] = relationship(  # noqa: F821
        back_populates="purple_team_tests"
    )
    target: Mapped["Target | None"] = relationship()  # noqa: F821
    finding: Mapped["Finding | None"] = relationship()  # noqa: F821
