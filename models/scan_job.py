"""ScanJob — a structured, authorized unit of agent/cloud execution.

Jobs carry structured parameters only (never shell commands). The Agent
validates job type, target, authorization and local policy before running
a supported safe operation, then returns structured results.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.assessment import utcnow

# Allowed job types. The agent accepts ONLY these.
JOB_NMAP_HOST_DISCOVERY = "NMAP_HOST_DISCOVERY"
JOB_NMAP_PORT_SCAN = "NMAP_PORT_SCAN"
JOB_NMAP_SERVICE_ENUMERATION = "NMAP_SERVICE_ENUMERATION"
JOB_AUTHORIZED_RECON = "AUTHORIZED_RECON"

VALID_JOB_TYPES = {
    JOB_NMAP_HOST_DISCOVERY,
    JOB_NMAP_PORT_SCAN,
    JOB_NMAP_SERVICE_ENUMERATION,
    JOB_AUTHORIZED_RECON,
}

# Safe predefined scan profiles (allowlisted argument sets).
VALID_PORT_PROFILES = {"safe_default", "common", "top100"}

JOB_STATUS_PENDING = "pending"
JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_CANCELLED = "cancelled"

VALID_JOB_STATUSES = {
    JOB_STATUS_PENDING,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_CANCELLED,
}

EXECUTION_CLOUD = "CLOUD"
EXECUTION_AGENT = "AGENT"


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    # Structured parameters, e.g. {"target": "...", "ports_profile": "safe_default"}
    params: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=JOB_STATUS_PENDING, index=True
    )
    execution_source: Mapped[str] = mapped_column(
        String(10), nullable=False, default=EXECUTION_AGENT, index=True
    )

    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id"), nullable=True, index=True
    )
    scan_id: Mapped[int | None] = mapped_column(
        ForeignKey("scans.id"), nullable=True, index=True
    )
    target_id: Mapped[int] = mapped_column(
        ForeignKey("targets.id"), nullable=False, index=True
    )
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessments.id"), nullable=True, index=True
    )

    # Structured result returned by the executing node.
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    agent: Mapped["Agent | None"] = relationship(  # noqa: F821
        back_populates="jobs"
    )
