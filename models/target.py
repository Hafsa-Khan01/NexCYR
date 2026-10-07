from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.assessment import utcnow

TARGET_TYPES = {"ip", "domain", "url", "host", "network"}


class Target(Base):
    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessments.id"), nullable=True, index=True
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="active", index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Preferred execution node for this target: NULL/0 = Cloud Scanner,
    # otherwise the id of the authorized NexCYR Agent inside its network.
    preferred_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    assessment: Mapped["Assessment | None"] = relationship(  # noqa: F821
        back_populates="targets"
    )
    scans: Mapped[list["Scan"]] = relationship(  # noqa: F821
        back_populates="target",
        cascade="all, delete-orphan",
    )
    findings: Mapped[list["Finding"]] = relationship(  # noqa: F821
        back_populates="target"
    )
