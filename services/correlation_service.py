"""Event correlation over actually stored SOC events.

Groups related events by category and source/target proximity. Correlation
output is derived exclusively from stored records — no activity is invented.
"""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from models.soc_event import SOCEvent


def to_iso(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value

CATEGORY_KEYWORDS = {
    "authentication": {"authentication", "auth", "login", "brute", "credential", "password", "failed attempt"},
    "network_scanning": {"scan", "port sweep", "reconnaissance", "nmap", "discovery", "sweep"},
    "privilege_escalation": {"privilege", "escalation", "sudo", "admin access", "elevation", "root"},
    "malware": {"malware", "ransomware", "trojan", "virus", "c2", "beacon", "payload", "implant"},
    "data_exfiltration": {"exfil", "data transfer", "large upload", "leak"},
    "policy_violation": {"policy", "compliance", "unauthorized change", "configuration drift"},
}

SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def categorize_event(event: SOCEvent) -> str:
    text = " ".join(
        str(part or "").lower()
        for part in (event.event_type, event.message, event.source, event.detected_by)
    )
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "other"


def correlate_events(db: Session, window_hours: int = 24) -> dict:
    events = db.query(SOCEvent).order_by(SOCEvent.created_at.asc()).all()
    if not events:
        return {
            "total_events": 0,
            "clusters": [],
            "by_category": {},
            "note": "No SOC events recorded; there is nothing to correlate.",
        }

    by_category = defaultdict(list)
    for event in events:
        by_category[categorize_event(event)].append(event)

    clusters = []
    for category, grouped in sorted(by_category.items()):
        # Split each category into time-window clusters.
        current = []
        for event in grouped:
            if (
                current
                and event.created_at
                and current[-1].created_at
                and event.created_at - current[-1].created_at > timedelta(hours=window_hours)
            ):
                clusters.append(_build_cluster(category, current))
                current = []
            current.append(event)
        if current:
            clusters.append(_build_cluster(category, current))

    clusters.sort(key=lambda c: (-c["max_severity_weight"], -c["event_count"]))

    return {
        "total_events": len(events),
        "window_hours": window_hours,
        "clusters": clusters,
        "by_category": {cat: len(items) for cat, items in by_category.items()},
    }


def _build_cluster(category: str, events: list) -> dict:
    severities = [e.severity for e in events]
    max_severity = max(severities, key=lambda s: SEVERITY_WEIGHT.get(s, 0))
    sources = sorted({e.source_ip for e in events if e.source_ip})
    targets = sorted({e.destination_ip for e in events if e.destination_ip})
    statuses = defaultdict(int)
    for e in events:
        statuses[e.status] += 1

    assessment = (
        f"Correlated {len(events)} {category.replace('_', ' ')} event(s). "
        f"Highest severity: {max_severity}."
    )
    if len(events) >= 3 and SEVERITY_WEIGHT.get(max_severity, 0) >= 2:
        assessment += (
            " Repeated related activity of this volume warrants investigation "
            "and detection validation via a purple team test."
        )

    return {
        "category": category,
        "event_count": len(events),
        "event_ids": [e.id for e in events],
        "max_severity": max_severity,
        "max_severity_weight": SEVERITY_WEIGHT.get(max_severity, 0),
        "open_count": statuses.get("open", 0),
        "sources": sources[:10],
        "targets": targets[:10],
        "first_seen": to_iso(events[0].created_at),
        "last_seen": to_iso(events[-1].created_at),
        "assessment": assessment,
    }
