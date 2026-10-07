from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessment_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="general", index=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="created", index=True
    )
    risk_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown"
    )
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    targets: Mapped[list["Target"]] = relationship(  # noqa: F821
        back_populates="assessment",
        cascade="all, delete-orphan",
    )
    scans: Mapped[list["Scan"]] = relationship(  # noqa: F821
        back_populates="assessment",
        cascade="all, delete-orphan",
    )
    findings: Mapped[list["Finding"]] = relationship(  # noqa: F821
        back_populates="assessment",
        cascade="all, delete-orphan",
    )
    soc_events: Mapped[list["SOCEvent"]] = relationship(  # noqa: F821
        back_populates="assessment",
        cascade="all, delete-orphan",
    )
    purple_team_tests: Mapped[list["PurpleTeamTest"]] = relationship(  # noqa: F821
        back_populates="assessment",
        cascade="all, delete-orphan",
    )
