"""Cyber Attack Map — NexCYR's original relationship graph.

Built exclusively from stored relationships:
Target -> Scan -> Finding -> SOC Event -> Purple Team Test.
No nodes or attacks are fabricated; an empty graph means no linked activity.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models.agent import Agent
from models.finding import Finding
from models.purple_team import PurpleTeamTest
from models.scan import Scan
from models.soc_event import SOCEvent
from models.target import Target
from services.agent_service import serialize_agent

router = APIRouter(prefix="/api/attack-map", tags=["Cyber Attack Map"])


@router.get("")
def attack_map(assessment_id: int | None = None, db: Session = Depends(get_db)):
    targets_q = db.query(Target)
    scans_q = db.query(Scan)
    findings_q = db.query(Finding)
    events_q = db.query(SOCEvent)
    tests_q = db.query(PurpleTeamTest)

    if assessment_id is not None:
        targets_q = targets_q.filter(Target.assessment_id == assessment_id)
        scans_q = scans_q.filter(Scan.assessment_id == assessment_id)
        findings_q = findings_q.filter(Finding.assessment_id == assessment_id)
        events_q = events_q.filter(SOCEvent.assessment_id == assessment_id)
        tests_q = tests_q.filter(PurpleTeamTest.assessment_id == assessment_id)

    targets = targets_q.all()
    scans = scans_q.all()
    findings = findings_q.all()
    events = events_q.all()
    tests = tests_q.all()

    nodes = []
    edges = []

    for t in targets:
        nodes.append(
            {
                "id": f"target:{t.id}",
                "type": "target",
                "label": t.name or t.value,
                "entity_id": t.id,
                "severity": None,
                "status": t.status,
                "meta": {
                    "value": t.value,
                    "target_type": t.target_type,
                    "authorized": bool(t.authorized),
                },
            }
        )

    agent_ids = {s.agent_id for s in scans if s.agent_id}
    agents = db.query(Agent).filter(Agent.id.in_(agent_ids)).all() if agent_ids else []
    agent_by_id = {a.id: a for a in agents}
    source_nodes_added = set()

    for s in scans:
        nodes.append(
            {
                "id": f"scan:{s.id}",
                "type": "scan",
                "label": f"Scan #{s.id} ({s.scan_type})",
                "entity_id": s.id,
                "severity": None,
                "status": s.status,
                "meta": {"summary": s.result_summary or ""},
            }
        )
        if s.target_id:
            edges.append(
                {"source": f"target:{s.target_id}", "target": f"scan:{s.id}", "relation": "scanned"}
            )

        # Execution-source node: the Agent or Cloud Scanner that ran it.
        src_id = f"agent:{s.agent_id}" if s.agent_id else "cloud:scanner"
        if src_id not in source_nodes_added:
            source_nodes_added.add(src_id)
            if s.agent_id and s.agent_id in agent_by_id:
                a = agent_by_id[s.agent_id]
                nodes.append(
                    {
                        "id": src_id,
                        "type": "agent",
                        "label": a.name,
                        "entity_id": a.id,
                        "severity": None,
                        "status": serialize_agent(a)["status"],
                        "meta": {"agent_key": a.agent_key, "version": a.version},
                    }
                )
            elif not s.agent_id:
                nodes.append(
                    {
                        "id": src_id,
                        "type": "cloud",
                        "label": "Cloud Scanner",
                        "entity_id": None,
                        "severity": None,
                        "status": "available",
                        "meta": {},
                    }
                )
        if src_id in {n["id"] for n in nodes}:
            edges.append(
                {"source": src_id, "target": f"scan:{s.id}", "relation": "executed"}
            )

    for f in findings:
        nodes.append(
            {
                "id": f"finding:{f.id}",
                "type": "finding",
                "label": f.title,
                "entity_id": f.id,
                "severity": f.severity,
                "status": f.status,
                "meta": {"risk_score": f.risk_score, "risk_level": f.risk_level},
            }
        )
        if f.scan_id:
            edges.append(
                {"source": f"scan:{f.scan_id}", "target": f"finding:{f.id}", "relation": "produced"}
            )
        elif f.target_id:
            edges.append(
                {"source": f"target:{f.target_id}", "target": f"finding:{f.id}", "relation": "affects"}
            )

    for e in events:
        nodes.append(
            {
                "id": f"soc:{e.id}",
                "type": "soc_event",
                "label": f"{e.event_type} alert",
                "entity_id": e.id,
                "severity": e.severity,
                "status": e.status,
                "meta": {"message": e.message, "source": e.source},
            }
        )
        if e.target_id:
            linked_finding = next(
                (f for f in findings if f.target_id == e.target_id), None
            )
            if linked_finding:
                edges.append(
                    {"source": f"finding:{linked_finding.id}", "target": f"soc:{e.id}", "relation": "alerted"}
                )
            else:
                edges.append(
                    {"source": f"target:{e.target_id}", "target": f"soc:{e.id}", "relation": "observed_on"}
                )

    for t in tests:
        nodes.append(
            {
                "id": f"purple:{t.id}",
                "type": "purple_team",
                "label": t.name,
                "entity_id": t.id,
                "severity": None,
                "status": t.detection_status,
                "meta": {"technique": t.technique or "", "test_status": t.status},
            }
        )
        if t.finding_id:
            edges.append(
                {"source": f"finding:{t.finding_id}", "target": f"purple:{t.id}", "relation": "validates"}
            )
        elif t.target_id:
            linked_event = next(
                (e for e in events if e.target_id == t.target_id), None
            )
            if linked_event:
                edges.append(
                    {"source": f"soc:{linked_event.id}", "target": f"purple:{t.id}", "relation": "validated_by"}
                )
            else:
                edges.append(
                    {"source": f"target:{t.target_id}", "target": f"purple:{t.id}", "relation": "tested"}
                )

    node_ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

    counts = {
        "target": sum(1 for n in nodes if n["type"] == "target"),
        "scan": sum(1 for n in nodes if n["type"] == "scan"),
        "finding": sum(1 for n in nodes if n["type"] == "finding"),
        "soc_event": sum(1 for n in nodes if n["type"] == "soc_event"),
        "purple_team": sum(1 for n in nodes if n["type"] == "purple_team"),
        "agent": sum(1 for n in nodes if n["type"] == "agent"),
        "cloud": sum(1 for n in nodes if n["type"] == "cloud"),
    }

    return {
        "nodes": nodes,
        "edges": edges,
        "counts": counts,
        "has_data": bool(nodes),
        "empty_message": None if nodes else "NO LINKED SECURITY ACTIVITY",
    }
