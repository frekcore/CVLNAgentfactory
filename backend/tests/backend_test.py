"""
CVLN Agent Factory - Backend regression tests
Covers: auth, registry, adl validation, generator, doctrine, external, events, memory, audit, monitoring, users.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

API = f"{BASE_URL}/api"

ADMIN_EMAIL = "laurent@cvln.fr"
ADMIN_PASSWORD = "CVLNfactory2026!"
AGT000_TOKEN = "svc_agt000_9f2e7c1a4b8d6f3e0a5c2d7b1e4f8a6c"

# unique run suffix so re-runs don't collide
RUN = str(int(time.time()))[-6:]


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def svc_headers():
    return {"Authorization": f"Bearer {AGT000_TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def reader_user(admin_headers):
    """Create a reader user for negative-authz tests."""
    email = f"TEST_reader_{RUN}@cvln.fr"
    password = "ReaderPass123!"
    r = requests.post(f"{API}/users", headers=admin_headers,
                      json={"email": email, "password": password, "name": "TEST Reader", "role": "reader"})
    assert r.status_code in (200, 201, 409), r.text
    if r.status_code == 200 or r.status_code == 201:
        user = r.json()
    else:
        user = None
    login = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"email": email, "password": password, "token": token, "user": user}


@pytest.fixture(scope="session")
def reader_headers(reader_user):
    return {"Authorization": f"Bearer {reader_user['token']}", "Content-Type": "application/json"}


# ---------- Auth ----------
class TestAuth:
    def test_login_success(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data and len(data["access_token"]) > 10
        assert data["user"]["email"] == ADMIN_EMAIL
        assert data["user"]["role"] == "admin"

    def test_login_bad_credentials(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong!"})
        assert r.status_code == 401

    def test_me_with_bearer(self, admin_headers):
        r = requests.get(f"{API}/auth/me", headers=admin_headers)
        assert r.status_code == 200
        me = r.json()
        assert me["type"] == "human"
        assert me["role"] == "admin"

    def test_me_without_token(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401


# ---------- Registry read ----------
class TestRegistryRead:
    def test_stats(self, admin_headers):
        r = requests.get(f"{API}/registry/stats", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["total"] >= 11
        assert d["target"] == 284
        assert "by_status" in d and "by_pole" in d and "by_entity" in d

    def test_list_agents(self, admin_headers):
        r = requests.get(f"{API}/registry/agents", headers=admin_headers)
        assert r.status_code == 200
        agents = r.json()
        ids = [a["id"] for a in agents]
        for expected in ["AGT-000", "AGT-005", "AGT-010"]:
            assert expected in ids

    def test_filter_by_status(self, admin_headers):
        r = requests.get(f"{API}/registry/agents?status=Production", headers=admin_headers)
        assert r.status_code == 200
        assert all(a["status"] == "Production" for a in r.json())

    def test_search(self, admin_headers):
        r = requests.get(f"{API}/registry/agents?search=Architect", headers=admin_headers)
        assert r.status_code == 200
        assert any(a["id"] == "AGT-000" for a in r.json())

    def test_get_agent_detail(self, admin_headers):
        r = requests.get(f"{API}/registry/agents/AGT-000", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == "AGT-000"
        assert "allowed_transitions" in d
        assert "adl" in d


# ---------- ADL validate ----------
class TestADLValidate:
    def test_valid_adl(self, admin_headers):
        yaml_body = """adl_version: "1.0"
agent:
  id: AGT-777
  name: Valid Test Agent
  pole: Test
  entity: CVLN Holding
  version: 0.1.0
  mission: A perfectly valid ADL for testing validation endpoint.
  vision: ""
  objectives: []
  kpis: []
brain:
  memory:
    scope: session
    owner: AGT-777
  identity:
    autonomy_level: supervised
permissions:
  read: [registry]
  write: []
  entities: [CVLN Holding]
tests:
  - name: identity_check
    assertion: agent.id == 'AGT-777'
"""
        r = requests.post(f"{API}/adl/validate", headers=admin_headers, json={"adl_yaml": yaml_body})
        assert r.status_code == 200
        d = r.json()
        assert d["valid"] is True and d["errors"] == []

    def test_invalid_adl_bad_id(self, admin_headers):
        bad = """adl_version: "1.0"
agent:
  id: INVALID
  name: xx
  pole: p
  entity: e
  version: 0.1.0
  mission: short
"""
        r = requests.post(f"{API}/adl/validate", headers=admin_headers, json={"adl_yaml": bad})
        assert r.status_code == 200
        d = r.json()
        assert d["valid"] is False
        paths = ".".join(e["path"] for e in d["errors"])
        assert "id" in paths or "mission" in paths or "name" in paths


# ---------- Registry compile ----------
class TestRegistryCompile:
    def test_reader_cannot_compile(self, reader_headers):
        yaml_body = self._minimal_adl("AGT-800", f"TEST_ReaderBlock_{RUN}")
        r = requests.post(f"{API}/registry/compile", headers=reader_headers, json={"adl_yaml": yaml_body})
        assert r.status_code == 403

    def test_denied_appears_in_audit(self, admin_headers):
        # give backend a moment
        time.sleep(0.5)
        r = requests.get(f"{API}/audit?allowed=false", headers=admin_headers)
        assert r.status_code == 200
        logs = r.json()
        assert any(l.get("allowed") is False for l in logs), "no denied audit entries found"

    def test_svc_token_compile_creates_draft(self, svc_headers, admin_headers):
        agent_id = "AGT-800"
        name = f"TEST_SvcCompile_{RUN}"
        yaml_body = self._minimal_adl(agent_id, name)
        r = requests.post(f"{API}/registry/compile", headers=svc_headers, json={"adl_yaml": yaml_body})
        # may already exist from previous run
        if r.status_code == 409:
            pytest.skip(f"AGT-800 already exists: {r.text}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["agent_id"] == agent_id
        assert d["status"] == "Draft"
        # verify via GET
        g = requests.get(f"{API}/registry/agents/{agent_id}", headers=admin_headers)
        assert g.status_code == 200
        assert g.json()["status"] == "Draft"

    def test_recompile_lower_version_conflict(self, svc_headers):
        agent_id = "AGT-800"
        yaml_same = self._minimal_adl(agent_id, f"TEST_SvcCompile_{RUN}", version="0.1.0")
        r = requests.post(f"{API}/registry/compile", headers=svc_headers, json={"adl_yaml": yaml_same})
        assert r.status_code == 409

    def test_recompile_higher_version_ok(self, svc_headers, admin_headers):
        agent_id = "AGT-800"
        yaml_v2 = self._minimal_adl(agent_id, f"TEST_SvcCompile_{RUN}", version="0.2.0")
        r = requests.post(f"{API}/registry/compile", headers=svc_headers, json={"adl_yaml": yaml_v2})
        assert r.status_code == 200, r.text
        assert r.json()["version"] == "0.2.0"
        # versions history
        v = requests.get(f"{API}/registry/agents/{agent_id}/versions", headers=admin_headers)
        assert v.status_code == 200
        versions = [x["version"] for x in v.json() if x.get("type") == "version"]
        assert "0.1.0" in versions and "0.2.0" in versions

    def test_duplicate_name_conflict(self, admin_headers):
        yaml_dup = self._minimal_adl("AGT-801", "CVLN Agent Architect")  # same name as AGT-000
        r = requests.post(f"{API}/registry/compile", headers=admin_headers, json={"adl_yaml": yaml_dup})
        assert r.status_code == 409
        detail = r.json().get("detail", {})
        assert detail.get("type") == "duplicate"
        assert len(detail.get("duplicates", [])) >= 1

    @staticmethod
    def _minimal_adl(agent_id, name, version="0.1.0"):
        return f"""adl_version: "1.0"
agent:
  id: {agent_id}
  name: {name}
  pole: Test
  entity: CVLN Holding
  version: {version}
  mission: Mission de test valide (au moins dix caractères).
  vision: ""
  objectives: []
  kpis: []
brain:
  memory:
    scope: session
    owner: {agent_id}
  identity:
    autonomy_level: supervised
permissions:
  read: [registry]
  write: []
  entities: [CVLN Holding]
tests:
  - name: identity_check
    assertion: agent.id == '{agent_id}'
"""


# ---------- Lifecycle ----------
class TestLifecycle:
    def test_diff_between_versions(self, admin_headers):
        r = requests.get(f"{API}/registry/agents/AGT-800/versions", headers=admin_headers)
        if r.status_code != 200:
            pytest.skip("AGT-800 unavailable")
        versions = [v["version"] for v in r.json() if v.get("type") == "version"]
        if "0.1.0" not in versions or "0.2.0" not in versions:
            pytest.skip("versions unavailable")
        d = requests.get(f"{API}/registry/agents/AGT-800/diff?from_version=0.1.0&to_version=0.2.0",
                         headers=admin_headers)
        assert d.status_code == 200
        assert "diff" in d.json()


# ---------- Generator ----------
class TestGenerator:
    def test_direct_generate(self, admin_headers):
        definition = {
            "name": f"TEST_QAGen_{RUN}",
            "category": "QA",
            "pole": "Test",
            "entity": "CVLN Holding",
            "mission": "Agent QA généré par pipeline test automatisé.",
            "objectives": ["obj1"],
            "skills": ["python"],
            "tools": ["pytest"],
            "autonomy_level": "supervised",
            "kpis": ["coverage"],
        }
        r = requests.post(f"{API}/generator/generate", headers=admin_headers,
                          json={"definition": definition})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["result"] == "generated"
        assert d["agent_id"].startswith("AGT-")
        assert d["status"] == "Beta"
        assert d["service_token"].startswith("svc_")
        # 11 pipeline steps expected
        step_names = [s["step"] for s in d["steps"]]
        for expected in ["business_analysis", "adl_generation", "doctrine_compliance",
                         "duplicate_check", "id_assignment", "identity_creation",
                         "permissions", "memory_space", "events_setup",
                         "registry_registration", "lifecycle_progression"]:
            assert expected in step_names, f"missing step {expected}: {step_names}"

    def test_generate_via_catalog(self, admin_headers):
        definition = {
            "name": f"TEST_CatalogGen_{RUN}",
            "category": "QA",
            "pole": "Test",
            "entity": "CVLN Holding",
            "mission": "Agent QA généré via catalogue.",
            "objectives": [],
            "skills": [],
            "tools": [],
            "autonomy_level": "supervised",
            "kpis": [],
        }
        c = requests.post(f"{API}/generator/catalog", headers=admin_headers, json=definition)
        assert c.status_code == 200, c.text
        cat_id = c.json()["id"]
        g = requests.post(f"{API}/generator/generate", headers=admin_headers,
                          json={"catalog_id": cat_id})
        assert g.status_code == 200, g.text
        assert g.json()["status"] == "Beta"
        # catalog entry now marked
        cat = requests.get(f"{API}/generator/catalog", headers=admin_headers).json()
        entry = next((e for e in cat if e["id"] == cat_id), None)
        assert entry and entry["generated_agent_id"] == g.json()["agent_id"]

    def test_generate_duplicate_name(self, admin_headers):
        definition = {
            "name": "CVLN Agent Architect",  # duplicates AGT-000
            "category": "QA",
            "pole": "Test",
            "entity": "CVLN Holding",
            "mission": "Tentative de doublon volontaire.",
            "objectives": [], "skills": [], "tools": [], "kpis": [],
            "autonomy_level": "supervised",
        }
        r = requests.post(f"{API}/generator/generate", headers=admin_headers, json={"definition": definition})
        assert r.status_code == 409


# ---------- Doctrine ----------
class TestDoctrine:
    def test_get_doctrine(self, admin_headers):
        r = requests.get(f"{API}/doctrine", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["version"] == "1.0"
        assert len(d["sections"]) == 6

    def test_doctrine_check_violation(self, admin_headers):
        # Agent NOT AGT-000 with write=[registry] should violate DOC-SEC-01
        yaml_bad = """adl_version: "1.0"
agent:
  id: AGT-802
  name: TEST DocViol
  pole: Test
  entity: CVLN Holding
  version: 0.1.0
  mission: Test ADL avec violation doctrine.
brain:
  memory:
    scope: session
    owner: AGT-802
  identity:
    autonomy_level: supervised
permissions:
  read: [registry]
  write: [registry]
  entities: [CVLN Holding]
tests:
  - name: identity_check
    assertion: agent.id == 'AGT-802'
"""
        r = requests.post(f"{API}/doctrine/check", headers=admin_headers, json={"adl_yaml": yaml_bad})
        assert r.status_code == 200
        d = r.json()
        assert d["compliant"] is False
        violation_ids = [v["rule_id"] for v in d["violations"]]
        assert "DOC-SEC-01" in violation_ids


# ---------- External ----------
class TestExternal:
    def test_list_external(self, admin_headers):
        r = requests.get(f"{API}/external", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert len(d["systems"]) == 8
        keys = [s["key"] for s in d["systems"]]
        for k in ["laurent-ia", "kora", "frek", "kiltikonet", "labelos", "good-mood", "cvl-academy", "cvln-central"]:
            assert k in keys

    def test_external_kora_501(self, admin_headers):
        r = requests.get(f"{API}/external/kora", headers=admin_headers)
        assert r.status_code == 501

    def test_laurent_ia_501(self, admin_headers):
        r = requests.get(f"{API}/laurent-ia", headers=admin_headers)
        assert r.status_code == 501


# ---------- Events / Memory / Audit / Monitoring ----------
class TestCoreServices:
    def test_events_list(self, admin_headers):
        r = requests.get(f"{API}/events?limit=20", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_events_filter_topic(self, admin_headers):
        r = requests.get(f"{API}/events?topic=agent", headers=admin_headers)
        assert r.status_code == 200
        for e in r.json():
            assert "agent" in e["topic"].lower()

    def test_memory_write_read(self, admin_headers):
        payload = {"agent_id": "AGT-000", "entity": "CVLN Holding",
                   "scope": "session", "key": f"TEST_key_{RUN}",
                   "value": {"note": "test entry"}}
        w = requests.post(f"{API}/memory", headers=admin_headers, json=payload)
        assert w.status_code == 200
        r = requests.get(f"{API}/memory/AGT-000", headers=admin_headers)
        assert r.status_code == 200
        keys = [e["key"] for e in r.json()]
        assert f"TEST_key_{RUN}" in keys

    def test_memory_logs(self, admin_headers):
        r = requests.get(f"{API}/memory/logs?limit=10", headers=admin_headers)
        assert r.status_code == 200

    def test_monitoring_health(self, admin_headers):
        r = requests.get(f"{API}/monitoring/health", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["database"] == "up"
        assert len(d["services"]) == 5
        assert all(s["status"] == "healthy" for s in d["services"])

    def test_monitoring_dashboard(self, admin_headers):
        r = requests.get(f"{API}/monitoring/dashboard", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert "active_agents" in d
        assert "recent_events" in d


# ---------- Users management ----------
class TestUsersManagement:
    def test_create_operator_then_patch_and_delete(self, admin_headers):
        email = f"TEST_op_{RUN}_{uuid.uuid4().hex[:6]}@cvln.fr"
        c = requests.post(f"{API}/users", headers=admin_headers,
                          json={"email": email, "password": "OpPass123!", "name": "TEST Op", "role": "operator"})
        assert c.status_code == 200, c.text
        user = c.json()
        # patch role -> reader
        p = requests.patch(f"{API}/users/{user['id']}", headers=admin_headers, json={"role": "reader"})
        assert p.status_code == 200
        # verify
        lst = requests.get(f"{API}/users", headers=admin_headers).json()
        row = next((u for u in lst if u["id"] == user["id"]), None)
        assert row and row["role"] == "reader"
        # delete
        d = requests.delete(f"{API}/users/{user['id']}", headers=admin_headers)
        assert d.status_code == 200

    def test_reader_cannot_list_users(self, reader_headers):
        r = requests.get(f"{API}/users", headers=reader_headers)
        assert r.status_code == 403
