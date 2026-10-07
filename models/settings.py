from sqlalchemy import Column, Integer, String, Boolean, Float

from database import Base


class NexCYRSettings(Base):
    __tablename__ = "nexcyr_settings"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    # =========================
    # PLATFORM SETTINGS
    # =========================

    platform_name = Column(
        String,
        nullable=False,
        default="NexCYR",
    )

    environment = Column(
        String,
        nullable=False,
        default="local",
    )

    # =========================
    # AI ENGINE SETTINGS
    # =========================

    ai_enabled = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    ai_provider = Column(
        String,
        nullable=False,
        default="not_configured",
    )

    ai_model = Column(
        String,
        nullable=False,
        default="not_configured",
    )

    # =========================
    # AI ANALYSIS SETTINGS
    # =========================

    automatic_analysis = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    soc_event_analysis = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    finding_analysis = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    purple_team_analysis = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    # =========================
    # AI VOICE SETTINGS
    # =========================

    voice_enabled = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    speak_critical_alerts = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    speak_high_alerts = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    speak_medium_alerts = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    voice_language = Column(
        String,
        nullable=False,
        default="en-US",
    )

    voice_name = Column(
        String,
        nullable=False,
        default="default",
    )

    voice_rate = Column(
        Float,
        nullable=False,
        default=1.0,
    )

    voice_volume = Column(
        Float,
        nullable=False,
        default=0.8,
    )