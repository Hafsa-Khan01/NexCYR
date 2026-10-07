"""NexCYR Intelligence — contextual cybersecurity assistant.

When AI_PROVIDER / AI_MODEL / OPENAI_API_KEY are configured, questions are
answered by the external model with real platform context. Otherwise the
NexCYR Intelligence Fallback Engine answers directly from the database.
The platform is always fully functional without an external LLM.
"""

import json
import logging
import re

import requests
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import Config
from models.agent import Agent
from models.ai_analysis import AIAnalysis
from models.assessment import Assessment
from models.finding import Finding
from models.purple_team import PurpleTeamTest
from models.scan import Scan
from models.soc_event import SOCEvent
from models.target import Target
from models.wifi_assessment import WiFiAssessment
from services.agent_service import serialize_agent
from services.risk_engine import calculate_overall_risk

logger = logging.getLogger("nexcyr.intelligence")

SEVERITY_EXPLAIN = {
    "critical": (
        "Critical severity: an issue that can typically be exploited "
        "immediately and lead to full compromise of the affected system."
    ),
    "high": (
        "High severity: a serious weakness that is realistically exploitable "
        "and should be remediated as a priority."
    ),
    "medium": (
        "Medium severity: a weakness that increases risk, usually requiring "
        "specific conditions to exploit."
    ),
    "low": (
        "Low severity: a minor issue or hardening opportunity with limited "
        "direct exploitability."
    ),
    "info": (
        "Informational: an observation about the environment, not a "
        "vulnerability by itself."
    ),
    "informational": (
        "Informational: an observation about the environment, not a "
        "vulnerability by itself."
    ),
}


# ============================================================
# CONTEXT BUILDING (always from real stored data)
# ============================================================

def build_platform_context(db: Session) -> dict:
    assessments = db.query(Assessment).order_by(Assessment.id.desc()).limit(10).all()
    findings = db.query(Finding).order_by(Finding.id.desc()).limit(10).all()
    soc_events = db.query(SOCEvent).order_by(SOCEvent.id.desc()).limit(10).all()

    counts = {
        "assessments": db.query(func.count(Assessment.id)).scalar() or 0,
        "targets": db.query(func.count(Target.id)).scalar() or 0,
        "authorized_targets": (
            db.query(func.count(Target.id)).filter(Target.authorized.is_(True)).scalar() or 0
        ),
        "scans": db.query(func.count(Scan.id)).scalar() or 0,
        "findings": db.query(func.count(Finding.id)).scalar() or 0,
        "open_findings": (
            db.query(func.count(Finding.id)).filter(Finding.status == "open").scalar() or 0
        ),
        "soc_events": db.query(func.count(SOCEvent.id)).scalar() or 0,
        "purple_team_tests": db.query(func.count(PurpleTeamTest.id)).scalar() or 0,
        "wifi_assessments": db.query(func.count(WiFiAssessment.id)).scalar() or 0,
    }

    all_findings = db.query(Finding).all()
    risk = calculate_overall_risk(
        [
            {
                "severity": f.severity,
                "risk_score": f.risk_score,
                "status": f.status,
            }
            for f in all_findings
        ]
    )

    return {
        "counts": counts,
        "risk": risk,
        "recent_assessments": [
            {
                "id": a.id,
                "name": a.name,
                "type": a.assessment_type,
                "status": a.status,
                "risk_level": a.risk_level,
                "risk_score": a.risk_score,
            }
            for a in assessments
        ],
        "recent_findings": [
            {
                "id": f.id,
                "title": f.title,
                "severity": f.severity,
                "status": f.status,
                "risk_score": f.risk_score,
            }
            for f in findings
        ],
        "recent_soc_events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "severity": e.severity,
                "message": e.message,
                "status": e.status,
            }
            for e in soc_events
        ],
    }


def build_finding_context(db: Session, finding: Finding) -> dict:
    target = db.get(Target, finding.target_id) if finding.target_id else None
    scan = db.get(Scan, finding.scan_id) if finding.scan_id else None
    assessment = (
        db.get(Assessment, finding.assessment_id) if finding.assessment_id else None
    )
    return {
        "finding": {
            "id": finding.id,
            "title": finding.title,
            "severity": finding.severity,
            "status": finding.status,
            "description": finding.description,
            "evidence": finding.evidence,
            "remediation": finding.remediation,
            "risk_score": finding.risk_score,
            "risk_level": finding.risk_level,
            "recommendations": finding.recommendations,
        },
        "target": {"id": target.id, "value": target.value} if target else None,
        "scan": {"id": scan.id, "scan_type": scan.scan_type} if scan else None,
        "assessment": {"id": assessment.id, "name": assessment.name} if assessment else None,
    }


def build_assessment_context(db: Session, assessment: Assessment) -> dict:
    targets = db.query(Target).filter(Target.assessment_id == assessment.id).all()
    findings = db.query(Finding).filter(Finding.assessment_id == assessment.id).all()
    scans = db.query(Scan).filter(Scan.assessment_id == assessment.id).all()
    events = db.query(SOCEvent).filter(SOCEvent.assessment_id == assessment.id).all()
    return {
        "assessment": {
            "id": assessment.id,
            "name": assessment.name,
            "description": assessment.description,
            "type": assessment.assessment_type,
            "status": assessment.status,
            "risk_level": assessment.risk_level,
            "risk_score": assessment.risk_score,
        },
        "targets": [
            {"id": t.id, "value": t.value, "type": t.target_type, "authorized": t.authorized}
            for t in targets
        ],
        "scans": [{"id": s.id, "type": s.scan_type, "status": s.status} for s in scans],
        "findings": [
            {"id": f.id, "title": f.title, "severity": f.severity, "status": f.status}
            for f in findings
        ],
        "soc_events": [
            {"id": e.id, "type": e.event_type, "severity": e.severity, "message": e.message}
            for e in events
        ],
    }


# ============================================================
# FALLBACK ENGINE — answers from the real database
# ============================================================

def _fmt_list(items, render, empty_text):
    if not items:
        return empty_text
    return "\n".join(f"- {render(item)}" for item in items)


def fallback_answer(db: Session, question: str, context_type: str, context_id) -> dict:
    q = (question or "").strip().lower()
    sources = []

    # ---- Explicit context: a specific finding ----
    if context_type == "finding" and context_id:
        finding = db.get(Finding, int(context_id))
        if not finding:
            return _fallback_result(
                f"No finding with id {context_id} exists in the NexCYR database.",
                sources,
            )
        ctx = build_finding_context(db, finding)
        sources.append({"type": "finding", "id": finding.id, "label": finding.title})
        return _fallback_result(
            _explain_finding(finding, ctx),
            sources,
            risk_level=finding.risk_level or finding.severity,
        )

    # ---- Explicit context: a specific assessment ----
    if context_type == "assessment" and context_id:
        assessment = db.get(Assessment, int(context_id))
        if not assessment:
            return _fallback_result(
                f"No assessment with id {context_id} exists in the NexCYR database.",
                sources,
            )
        ctx = build_assessment_context(db, assessment)
        sources.append({"type": "assessment", "id": assessment.id, "label": assessment.name})
        return _fallback_result(
            _summarize_assessment(assessment, ctx),
            sources,
            risk_level=assessment.risk_level,
        )

    # ---- Explicit context: a specific scan ----
    if context_type == "scan" and context_id:
        scan = db.get(Scan, int(context_id))
        if not scan:
            return _fallback_result(
                f"No scan with id {context_id} exists in the NexCYR database.", sources
            )
        sources.append({"type": "scan", "id": scan.id, "label": f"Scan #{scan.id}"})
        return _fallback_result(_explain_scan(db, scan), sources)

    # ---- Intent detection on the question text ----
    if "highest risk" in q or "biggest risk" in q or "worst finding" in q:
        return _fallback_result(*_answer_highest_risk(db))

    if "summarize" in q and "assessment" in q:
        return _fallback_result(*_answer_summarize_assessment(db, q))

    if ("what should i do" in q) or ("next step" in q) or ("do next" in q):
        return _fallback_result(*_answer_next_steps(db))

    if "severity" in q and ("alert" in q or "event" in q):
        return _fallback_result(*_answer_alert_severity(db))

    if "fix" in q or "remediat" in q or "how do i" in q:
        return _fallback_result(*_answer_remediation(db))

    # ---- Agent / execution-source questions (hybrid architecture) ----
    if (
        "agent" in q
        or "kahan se" in q
        or "execution source" in q
        or ("where" in q and "run" in q)
        or ("which" in q and "scan" in q and ("run" in q or "execut" in q))
    ):
        return _fallback_result(*_answer_agent_question(db, q))

    if "explain" in q and "scan" in q:
        return _fallback_result(*_answer_explain_last_scan(db))

    if ("finding" in q) or ("vulnerab" in q):
        return _fallback_result(*_answer_explain_finding_generic(db, q))

    # ---- Default: platform status briefing ----
    ctx = build_platform_context(db)
    sources.append({"type": "platform", "id": None, "label": "Platform status"})
    return _fallback_result(_platform_briefing(ctx), sources)


def _fallback_result(answer: str, sources: list, risk_level: str = "unknown") -> tuple:
    return answer, {
        "engine": "nexcyr-fallback",
        "sources": sources,
        "risk_level": risk_level,
    }


def _explain_finding(finding: Finding, ctx: dict) -> str:
    target_text = (
        f"Target: {ctx['target']['value']} (id {ctx['target']['id']})"
        if ctx.get("target")
        else "Target: not linked to a stored target record"
    )
    return "\n\n".join(
        [
            f"WHAT IT MEANS\n{finding.description or finding.title}",
            (
                "WHY IT MATTERS\n"
                f"{SEVERITY_EXPLAIN.get((finding.severity or 'info').lower(), '')} "
                "Unremediated, it keeps the affected asset exposed and raises the "
                "overall risk score of the assessment."
            ).strip(),
            f"SEVERITY\n{finding.severity.upper()} (risk score {finding.risk_score}/100, level {finding.risk_level})",
            f"EVIDENCE\n{finding.evidence or 'No evidence recorded for this finding.'}",
            (
                "RECOMMENDED REMEDIATION\n"
                + (
                    finding.remediation
                    or finding.recommendations
                    or "No remediation recorded. Review the finding description and apply standard hardening for the affected service."
                )
            ),
            (
                "NEXT VALIDATION STEP\n"
                "Re-scan the linked target after remediation and confirm the finding "
                "no longer appears; then mark it resolved in NexCYR. "
                + target_text
            ),
        ]
    )


def _summarize_assessment(assessment: Assessment, ctx: dict) -> str:
    findings = ctx["findings"]
    sev_counts = {}
    for f in findings:
        sev_counts[f["severity"]] = sev_counts.get(f["severity"], 0) + 1
    sev_text = ", ".join(f"{count} {sev}" for sev, count in sorted(sev_counts.items())) or "none recorded"

    lines = [
        f"Assessment '{assessment.name}' (id {assessment.id})",
        f"Type: {assessment.assessment_type} | Status: {assessment.status}",
        f"Overall risk: {assessment.risk_level} (score {assessment.risk_score}/100)",
        f"Scope: {len(ctx['targets'])} target(s), {len(ctx['scans'])} scan(s)",
        f"Findings: {len(findings)} ({sev_text})",
        f"SOC events linked: {len(ctx['soc_events'])}",
    ]
    if assessment.description:
        lines.append(f"Description: {assessment.description}")
    top = sorted(
        (f for f in findings),
        key=lambda f: {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "informational": 4}.get(f["severity"], 5),
    )[:3]
    if top:
        lines.append("Top findings: " + "; ".join(f"{f['title']} [{f['severity']}]" for f in top))
    else:
        lines.append("No security findings recorded for this assessment yet.")
    return "\n".join(lines)


def _platform_briefing(ctx: dict) -> str:
    counts = ctx["counts"]
    risk = ctx["risk"]
    lines = [
        "NexCYR platform status (all values from the live database):",
        f"- Assessments: {counts['assessments']}",
        f"- Targets: {counts['targets']} ({counts['authorized_targets']} authorized)",
        f"- Scans: {counts['scans']}",
        f"- Findings: {counts['findings']} ({counts['open_findings']} open)",
        f"- SOC events: {counts['soc_events']}",
        f"- Purple team tests: {counts['purple_team_tests']}",
        f"- Wi-Fi assessments: {counts['wifi_assessments']}",
        f"- Overall risk: {risk.get('overall_risk', 'unknown')} (score {risk.get('overall_score', 0)})",
    ]
    if not counts["findings"] and not counts["soc_events"]:
        lines.append(
            "No recorded security findings or activity yet — the platform shows no risk data because none exists."
        )
    if ctx["recent_findings"]:
        lines.append(
            "Most recent findings: "
            + "; ".join(f"{f['title']} [{f['severity']}]" for f in ctx["recent_findings"][:3])
        )
    lines.append("Ask me about a specific assessment, finding, scan or alert for deeper context.")
    return "\n".join(lines)


def _answer_highest_risk(db: Session):
    finding = (
        db.query(Finding).order_by(Finding.risk_score.desc(), Finding.id.desc()).first()
    )
    if not finding:
        return (
            "No findings are recorded in the database, so there is no measured risk yet. "
            "Run an authorized scan or add findings to populate risk data.",
            {"engine": "nexcyr-fallback", "sources": [], "risk_level": "unknown"},
        )
    ctx = build_finding_context(db, finding)
    sources = [{"type": "finding", "id": finding.id, "label": finding.title}]
    return (
        f"Your highest recorded risk is finding #{finding.id} '{finding.title}' "
        f"(severity {finding.severity}, risk score {finding.risk_score}/100).\n\n"
        + _explain_finding(finding, ctx),
        {"engine": "nexcyr-fallback", "sources": sources, "risk_level": finding.risk_level},
    )


def _answer_summarize_assessment(db: Session, q: str):
    assessment = None
    for token in q.replace("?", " ").split():
        if token.isdigit():
            assessment = db.get(Assessment, int(token))
            if assessment:
                break
    if not assessment:
        assessment = db.query(Assessment).order_by(Assessment.id.desc()).first()
    if not assessment:
        return (
            "No assessments exist in the database yet. Create one to get a summary.",
            {"engine": "nexcyr-fallback", "sources": [], "risk_level": "unknown"},
        )
    ctx = build_assessment_context(db, assessment)
    return (
        _summarize_assessment(assessment, ctx),
        {
            "engine": "nexcyr-fallback",
            "sources": [{"type": "assessment", "id": assessment.id, "label": assessment.name}],
            "risk_level": assessment.risk_level,
        },
    )


def _answer_next_steps(db: Session):
    open_critical = (
        db.query(Finding)
        .filter(Finding.status == "open", Finding.severity.in_(["critical", "high"]))
        .order_by(Finding.risk_score.desc())
        .first()
    )
    unauthorized = (
        db.query(Target).filter(Target.authorized.is_(False)).count()
    )
    pending_tests = (
        db.query(PurpleTeamTest)
        .filter(PurpleTeamTest.detection_status.in_(["pending", "missed"]))
        .count()
    )
    steps = []
    if open_critical:
        steps.append(
            f"1. Remediate finding #{open_critical.id} '{open_critical.title}' "
            f"({open_critical.severity}, score {open_critical.risk_score})."
        )
    if unauthorized:
        steps.append(
            f"{len(steps) + 1}. Obtain and record authorization for {unauthorized} "
            "target(s) before any scanning."
        )
    if pending_tests:
        steps.append(
            f"{len(steps) + 1}. Complete detection validation for {pending_tests} "
            "purple team test(s)."
        )
    steps.append(f"{len(steps) + 1}. Re-run authorized scans and generate an updated PDF report.")
    if not (open_critical or unauthorized or pending_tests):
        steps.insert(
            0,
            "No open critical findings, unauthorized targets or pending tests — "
            "the recorded posture is quiet.",
        )
    return (
        "Recommended next actions based on live NexCYR data:\n" + "\n".join(steps),
        {"engine": "nexcyr-fallback", "sources": [], "risk_level": "unknown"},
    )


def _answer_alert_severity(db: Session):
    event = db.query(SOCEvent).order_by(SOCEvent.id.desc()).first()
    if not event:
        return (
            "No SOC events are recorded, so there is no alert severity to report.",
            {"engine": "nexcyr-fallback", "sources": [], "risk_level": "unknown"},
        )
    return (
        f"The most recent alert is SOC event #{event.id} ({event.event_type}) "
        f"with severity {event.severity.upper()} and status '{event.status}'.\n"
        f"Message: {event.message}\n"
        f"{SEVERITY_EXPLAIN.get(event.severity.lower(), '')}",
        {
            "engine": "nexcyr-fallback",
            "sources": [{"type": "soc_event", "id": event.id, "label": event.event_type}],
            "risk_level": event.severity,
        },
    )


def _answer_remediation(db: Session):
    finding = (
        db.query(Finding)
        .filter(Finding.status == "open")
        .order_by(Finding.risk_score.desc())
        .first()
    )
    if not finding:
        return (
            "No open findings are recorded, so there is nothing to remediate right now.",
            {"engine": "nexcyr-fallback", "sources": [], "risk_level": "unknown"},
        )
    ctx = build_finding_context(db, finding)
    return (
        f"The highest-priority open finding is #{finding.id} '{finding.title}'.\n\n"
        + _explain_finding(finding, ctx),
        {
            "engine": "nexcyr-fallback",
            "sources": [{"type": "finding", "id": finding.id, "label": finding.title}],
            "risk_level": finding.risk_level,
        },
    )


def _answer_explain_last_scan(db: Session):
    scan = db.query(Scan).order_by(Scan.id.desc()).first()
    if not scan:
        return (
            "No scans are recorded in the database yet.",
            {"engine": "nexcyr-fallback", "sources": [], "risk_level": "unknown"},
        )
    return (
        _explain_scan(db, scan),
        {
            "engine": "nexcyr-fallback",
            "sources": [{"type": "scan", "id": scan.id, "label": f"Scan #{scan.id}"}],
            "risk_level": "unknown",
        },
    )


def _answer_agent_question(db: Session, q: str):
    """Answer agent / execution-source questions from real stored data."""
    agents = db.query(Agent).order_by(Agent.id.asc()).all()
    sources = [{"type": "agent", "id": a.id, "label": a.name} for a in agents]

    m = re.search(r"agent[\s#-]*(\d+)", q)
    target_agent = db.get(Agent, int(m.group(1))) if m else None

    if "nmap" in q and ("available" in q or "ready" in q):
        a = target_agent or (agents[0] if agents else None)
        if not a:
            return (
                "No NexCYR Agents are registered yet, so agent Nmap availability "
                "cannot be reported.",
                sources,
            )
        s = serialize_agent(a)
        return (
            f"Nmap on {a.name}: {'AVAILABLE' if s['nmap_available'] else 'UNAVAILABLE'}. "
            f"Agent status: {s['status'].upper()}.",
            sources,
        )

    if target_agent and ("online" in q or "status" in q or "is agent" in q):
        s = serialize_agent(target_agent)
        extra = (
            f" (last seen {s['last_seen_seconds_ago']}s ago)"
            if s["last_seen_seconds_ago"] is not None
            else " (no heartbeat recorded yet)"
        )
        return f"{target_agent.name} is {s['status'].upper()}{extra}.", sources

    scan = None
    m2 = re.search(r"scan[\s#-]*(\d+)", q)
    if m2:
        scan = db.get(Scan, int(m2.group(1)))
    if scan is None:
        scan = db.query(Scan).order_by(Scan.id.desc()).first()
    if scan is not None and any(w in q for w in ("run", "execut", "kahan", "where", "which")):
        src = (scan.execution_source or "CLOUD").upper()
        if src == "AGENT" and scan.agent_id:
            a = db.get(Agent, scan.agent_id)
            return (
                f"Scan #{scan.id} was executed by NexCYR Agent "
                f"{a.name if a else scan.agent_id}.",
                sources,
            )
        return f"Scan #{scan.id} was executed by the NexCYR Cloud Scanner.", sources

    if not agents:
        return (
            "No NexCYR Agents are registered. Scans currently run via the "
            "Cloud Scanner only.",
            sources,
        )
    lines = ["NexCYR Agent roster:"]
    for a in agents:
        s = serialize_agent(a)
        seen = (
            f"last seen {s['last_seen_seconds_ago']}s ago"
            if s["last_seen_seconds_ago"] is not None
            else "no heartbeat yet"
        )
        lines.append(
            f"- {a.name} [{a.agent_key}]: {s['status'].upper()}, "
            f"Nmap {'READY' if s['nmap_available'] else 'UNAVAILABLE'}, {seen}"
        )
    return "\n".join(lines), sources


def _explain_scan(db: Session, scan: Scan) -> str:
    target = db.get(Target, scan.target_id) if scan.target_id else None
    findings = db.query(Finding).filter(Finding.scan_id == scan.id).all()
    lines = [
        f"Scan #{scan.id} ({scan.scan_type}) — status: {scan.status}",
        f"Target: {target.value if target else 'unknown'}"
        + (" (authorized)" if target and target.authorized else ""),
    ]
    src = (scan.execution_source or "CLOUD").upper()
    if src == "AGENT" and scan.agent_id:
        agent = db.get(Agent, scan.agent_id)
        a_status = serialize_agent(agent)["status"] if agent else "unknown"
        lines.append(
            f"Executed by: NexCYR Agent {agent.name if agent else scan.agent_id} "
            f"(version {scan.agent_version or 'unknown'}, status {a_status})"
        )
    else:
        lines.append("Executed by: NexCYR Cloud Scanner")
    if scan.result_summary:
        lines.append(f"Summary: {scan.result_summary}")
    if scan.error:
        lines.append(f"Note: {scan.error}")
    if findings:
        lines.append(
            "Findings produced: "
            + "; ".join(f"{f.title} [{f.severity}]" for f in findings)
        )
    else:
        lines.append("This scan produced no findings.")
    return "\n".join(lines)


def _answer_explain_finding_generic(db: Session, q: str):
    finding = None
    for token in q.replace("?", " ").replace("#", " ").split():
        if token.isdigit():
            finding = db.get(Finding, int(token))
            if finding:
                break
    if not finding:
        match = None
        for word in q.split():
            if len(word) > 4:
                match = (
                    db.query(Finding)
                    .filter(Finding.title.ilike(f"%{word}%"))
                    .order_by(Finding.risk_score.desc())
                    .first()
                )
                if match:
                    break
        finding = match or (
            db.query(Finding).order_by(Finding.risk_score.desc(), Finding.id.desc()).first()
        )
    if not finding:
        return (
            "No findings exist in the database yet, so there is nothing to explain. "
            "Run an authorized scan or record a finding first.",
            {"engine": "nexcyr-fallback", "sources": [], "risk_level": "unknown"},
        )
    ctx = build_finding_context(db, finding)
    return (
        _explain_finding(finding, ctx),
        {
            "engine": "nexcyr-fallback",
            "sources": [{"type": "finding", "id": finding.id, "label": finding.title}],
            "risk_level": finding.risk_level,
        },
    )


# ============================================================
# EXTERNAL PROVIDER (OpenAI-compatible), optional
# ============================================================

def _call_external_model(question: str, context: dict) -> str:
    response = requests.post(
        f"{Config.OPENAI_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": Config.AI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are NexCYR Intelligence, a contextual cybersecurity "
                        "assistant embedded in the NexCYR platform. Answer strictly "
                        "from the supplied platform context. Never invent evidence, "
                        "findings or attacks that are not in the context."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Platform context (JSON):\n{json.dumps(context, default=str)}\n\n"
                        f"Question: {question}"
                    ),
                },
            ],
            "timeout": 60,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def answer_question(
    db: Session,
    question: str,
    context_type: str | None = None,
    context_id: int | None = None,
) -> dict:
    question = (question or "").strip()
    if not question:
        raise ValueError("Question cannot be empty.")

    if context_type == "finding" and context_id:
        context = build_finding_context(db, db.get(Finding, context_id) or Finding())
    elif context_type == "assessment" and context_id:
        assessment = db.get(Assessment, context_id)
        context = build_assessment_context(db, assessment) if assessment else {}
    else:
        context = build_platform_context(db)

    engine_used = "nexcyr-fallback"
    answer_text = None
    risk_level = "unknown"
    sources = []

    if Config.ai_enabled():
        try:
            answer_text = _call_external_model(question, context)
            engine_used = f"external:{Config.AI_PROVIDER}"
        except Exception:
            logger.exception("External AI provider failed; using fallback engine")
            answer_text = None

    if answer_text is None:
        answer_text, meta = fallback_answer(db, question, context_type, context_id)
        engine_used = meta["engine"]
        risk_level = meta.get("risk_level", "unknown")
        sources = meta.get("sources", [])

    analysis = AIAnalysis(
        question=question,
        analysis_type="chat",
        source_type=context_type or "platform",
        source_id=context_id,
        risk_level=risk_level,
        summary=answer_text[:2000],
        provider=engine_used,
        status="completed",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return {
        "answer": answer_text,
        "engine": engine_used,
        "risk_level": risk_level,
        "sources": sources,
        "analysis_id": analysis.id,
    }
