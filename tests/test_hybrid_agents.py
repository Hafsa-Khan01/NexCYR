"""Hybrid Cloud + Agent architecture tests.

Covers enrollment (one-time token), agent authentication, heartbeat-derived
status, capability-gated job routing, the full job lifecycle
(queued -> claimed -> completed) with centrally-derived findings, the honest
"NO AVAILABLE NEXCYR AGENT" refusal, revocation, auditing, and agent-aware
attack map / reports / AI context.
"""

from conftest import (
    enroll_agent,
    make_assessment,
    make_target,
    register_agent,
)


def _auth(token):
    return {"X-NexCYR-Agent-Token": token}


# --------------------------------------------------------------------------
# Enrollment + credential security
# --------------------------------------------------------------------------
def test_enrollment_returns_one_time_token(client):
    a = enroll_agent(client, "Agent Alpha", "ALPHA-01")
    assert a["agent_key"] == "ALPHA-01"
    assert a["status"] == "enrolled"
    assert a["enrollment_token"]
    # The stored record never exposes the plaintext token again.
    listed = client.get("/api/agents").json()
    assert listed[0]["agent_key"] == "ALPHA-01"
    assert "enrollment_token" not in listed[0]
    got = client.get(f"/api/agents/{a['id']}").json()
    assert "enrollment_token" not in got


def test_duplicate_agent_key_rejected(client):
    enroll_agent(client, "A", "DUP-KEY")
    r = client.post("/api/agents", json={"name": "B", "agent_key": "DUP-KEY"})
    assert r.status_code == 400


def test_agent_auth_required_and_validated(client):
    # No credential -> 401
    assert client.post("/api/agents/register", json={}).status_code == 401
    # Bogus credential -> 401
    r = client.post("/api/agents/register", headers=_auth("not-a-real-token"), json={})
    assert r.status_code == 401


def test_register_sets_online_status(client):
    a = enroll_agent(client, "Agent Beta")
    reg = register_agent(client, a["enrollment_token"], version="2.1.0")
    assert reg["status"] == "online"
    assert reg["version"] == "2.1.0"
    assert reg["nmap_available"] is True

    health = client.get(f"/api/agents/{a['id']}/health").json()
    assert health["status"] == "online"
    caps = client.get(f"/api/agents/{a['id']}/capabilities").json()["capabilities"]
    assert caps["service_enumeration"] is True


def test_heartbeat_updates_last_seen(client):
    a = enroll_agent(client, "Agent Gamma")
    register_agent(client, a["enrollment_token"])
    r = client.post("/api/agents/heartbeat", headers=_auth(a["enrollment_token"]),
                    json={"cpu": 12.5, "memory": 40.0, "uptime": "3h"})
    assert r.status_code == 200
    assert r.json()["status"] == "online"
    health = client.get(f"/api/agents/{a['id']}/health").json()
    assert health["health"]["cpu"] == 12.5


# --------------------------------------------------------------------------
# Scan routing — honest refusal when no agent is available
# --------------------------------------------------------------------------
def test_scan_to_non_online_agent_refused_409(client):
    a = enroll_agent(client, "Offline Agent")  # never registers -> not online
    t = make_target(client, authorized=True)
    r = client.post("/api/scans", json={"target_id": t["id"], "agent_id": a["id"]})
    assert r.status_code == 409
    assert "NO AVAILABLE NEXCYR AGENT" in r.json()["detail"]


def test_scan_to_unknown_agent_404(client):
    t = make_target(client, authorized=True)
    r = client.post("/api/scans", json={"target_id": t["id"], "agent_id": 999999})
    assert r.status_code == 404


def test_scan_to_incapable_agent_refused_409(client):
    a = enroll_agent(client, "No Scanner Agent")
    # Online, but reports no scanning capabilities at all.
    register_agent(client, a["enrollment_token"], nmap=False, service_enum=False,
                   port_scan=False, host_discovery=False)
    t = make_target(client, authorized=True)
    r = client.post("/api/scans", json={"target_id": t["id"], "agent_id": a["id"],
                                        "scan_type": "service"})
    assert r.status_code == 409


# --------------------------------------------------------------------------
# Full agent job lifecycle -> centrally derived findings
# --------------------------------------------------------------------------
def test_agent_scan_full_lifecycle(client):
    a = make_assessment(client, "Hybrid Scope")
    t = make_target(client, authorized=True, assessment_id=a["id"])
    ag = enroll_agent(client, "Field Agent", "FIELD-01")
    register_agent(client, ag["enrollment_token"], version="1.2.3")

    # 1) Route an authorized scan to the online, capable agent -> QUEUED job.
    scan = client.post("/api/scans", json={
        "target_id": t["id"], "scan_type": "service",
        "assessment_id": a["id"], "agent_id": ag["id"],
    })
    assert scan.status_code == 201, scan.text
    sj = scan.json()
    assert sj["status"] == "queued"
    assert sj["execution_source"] == "AGENT"
    assert sj["agent_name"] == "Field Agent"
    job_id = sj["job"]["id"]
    assert sj["job"]["job_type"] == "NMAP_SERVICE_ENUMERATION"
    assert sj["job"]["status"] == "queued"

    # 2) Agent claims the next job.
    nxt = client.get("/api/agents/me/jobs/next", headers=_auth(ag["enrollment_token"]))
    assert nxt.status_code == 200
    claimed = nxt.json()["job"]
    assert claimed["id"] == job_id
    assert claimed["status"] == "running"
    assert claimed["target"] == t["value"]
    assert claimed["target_authorized"] is True

    # 3) Agent submits structured results (never trusted verbatim).
    res = client.post(f"/api/agents/jobs/{job_id}/result", headers=_auth(ag["enrollment_token"]),
                      json={"status": "COMPLETED", "results": {"services": [
                          {"port": 445, "state": "open", "service": "microsoft-ds", "version": "SMB"},
                          {"port": 22, "state": "open", "service": "ssh", "version": "OpenSSH 7.4"},
                          {"port": 999999, "state": "open", "service": "bogus"},  # invalid -> dropped
                      ]}})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "completed"

    # 4) Scan is now completed, sourced from the agent, with derived findings.
    got = client.get(f"/api/scans/{sj['id']}").json()
    assert got["status"] == "completed"
    assert got["execution_source"] == "AGENT"
    assert got["agent_name"] == "Field Agent"
    assert got["agent_version"] == "1.2.3"

    results = client.get(f"/api/scans/{sj['id']}/results").json()
    services = results["scan"]["result_data"]["services"]
    # The invalid port was filtered out by validation.
    assert all(0 < s["port"] <= 65535 for s in services)
    assert len(services) == 2
    findings = results["findings"]
    assert findings, "risk-worthy services should derive findings"
    assert all(f["source"] == "agent:FIELD-01" for f in findings)


def test_job_result_rejected_for_other_agent(client):
    t = make_target(client, authorized=True)
    ag1 = enroll_agent(client, "Agent One", "ONE")
    register_agent(client, ag1["enrollment_token"])
    ag2 = enroll_agent(client, "Agent Two", "TWO")
    register_agent(client, ag2["enrollment_token"])

    scan = client.post("/api/scans", json={"target_id": t["id"], "agent_id": ag1["id"],
                                           "scan_type": "service"}).json()
    job_id = scan["job"]["id"]
    # Agent Two cannot touch Agent One's job.
    r = client.post(f"/api/agents/jobs/{job_id}/result", headers=_auth(ag2["enrollment_token"]),
                    json={"status": "COMPLETED", "results": {"services": []}})
    assert r.status_code == 404


def test_operator_job_endpoints(client):
    t = make_target(client, authorized=True)
    ag = enroll_agent(client, "Operator Job Agent")
    register_agent(client, ag["enrollment_token"])

    # Operator queues a job directly.
    created = client.post("/api/agents/jobs", json={
        "target_id": t["id"], "agent_id": ag["id"], "job_type": "NMAP_PORT_SCAN",
    })
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    listing = client.get("/api/agents/jobs").json()
    assert any(j["id"] == job_id for j in listing)

    single = client.get(f"/api/agents/jobs/{job_id}")
    assert single.status_code == 200

    cancelled = client.post(f"/api/agents/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_operator_job_validation(client):
    t = make_target(client, authorized=True)
    # bad job type
    assert client.post("/api/agents/jobs", json={"target_id": t["id"], "job_type": "SHELL"}).status_code == 400
    # unauthorized target
    tu = make_target(client, authorized=False)
    assert client.post("/api/agents/jobs", json={"target_id": tu["id"], "job_type": "NMAP_PORT_SCAN"}).status_code == 400


# --------------------------------------------------------------------------
# Disable / revoke
# --------------------------------------------------------------------------
def test_disable_and_revoke(client):
    ag = enroll_agent(client, "Revoke Me", "REV-01")
    token = ag["enrollment_token"]
    register_agent(client, token)

    # Disable -> cannot authenticate.
    d = client.put(f"/api/agents/{ag['id']}", json={"enabled": False})
    assert d.status_code == 200 and d.json()["enabled"] is False
    assert client.post("/api/agents/heartbeat", headers=_auth(token), json={}).status_code == 401

    # Re-enable then revoke -> credential invalidated permanently.
    client.put(f"/api/agents/{ag['id']}", json={"enabled": True})
    rv = client.post(f"/api/agents/{ag['id']}/revoke")
    assert rv.status_code == 200 and rv.json()["status"] == "revoked"
    assert client.post("/api/agents/heartbeat", headers=_auth(token), json={}).status_code == 401


# --------------------------------------------------------------------------
# Audit trail
# --------------------------------------------------------------------------
def test_audit_trail_records_lifecycle(client):
    ag = enroll_agent(client, "Audited Agent", "AUD-01")
    register_agent(client, ag["enrollment_token"])
    client.post(f"/api/agents/{ag['id']}/revoke")

    actions = {e["action"] for e in client.get("/api/agents/audit").json()}
    assert "agent_enrolled" in actions
    assert "agent_registered" in actions
    assert "agent_revoked" in actions


# --------------------------------------------------------------------------
# Agent-aware attack map, reports and AI context
# --------------------------------------------------------------------------
def test_attack_map_includes_agent_source(client):
    a = make_assessment(client, "Map Scope")
    t = make_target(client, authorized=True, assessment_id=a["id"])
    ag = enroll_agent(client, "Map Agent", "MAP-01")
    register_agent(client, ag["enrollment_token"])
    scan = client.post("/api/scans", json={"target_id": t["id"], "agent_id": ag["id"],
                                           "scan_type": "service"}).json()
    client.post(f"/api/agents/jobs/{scan['job']['id']}/result",
                headers=_auth(ag["enrollment_token"]),
                json={"status": "COMPLETED", "results": {"services": [
                    {"port": 3389, "state": "open", "service": "ms-wbt-server"}]}})

    m = client.get("/api/attack-map").json()
    assert m["has_data"] is True
    types = {n["type"] for n in m["nodes"]}
    assert "agent" in types
    assert m["counts"]["agent"] >= 1
    assert any(e["relation"] == "executed" for e in m["edges"])


def test_ai_fallback_answers_agent_question(client):
    a = make_assessment(client, "AI Agent Scope")
    t = make_target(client, authorized=True, assessment_id=a["id"])
    ag = enroll_agent(client, "Context Agent", "CTX-01")
    register_agent(client, ag["enrollment_token"])
    scan = client.post("/api/scans", json={"target_id": t["id"], "agent_id": ag["id"],
                                           "scan_type": "service"}).json()
    r = client.post("/api/ai", json={"question": f"Which agent ran scan #{scan['id']}?"})
    assert r.status_code == 200, r.text
    ans = (r.json()["answer"] or "").lower()
    # The fallback engine answers from the DB and names the execution source.
    assert "context agent" in ans or "agent" in ans


def test_report_pdf_renders_with_agent_scan(client):
    a = make_assessment(client, "Report Agent Scope")
    t = make_target(client, authorized=True, assessment_id=a["id"])
    ag = enroll_agent(client, "Report Agent", "RPT-01")
    register_agent(client, ag["enrollment_token"], version="3.0.0")
    scan = client.post("/api/scans", json={"target_id": t["id"], "agent_id": ag["id"],
                                           "assessment_id": a["id"], "scan_type": "service"}).json()
    client.post(f"/api/agents/jobs/{scan['job']['id']}/result",
                headers=_auth(ag["enrollment_token"]),
                json={"status": "COMPLETED", "results": {"services": [
                    {"port": 445, "state": "open", "service": "microsoft-ds"}]}})

    pdf = client.get(f"/api/reports/pdf?assessment_id={a['id']}")
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"
    assert len(pdf.content) > 1000
