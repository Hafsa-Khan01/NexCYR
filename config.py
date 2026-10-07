"""Central NexCYR configuration.

All secrets come from environment variables. Nothing sensitive is hardcoded.
"""

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class Config:
    APP_NAME = "NexCYR"
    APP_VERSION = "1.0.0"
    APP_DESCRIPTION = (
        "AI-Powered Unified Cybersecurity Assessment "
        "& Purple Team Platform"
    )

    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "sqlite:///./nexcyr.db",
    )

    # --- AI provider (all optional; fallback engine runs without them) ---
    AI_PROVIDER = os.getenv("AI_PROVIDER", "").strip()
    AI_MODEL = os.getenv("AI_MODEL", "").strip()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_BASE_URL = os.getenv(
        "OPENAI_BASE_URL",
        "https://api.openai.com/v1",
    ).strip().rstrip("/")

    # --- Optional path to the nmap executable ---
    NMAP_PATH = os.getenv("NMAP_PATH", "").strip()

    REPORTS_DIR = Path(
        os.getenv("REPORTS_DIR", str(BASE_DIR / "reports"))
    )

    @classmethod
    def ai_enabled(cls) -> bool:
        return bool(
            cls.OPENAI_API_KEY
            and cls.AI_PROVIDER
            and cls.AI_MODEL
        )

    @classmethod
    def resolve_nmap(cls):
        """Locate the nmap binary without ever accepting user input."""
        if cls.NMAP_PATH and Path(cls.NMAP_PATH).is_file():
            return cls.NMAP_PATH

        found = shutil.which("nmap")
        if found:
            return found

        candidates = [
            BASE_DIR.parent / "nmap.exe",
            BASE_DIR.parent / "nmap" / "nmap.exe",
            Path(r"C:\Program Files (x86)\Nmap\nmap.exe"),
            Path(r"C:\Program Files\Nmap\nmap.exe"),
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return None
