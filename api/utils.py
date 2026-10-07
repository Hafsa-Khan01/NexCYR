"""Shared API helpers: serialization and validation."""

from datetime import datetime

VALID_SEVERITIES = {"critical", "high", "medium", "low", "info", "informational"}
VALID_TARGET_TYPES = {"ip", "domain", "url", "host", "network"}


def to_iso(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def normalize_severity(value: str | None, default: str = "info") -> str:
    value = (value or default).strip().lower()
    if value == "informational":
        return "info"
    if value not in VALID_SEVERITIES:
        return default
    return value


def split_list_text(value):
    if not value:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]
