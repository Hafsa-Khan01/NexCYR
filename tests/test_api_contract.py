"""End-to-end API contract tests — every route in the NexCYR brief.

All assertions run against an isolated test DB (see conftest.py) and the
fallback intelligence engine (no external LLM).
"""

from conftest import make_assessment, make_target


# --------------------------------------------------------------------------
# System + pages
# --------------------------------------------------------------------------
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["service"] == "NexCYR API"


def test_pages_served(client):
    for path in ("/", "/boot", "/dashboard", "/docs"):
        r = client.get(path)
        assert r.status_code == 200, path


def test_dashboard_summary_shape(client):
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200
    d = r.json()
    for key in ("counts", "risk", "purple_team", "agents", "recent_findings",
                "recent_soc_events", "correlation"):
        assert key in d
    assert d["risk"]["has_data"] is False
    # No findings => the empty-state message is surfaced, never fabricated risk.
    assert d["counts"]["agents"] == 0


# --------------------------------------------------------------------------
# Assessments CRUD
# --------------------------------------------------------------------------
def test_assessment_crud(client):
    a = make_assessment(client, "Q3 Perimeter")
    aid = a["id"]
    assert client.get(f"/api/assessments/{aid}").status_code == 200

    r = client.put(f"/api/assessments/{aid}", json={"status": "running"})
    assert r.status_code == 200 and r.json()["status"] == "running"

    listing = client.get("/api/assessments").json()
    assert any(x["id"] == aid for x in listing)

    assert client.delete(f"/api/assessments/{aid}").status_code == 200
    assert client.get(f"/api/assessments/{aid}").status_code == 404


def test_assessment_requires_name(client):
    assert client.post("/api/assessments", json={}).status_code == 422


# --------------------------------------------------------------------------
# Targets CRUD + validation
# --------------------------------------------------------------------------
def test_target_crud(client):
    t = make_target(client, name="web-01")
    tid = t["id"]
    assert t["authorized"] is True
    assert client.get(f"/api/targets/{tid}").status_code == 200

    r = client.put(f"/api/targets/{tid}", json={"authorized": False})
    assert r.status_code == 200 and r.json()["authorized"] is False

    assert client.delete(f"/api/targets/{tid}").status_code == 200


def test_target_invalid_value_rejected(client):
    r = client.post("/api/targets", json={"target_type": "ip", "value": "not-an-ip"})
    assert r.status_code == 400


def test_target_invalid_type_rejected(client):
    r = client.post("/api/targets", json={"target_type": "bogus", "value": "127.0.0.1"})
    assert r.status_code == 400


# --------------------------------------------------------------------------
# Findings CRUD + risk engine
# --------------------------------------------------------------------------
def test_finding_crud_and_risk(client):
    a = make_assessment(client)
    f = client.post("/api/findings", json={
        "title": "Exposed SMB service", "severity": "high",
        "assessment_id": a["id"], "description": "445/tcp open",
    })
    assert f.status_code == 201, f.text
    fid = f.json()["id"]
    # Risk engine scores the finding on creation.
    assert f.json()["risk_score"] is not None

    r = client.put(f"/api/findings/{fid}", json={"status": "resolved"})
    assert r.status_code == 200 and r.json()["status"] == "resolved"

    # Dashboard now reports real risk data.
    d = client.get("/api/dashboard/summary").json()
    assert d["risk"]["has_data"] is True
    assert d["counts"]["high_findings"] >= 1

    assert client.delete(f"/api/findings/{fid}").status_code == 200


def test_finding_requires_title(client):
    assert client.post("/api/findings", json={"severity": "high"}).status_code == 422


# --------------------------------------------------------------------------
# Scans — authorization gating (no scan is run against unauthorized targets)
# --------------------------------------------------------------------------
def test_scan_requires_authorized_target(client):
    t = make_target(client, authorized=False)
    r = client.post("/api/scans", json={"target_id": t["id"], "scan_type": "service"})
    assert r.status_code == 400
    assert "not authorized" in r.json()["detail"].lower()


def test_scan_missing_target_404(client):
    assert client.post("/api/scans", json={"target_id": 999999}).status_code == 404


def test_scan_invalid_type_400(client):
    t = make_target(client, authorized=True)
    r = client.post("/api/scans", json={"target_id": t["id"], "scan_type": "bogus"})
    assert r.status_code == 400


def test_scan_summary(client):
    r = client.get("/api/scans/summary")
    assert r.status_code == 200
    body = r.json()
    assert "total_scans" in body and "nmap_available" in body


def test_scan_status_and_results_404(client):
    assert client.get("/api/scans/424242/status").status_code == 404
    assert client.get("/api/scans/424242/results").status_code == 404


# --------------------------------------------------------------------------
# Recon — authorization + type validation (no network op performed here)
# --------------------------------------------------------------------------
def test_recon_requires_authorized_target(client):
    t = make_target(client, authorized=False)
    r = client.post("/api/recon", json={"target_id": t["id"], "recon_type": "host_discovery"})
    assert r.status_code == 400


def test_recon_invalid_type_400(client):
    t = make_target(client, authorized=True)
    r = client.post("/api/recon", json={"target_id": t["id"], "recon_type": "bogus"})
    assert r.status_code == 400


def test_recon_listing(client):
    assert client.get("/api/recon").status_code == 200


# --------------------------------------------------------------------------
# SOC events + summary + correlation
# --------------------------------------------------------------------------
def test_soc_crud_summary_correlation(client):
    e = client.post("/api/soc/events", json={
        "event_type": "network_scanning", "source": "fw-01",
        "message": "Port sweep detected from 10.0.0.5", "severity": "high",
    })
    assert e.status_code == 201, e.text
    eid = e.json()["id"]

    assert client.get(f"/api/soc/events/{eid}").status_code == 200
    assert client.put(f"/api/soc/events/{eid}", json={"status": "investigating"}).status_code == 200

    s = client.get("/api/soc/summary").json()
    assert s["total"] >= 1

    c = client.get("/api/soc/correlation")
    assert c.status_code == 200
    assert "clusters" in c.json()

    assert client.delete(f"/api/soc/events/{eid}").status_code == 200


def test_soc_event_requires_fields(client):
    assert client.post("/api/soc/events", json={"event_type": "x"}).status_code == 422


# --------------------------------------------------------------------------
# Purple team CRUD
# --------------------------------------------------------------------------
def test_purple_team_crud(client):
    p = client.post("/api/purple-team/tests", json={
        "name": "Brute-force detection validation", "technique": "T1110",
        "detection_status": "missed",
    })
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    # A missed detection produces a recommendation.
    assert p.json().get("recommendation")

    assert client.get(f"/api/purple-team/tests/{pid}").status_code == 200
    assert client.put(f"/api/purple-team/tests/{pid}", json={"status": "executed"}).status_code == 200
    assert client.delete(f"/api/purple-team/tests/{pid}").status_code == 200


# --------------------------------------------------------------------------
# Wi-Fi CRUD + sensor + discovery
# --------------------------------------------------------------------------
def test_wifi_crud_and_sensor(client):
    assert client.get("/api/wifi/sensor/status").status_code == 200

    w = client.post("/api/wifi/assessments", json={"ssid": "CorpGuest", "security_type": "WPA2"})
    assert w.status_code == 201, w.text
    wid = w.json()["id"]

    assert client.get(f"/api/wifi/assessments/{wid}").status_code == 200
    assert client.put(f"/api/wifi/assessments/{wid}", json={"status": "completed"}).status_code == 200

    d = client.post(f"/api/wifi/assessments/{wid}/discover")
    assert d.status_code == 200

    assert client.delete(f"/api/wifi/assessments/{wid}").status_code == 200


# --------------------------------------------------------------------------
# Attack map — honest empty state
# --------------------------------------------------------------------------
def test_attack_map_empty(client):
    r = client.get("/api/attack-map")
    assert r.status_code == 200
    body = r.json()
    assert body["has_data"] is False
    assert body["nodes"] == []


def test_attack_map_builds_from_links(client):
    a = make_assessment(client)
    t = make_target(client, assessment_id=a["id"])
    f = client.post("/api/findings", json={
        "title": "Open RDP", "severity": "critical",
        "assessment_id": a["id"], "target_id": t["id"],
    })
    assert f.status_code == 201
    m = client.get("/api/attack-map").json()
    assert m["has_data"] is True
    types = {n["type"] for n in m["nodes"]}
    assert "target" in types and "finding" in types


# --------------------------------------------------------------------------
# AI — fallback engine answers from the DB, never fabricates
# --------------------------------------------------------------------------
def test_ai_status_reports_fallback(client):
    r = client.get("/api/ai/status")
    assert r.status_code == 200
    body = r.json()
    assert body["external_provider_configured"] is False
    assert "fallback" in body["fallback_engine"].lower()


def test_ai_answers_without_external_key(client):
    a = make_assessment(client, "Fallback Check")
    client.post("/api/findings", json={
        "title": "Weak TLS", "severity": "high", "assessment_id": a["id"],
    })
    r = client.post("/api/ai", json={"question": "What is my highest risk?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"]
    assert "fallback" in (body.get("engine") or "").lower()


def test_ai_rejects_bad_context_type(client):
    r = client.post("/api/ai", json={"question": "hi", "context_type": "bogus"})
    assert r.status_code == 400


def test_ai_requires_question(client):
    assert client.post("/api/ai", json={}).status_code == 422


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
def test_settings_get_and_update(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    s = r.json()
    assert "voice" in s and "ai" in s and "platform" in s

    upd = client.put("/api/settings", json={"voice_rate": 1.3, "platform_name": "NexCYR"})
    assert upd.status_code == 200
    assert client.get("/api/settings").json()["voice"]["voice_rate"] == 1.3


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------
def test_search_finds_entities(client):
    make_assessment(client, "Searchable Engagement")
    r = client.get("/api/search?q=Searchable")
    assert r.status_code == 200
    body = r.json()
    assert any("Searchable" in (x.get("label") or "") for x in body.get("assessments", []))


# --------------------------------------------------------------------------
# Reports + PDF
# --------------------------------------------------------------------------
def test_report_generation_and_pdf(client):
    a = make_assessment(client, "Report Scope")
    t = make_target(client, assessment_id=a["id"])
    client.post("/api/findings", json={
        "title": "Exposed SSH", "severity": "medium",
        "assessment_id": a["id"], "target_id": t["id"],
    })

    r = client.post("/api/reports", json={"assessment_id": a["id"]})
    assert r.status_code in (200, 201), r.text

    listing = client.get("/api/reports").json()
    assert listing, "a report record should exist"

    pdf = client.get(f"/api/reports/pdf?assessment_id={a['id']}")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"
    assert len(pdf.content) > 1000
