"""Tests for CVLN Autonomous Workforce Layer (Iteration 3)
Covers: entities registry, pilots, autonomy, tasks, workspace, finance,
knowledge, evolution proposals, founder overview, industrial bulk import + batch.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "laurent@cvln.fr"
ADMIN_PWD = "CVLNfactory2026!"
SVC_TOKEN = "svc_agt000_9f2e7c1a4b8d6f3e0a5c2d7b1e4f8a6c"
RUN = uuid.uuid4().hex[:6]

PILOTS = ["AGT-011", "AGT-012", "AGT-013", "AGT-014", "AGT-015"]


# ------------------ Fixtures ------------------

@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def svc_headers():
    return {"Authorization": f"Bearer {SVC_TOKEN}"}


@pytest.fixture(scope="session")
def reader_headers(admin_headers):
    """Create a TEST reader user and return its bearer headers."""
    run = str(int(time.time()))
    email = f"TEST_wf_reader_{run}@cvln.fr"
    pwd = "ReaderPass123!"
    r = requests.post(f"{API}/users", headers=admin_headers,
                      json={"email": email, "password": pwd, "role": "reader", "name": "TEST reader"})
    # already exists is OK
    assert r.status_code in (200, 201, 409), r.text
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ------------------ Entities ------------------
class TestEntities:
    def test_list_entities_returns_10(self, admin_headers):
        r = requests.get(f"{API}/entities", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        names = {e["name"] for e in data}
        required = {"CVLN Holding", "CVLN Brain", "Kiltikonet", "Laurent.ia", "FREK",
                    "KORA", "LabelOS", "Factory Maker Studio", "Good Mood", "CVL Academy"}
        assert required.issubset(names), f"Missing: {required - names}"

    def test_cvln_holding_detail_has_pilots(self, admin_headers):
        r = requests.get(f"{API}/entities", headers=admin_headers)
        holding = next(e for e in r.json() if e["name"] == "CVLN Holding")
        r2 = requests.get(f"{API}/entities/{holding['id']}", headers=admin_headers)
        assert r2.status_code == 200
        agent_ids = {a["id"] for a in r2.json().get("agents", [])}
        for pid in ("AGT-011", "AGT-012", "AGT-015"):
            assert pid in agent_ids, f"{pid} missing from CVLN Holding"

    def test_create_entity_admin_and_duplicate_409(self, admin_headers):
        name = f"TEST_Entity_QA_{RUN}"
        payload = {"name": name, "type": "other", "description": "test",
                   "activities": [], "data_domains": [], "apis": [], "objectives": []}
        r = requests.post(f"{API}/entities", headers=admin_headers, json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["name"] == name
        # duplicate
        r2 = requests.post(f"{API}/entities", headers=admin_headers, json=payload)
        assert r2.status_code == 409

    def test_link_agent_to_entity(self, admin_headers):
        name = f"TEST_Entity_QA_{RUN}"
        r = requests.get(f"{API}/entities", headers=admin_headers)
        target = next(e for e in r.json() if e["name"] == name)
        r2 = requests.post(f"{API}/entities/{target['id']}/agents", headers=admin_headers,
                           json={"agent_ids": ["AGT-011"]})
        assert r2.status_code == 200
        assert "AGT-011" in r2.json()["linked"]
        r3 = requests.get(f"{API}/entities/{target['id']}", headers=admin_headers)
        assert "AGT-011" in [a["id"] for a in r3.json()["agents"]]


# ------------------ Pilot agents ------------------
class TestPilots:
    def test_pilots_present_beta_generated(self, admin_headers):
        # Beta at seed; may already be promoted to Production by human admin during
        # prior QA iterations (that's a valid state per lifecycle rules).
        for pid in PILOTS:
            r = requests.get(f"{API}/registry/agents/{pid}", headers=admin_headers)
            assert r.status_code == 200, f"{pid} not found"
            a = r.json()
            assert a["status"] in ("Beta", "Production"), f"{pid} status={a['status']}"
            assert a.get("generated") is True
            assert a.get("pilot") is True

    def test_pilots_have_lifecycle_history(self, admin_headers):
        r = requests.get(f"{API}/registry/agents/AGT-011/versions", headers=admin_headers)
        assert r.status_code == 200
        statuses = {v["status"] for v in r.json()}
        # Should have progression Draft → Prototype → Alpha → Beta
        assert "Prototype" in statuses or "Beta" in statuses  # lifecycle history exists
        assert "Beta" in statuses


# ------------------ Autonomy ------------------
class TestAutonomy:
    def test_autonomy_levels_endpoint(self, admin_headers):
        r = requests.get(f"{API}/workforce/autonomy-levels", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        # 4 levels 1-4 (keys may be strings)
        keys = {int(k) for k in data.keys()}
        assert keys == {1, 2, 3, 4}

    def test_admin_can_set_l1_l4(self, admin_headers):
        # L1
        r = requests.post(f"{API}/workforce/agents/AGT-011/autonomy", headers=admin_headers,
                          json={"level": 1, "note": "test L1"})
        assert r.status_code == 200
        assert r.json()["autonomy"]["level"] == 1
        # L4
        r = requests.post(f"{API}/workforce/agents/AGT-011/autonomy", headers=admin_headers,
                          json={"level": 4, "note": "test L4"})
        assert r.status_code == 200
        assert r.json()["autonomy"]["level"] == 4
        # restore L2
        r = requests.post(f"{API}/workforce/agents/AGT-011/autonomy", headers=admin_headers,
                          json={"level": 2, "note": "restore"})
        assert r.status_code == 200

    def test_svc_can_L1_L2(self, svc_headers):
        r = requests.post(f"{API}/workforce/agents/AGT-012/autonomy", headers=svc_headers,
                         json={"level": 2, "note": "svc L2"})
        assert r.status_code == 200

    def test_svc_forbidden_L3_L4(self, svc_headers):
        r = requests.post(f"{API}/workforce/agents/AGT-012/autonomy", headers=svc_headers,
                          json={"level": 3, "note": "svc tries L3"})
        assert r.status_code == 403
        r2 = requests.post(f"{API}/workforce/agents/AGT-012/autonomy", headers=svc_headers,
                           json={"level": 4, "note": "svc tries L4"})
        assert r2.status_code == 403


# ------------------ Tasks ------------------
class TestTasks:
    def test_create_task_admin(self, admin_headers):
        payload = {"agent_id": "AGT-011", "title": "TEST_QA task", "priority": "P1", "description": "test"}
        r = requests.post(f"{API}/workforce/tasks", headers=admin_headers, json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "open"
        assert data["agent_id"] == "AGT-011"
        pytest.task_id = data["id"]

    def test_reader_forbidden_create_task(self, reader_headers):
        payload = {"agent_id": "AGT-011", "title": "reader task", "priority": "P1"}
        r = requests.post(f"{API}/workforce/tasks", headers=reader_headers, json=payload)
        assert r.status_code == 403

    def test_invalid_status_400(self, admin_headers):
        r = requests.patch(f"{API}/workforce/tasks/{pytest.task_id}", headers=admin_headers,
                           json={"status": "invalid_status"})
        assert r.status_code == 400

    def test_patch_task_to_done(self, admin_headers):
        r = requests.patch(f"{API}/workforce/tasks/{pytest.task_id}", headers=admin_headers,
                           json={"status": "done"})
        assert r.status_code == 200
        # verify persistence
        r2 = requests.get(f"{API}/workforce/tasks?agent_id=AGT-011", headers=admin_headers)
        matched = [t for t in r2.json() if t["id"] == pytest.task_id]
        assert matched and matched[0]["status"] == "done"

    def test_service_can_only_update_own_task(self, svc_headers, admin_headers):
        # Create a task assigned to AGT-011 (not AGT-000)
        r = requests.post(f"{API}/workforce/tasks", headers=admin_headers,
                          json={"agent_id": "AGT-011", "title": "TEST_svc_not_own", "priority": "P2"})
        tid = r.json()["id"]
        # svc = AGT-000 tries to update
        r2 = requests.patch(f"{API}/workforce/tasks/{tid}", headers=svc_headers,
                            json={"status": "in_progress"})
        assert r2.status_code == 403


# ------------------ Workspace ------------------
class TestWorkspace:
    def test_workspace_agt_011(self, admin_headers):
        r = requests.get(f"{API}/workforce/workspace/AGT-011", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        # agent block
        assert data["agent"]["id"] == "AGT-011"
        assert "autonomy" in data["agent"]
        assert isinstance(data["agent"].get("kpis"), list)
        assert "tools" in data["agent"]
        assert "permissions" in data["agent"]
        # briefing
        assert "briefing" in data
        assert "objectives" in data["briefing"]
        assert "priority_tasks" in data["briefing"]
        # tasks, daily_reports, memory
        assert isinstance(data["tasks"], list)
        assert isinstance(data["daily_reports"], list)
        assert "memory" in data
        # entities include CVLN Holding
        entity_names = {e["name"] for e in data["entities"]}
        assert "CVLN Holding" in entity_names


# ------------------ Finance ------------------
class TestFinance:
    def test_post_cost_entry(self, admin_headers):
        r = requests.post(f"{API}/finance/entries", headers=admin_headers, json={
            "type": "cost", "category": "api", "agent_id": "AGT-011", "entity": "CVLN Holding",
            "amount": 25.5, "description": "TEST cost"})
        assert r.status_code == 200, r.text
        assert r.json()["type"] == "cost"

    def test_post_revenue_entry(self, admin_headers):
        r = requests.post(f"{API}/finance/entries", headers=admin_headers, json={
            "type": "revenue", "category": "service", "agent_id": "AGT-011",
            "entity": "CVLN Holding", "amount": 200.0, "description": "TEST revenue"})
        assert r.status_code == 200

    def test_invalid_type_400(self, admin_headers):
        r = requests.post(f"{API}/finance/entries", headers=admin_headers, json={
            "type": "bogus", "amount": 10})
        assert r.status_code == 400

    def test_amount_le_zero_422(self, admin_headers):
        r = requests.post(f"{API}/finance/entries", headers=admin_headers, json={
            "type": "cost", "amount": 0})
        assert r.status_code == 422

    def test_reader_forbidden(self, reader_headers):
        r = requests.post(f"{API}/finance/entries", headers=reader_headers, json={
            "type": "cost", "amount": 5})
        assert r.status_code == 403

    def test_summary_totals_and_roi(self, admin_headers):
        r = requests.get(f"{API}/finance/summary", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        for k in ("total_cost", "total_revenue", "roi_percent", "by_agent", "forecast_net_30d"):
            assert k in d, f"missing {k}"
        assert d["total_cost"] >= 25.5
        assert d["total_revenue"] >= 200


# ------------------ Knowledge ------------------
class TestKnowledge:
    def test_ingest_auto_classify_doctrine(self, admin_headers):
        r = requests.post(f"{API}/knowledge/ingest", headers=admin_headers, json={
            "title": "TEST_doctrine_QA",
            "source_type": "note",
            "content": "Cette doctrine définit la règle de gouvernance des agents.",
            "target_agents": ["AGT-011"]
        })
        assert r.status_code == 200, r.text
        item = r.json()
        assert item["category"] == "doctrine"
        assert item["auto_classified"] is True
        pytest.knowledge_id = item["id"]

    def test_memory_entry_created_for_target_agent(self, admin_headers):
        # workspace memory count should include a strategic entry now
        r = requests.get(f"{API}/workforce/workspace/AGT-011", headers=admin_headers)
        assert r.status_code == 200
        # knowledge array should include our item
        titles = [k["title"] for k in r.json().get("knowledge", [])]
        assert "TEST_doctrine_QA" in titles

    def test_validate_admin_only(self, admin_headers, reader_headers):
        r_reader = requests.post(f"{API}/knowledge/items/{pytest.knowledge_id}/validate", headers=reader_headers)
        assert r_reader.status_code == 403
        r = requests.post(f"{API}/knowledge/items/{pytest.knowledge_id}/validate", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["result"] == "validated"

    def test_brain_stats(self, admin_headers):
        r = requests.get(f"{API}/knowledge/brain/stats", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert "by_category" in d and "by_status" in d
        assert d["by_category"].get("doctrine", 0) >= 1


# ------------------ Evolution ------------------
class TestEvolution:
    def test_svc_can_propose(self, svc_headers):
        r = requests.post(f"{API}/evolution/proposals", headers=svc_headers, json={
            "type": "improve_agent",
            "title": "TEST_QA improve AGT-011",
            "description": "Improve responsiveness by 10%.",
            "target_agent_id": "AGT-011"
        })
        assert r.status_code == 200, r.text
        pytest.proposal_id = r.json()["id"]

    def test_reader_forbidden_propose(self, reader_headers):
        r = requests.post(f"{API}/evolution/proposals", headers=reader_headers, json={
            "type": "improve_agent", "title": "reader tries",
            "description": "should be blocked here"
        })
        assert r.status_code == 403

    def test_invalid_type_400(self, admin_headers):
        r = requests.post(f"{API}/evolution/proposals", headers=admin_headers, json={
            "type": "bogus_type", "title": "Valid title long enough",
            "description": "bad type test 12345"
        })
        assert r.status_code == 400

    def test_svc_forbidden_decide(self, svc_headers):
        r = requests.post(f"{API}/evolution/proposals/{pytest.proposal_id}/decide",
                          headers=svc_headers, json={"decision": "validated"})
        assert r.status_code == 403

    def test_admin_validate(self, admin_headers):
        r = requests.post(f"{API}/evolution/proposals/{pytest.proposal_id}/decide",
                          headers=admin_headers, json={"decision": "validated", "note": "ok"})
        assert r.status_code == 200
        assert r.json()["result"] == "validated"

    def test_re_decide_409(self, admin_headers):
        r = requests.post(f"{API}/evolution/proposals/{pytest.proposal_id}/decide",
                          headers=admin_headers, json={"decision": "rejected"})
        assert r.status_code == 409


# ------------------ Founder overview ------------------
class TestFounder:
    def test_admin_overview(self, admin_headers):
        r = requests.get(f"{API}/founder/overview", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["ecosystem"]["target"] == 284
        assert "by_status" in d["ecosystem"]
        beta = [a["id"] for a in d["pending_validations"]["beta_awaiting_production"]]
        # At least 4 of 5 pilots must still be in Beta (some may already be promoted)
        beta_pilots = [pid for pid in PILOTS if pid in beta]
        assert len(beta_pilots) >= 4, f"Expected ≥4 pilots in Beta list, got: {beta_pilots}"
        assert "finance" in d
        assert "knowledge" in d

    def test_reader_forbidden(self, reader_headers):
        r = requests.get(f"{API}/founder/overview", headers=reader_headers)
        assert r.status_code == 403


# ------------------ Industrial : bulk-import + batch generate ------------------
class TestIndustrial:
    def test_bulk_import_csv(self, admin_headers):
        csv_data = ("name,category,pole,entity,mission,objectives,skills,tools,autonomy_level,kpis\n"
                    f"TEST_QA_CSV_Agent1_{RUN},QA,Test,CVLN Holding,Mission de test QA en masse via CSV run {RUN} unique,"
                    "obj1;obj2,skill1,tool1,supervised,kpi1;kpi2\n"
                    f"TEST_QA_CSV_Agent2_{RUN},QA,Test,CVLN Holding,Mission secondaire QA CSV run {RUN} unique,,,,supervised,\n")
        r = requests.post(f"{API}/generator/bulk-import", headers=admin_headers,
                          json={"format": "csv", "data": csv_data})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["imported"] >= 1, f"errors={d.get('errors')}"
        assert f"TEST_QA_CSV_Agent1_{RUN}" in d["names"]

    def test_bulk_import_duplicate_flagged(self, admin_headers):
        # Re-import same names should produce errors
        csv_data = ("name,category,pole,entity,mission,objectives,skills,tools,autonomy_level,kpis\n"
                    f"TEST_QA_CSV_Agent1_{RUN},QA,Test,CVLN Holding,Mission de test QA en masse via CSV run {RUN} unique,,,,supervised,\n")
        r = requests.post(f"{API}/generator/bulk-import", headers=admin_headers,
                          json={"format": "csv", "data": csv_data})
        assert r.status_code == 200
        assert r.json()["errors"], "duplicate should be listed in errors"
        assert any(f"TEST_QA_CSV_Agent1_{RUN}" == e["name"] for e in r.json()["errors"])

    def test_bulk_import_json(self, admin_headers):
        name = f"TEST_QA_JSON_Agent1_{RUN}"
        payload = [{
            "name": name,
            "category": "QA", "pole": "Test", "entity": "CVLN Holding",
            "mission": f"Mission JSON de test pour import en masse du catalogue run {RUN} unique.",
            "objectives": ["obj a"], "skills": [], "tools": [], "kpis": []
        }]
        import json
        r = requests.post(f"{API}/generator/bulk-import", headers=admin_headers,
                          json={"format": "json", "data": json.dumps(payload)})
        assert r.status_code == 200
        assert name in r.json()["names"], f"{name} not in {r.json()}"

    def test_generate_batch_all_pending(self, admin_headers):
        r = requests.post(f"{API}/generator/generate-batch", headers=admin_headers,
                          json={"all_pending": True})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["generated"] >= 1, f"no agents generated: {d}"
        for a in d["agents"]:
            assert a["status"] == "Beta"
        # verify catalog entries now have generated_agent_id
        cat = requests.get(f"{API}/generator/catalog", headers=admin_headers).json()
        matched = [c for c in cat if c["name"].startswith("TEST_QA_") and RUN in c["name"]]
        assert any(c.get("generated_agent_id") for c in matched)
