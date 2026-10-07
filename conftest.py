"""Pytest configuration — isolated test database, no external AI.

The test DATABASE_URL / REPORTS_DIR are pointed at a throwaway temp location
BEFORE the application (and therefore the SQLAlchemy engine) is imported, so
the real nexcyr.db and reports/ directory are never touched by tests.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="nexcyr_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test_nexcyr.db').as_posix()}"
os.environ["REPORTS_DIR"] = str(_TMP / "reports")
# Force the fallback intelligence engine — tests never call an external LLM.
os.environ["OPENAI_API_KEY"] = ""
os.environ["AI_PROVIDER"] = ""
os.environ["AI_MODEL"] = ""
os.environ["NMAP_PATH"] = ""

import pytest
from fastapi.testclient import TestClient

import database
from main import app


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_schema():
    database.Base.metadata.create_all(bind=database.engine)
    yield


@pytest.fixture()
def client():
    """A client bound to freshly-recreated (empty) tables for isolation."""
    database.Base.metadata.drop_all(bind=database.engine)
    database.Base.metadata.create_all(bind=database.engine)
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------
def make_assessment(client, name="Test Assessment"):
    r = client.post("/api/assessments", json={"name": name, "assessment_type": "general"})
    assert r.status_code == 201, r.text
    return r.json()


def make_target(client, *, authorized=True, value="127.0.0.1", target_type="ip",
                assessment_id=None, name=None):
    body = {"target_type": target_type, "value": value, "authorized": authorized}
    if assessment_id is not None:
        body["assessment_id"] = assessment_id
    if name is not None:
        body["name"] = name
    r = client.post("/api/targets", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def enroll_agent(client, name="NexCYR Agent 01", agent_key=None):
    body = {"name": name}
    if agent_key:
        body["agent_key"] = agent_key
    r = client.post("/api/agents", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def register_agent(client, token, *, nmap=True, service_enum=True, port_scan=True,
                   host_discovery=True, version="1.0.0"):
    caps = {
        "nmap": nmap,
        "host_discovery": host_discovery,
        "port_scan": port_scan,
        "service_enumeration": service_enum,
    }
    r = client.post(
        "/api/agents/register",
        headers={"X-NexCYR-Agent-Token": token},
        json={"hostname": "agent-host", "platform": "linux", "arch": "x86_64",
              "version": version, "capabilities": caps},
    )
    assert r.status_code == 200, r.text
    return r.json()
