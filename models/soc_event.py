from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.assessment import utcnow


class SOCEvent(Base):
    __tablename__ = "soc_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="low", index=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="open", index=True
    )

    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessments.id"), nullable=True, index=True
    )
    target_id: Mapped[int | None] = mapped_column(
        ForeignKey("targets.id"), nullable=True, index=True
    )

    source_ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    destination_ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    assessment: Mapped["Assessment | None"] = relationship(  # noqa: F821
        back_populates="soc_events"
    )
    target: Mapped["Target | None"] = relationship()  # noqa: F821
