"""NexCYR Agent — distributed authorized execution node.

An Agent is a lightweight service inside an authorized network that the
Cloud command center can assign structured scan jobs to. It is never a
remote shell: only predefined job types with structured parameters are
accepted, and every job is validated against target authorization.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.assessment import utcnow

# Lifecycle states for an Agent record.
AGENT_STATUS_ENROLLED = "enrolled"
AGENT_STATUS_ONLINE = "online"
AGENT_STATUS_OFFLINE = "offline"
AGENT_STATUS_DEGRADED = "degraded"
AGENT_STATUS_DISABLED = "disabled"
AGENT_STATUS_REVOKED = "revoked"

# Heartbeat freshness threshold (seconds) before an agent is not "online".
HEARTBEAT_ONLINE_SECONDS = 90
HEARTBEAT_DEGRADED_SECONDS = 300


def compute_agent_status(agent, now: datetime | None = None) -> str:
    """Derive ONLINE / OFFLINE / DEGRADED from real heartbeat recency.

    Never claims an agent is online without a recent heartbeat.
    """
    if agent.status == AGENT_STATUS_REVOKED:
        return AGENT_STATUS_REVOKED
    if not agent.enabled:
        return AGENT_STATUS_DISABLED
    if agent.last_seen is None:
        # Never checked in: keep the honest "enrolled" state (awaiting first
        # heartbeat) rather than implying it once was and went silent.
        return (
            AGENT_STATUS_ENROLLED
            if agent.status == AGENT_STATUS_ENROLLED
            else AGENT_STATUS_OFFLINE
        )
    now = now or utcnow()
    seen = agent.last_seen
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=now.tzinfo)
    age = (now - seen).total_seconds()
    if age <= HEARTBEAT_ONLINE_SECONDS:
        return AGENT_STATUS_ONLINE
    if age <= HEARTBEAT_DEGRADED_SECONDS:
        return AGENT_STATUS_DEGRADED
    return AGENT_STATUS_OFFLINE


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agent_key: Mapped[str] = mapped_column(
        String(60), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(120), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(40), nullable=True)
    os_info: Mapped[str | None] = mapped_column(String(120), nullable=True)
    arch: Mapped[str | None] = mapped_column(String(40), nullable=True)
    version: Mapped[str | None] = mapped_column(String(40), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AGENT_STATUS_ENROLLED, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Only a hash of the credential is stored; the plaintext token is
    # returned exactly once at enrollment and never persisted or logged.
    token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # JSON blobs: {"nmap": bool, "host_discovery": bool, ...}
    capabilities: Mapped[str | None] = mapped_column(Text, nullable=True)
    health: Mapped[str | None] = mapped_column(Text, nullable=True)

    assigned_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    registered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    jobs: Mapped[list["ScanJob"]] = relationship(  # noqa: F821
        back_populates="agent"
    )
