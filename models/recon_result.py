from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.assessment import utcnow

RECON_TYPES = {"host_discovery", "port_discovery", "service_enumeration"}


class ReconResult(Base):
    __tablename__ = "recon_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    target_id: Mapped[int | None] = mapped_column(
        ForeignKey("targets.id"), nullable=True, index=True
    )
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessments.id"), nullable=True, index=True
    )
    recon_type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="completed"
    )
    result_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Execution source tracking (hybrid architecture): CLOUD or AGENT.
    execution_source: Mapped[str] = mapped_column(
        String(10), nullable=False, default="CLOUD", server_default="CLOUD", index=True
    )
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
