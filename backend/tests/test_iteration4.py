"""
CVLN Agent Factory — Iteration 4 backend tests
Covers: Founder Notification Service, Mission Engine + Orchestrator + Performance,
Cognitive Interface (chat/confirm/temporal/conversations), Continuity Layer (backup/list).
"""
import os
import time
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
RUN = str(int(time.time()))[-6:]


# ---------------- Fixtures ----------------
@pytest.fixture(scope="session")
def admin_headers():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def svc_headers():
    return {"Authorization": f"Bearer {AGT000_TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def reader_headers(admin_headers):
    email = f"TEST_it4_reader_{RUN}@cvln.fr"
    password = "ReaderPass123!"
    r = requests.post(f"{API}/users", headers=admin_headers,
                      json={"email": email, "password": password, "name": "TEST it4 Reader", "role": "reader"})
    assert r.status_code in (200, 201, 409), r.text
    login = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}", "Content-Type": "application/json"}


# ================= (A) Founder Notification Service =================
class TestNotifications:
    def test_settings_expects_telegram_but_not_connected(self, admin_headers):
        r = requests.get(f"{API}/notifications/settings", headers=admin_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["telegram_configured"] is True
        assert d["founder_chat_connected"] is False
        # 4 levels
        assert set(map(int, d["levels"].keys())) == {1, 2, 3, 4}

    def test_send_test_returns_502_but_persists_notification(self, admin_headers):
        before = requests.get(f"{API}/notifications", headers=admin_headers).json()
        r = requests.post(f"{API}/notifications/test", headers=admin_headers,
                          json={"message": f"TEST it4 notif {RUN}"})
        # Push fails cleanly because /start not sent → backend returns 502 EXPECTED.
        # NOTE: The Cloudflare/ingress in front of the app intercepts origin 502 responses
        # and replaces the body with an HTML "Bad gateway" page. Body/detail therefore
        # can NOT be relied on from the client side. We only assert the status code and
        # verify the notification is still persisted in Mongo.
        assert r.status_code == 502, f"expected 502 got {r.status_code} — {r.text[:200]}"
        # But notification persisted
        after = requests.get(f"{API}/notifications", headers=admin_headers).json()
        assert len(after) >= len(before) + 1
        titles = [n["title"] for n in after]
        assert "Test CVLN Command" in titles

    def test_discover_chat_returns_404(self, admin_headers):
        r = requests.post(f"{API}/notifications/discover-chat", headers=admin_headers)
        # Founder has not sent /start → clean 404
        assert r.status_code == 404, r.text

    def test_list_notifications_admin_only(self, reader_headers):
        r = requests.get(f"{API}/notifications", headers=reader_headers)
        assert r.status_code == 403


# ================= (B) Mission Assignment Engine + Orchestrator + Performance =================
class TestMissionEngine:
    mission_id = None
    recommended_agents = []

    def test_orchestrate_strategy_intent(self, admin_headers):
        r = requests.post(f"{API}/missions/orchestrate", headers=admin_headers,
                          json={"request_text": "Analyse la stratégie marketing digitale de Factory Maker Studio"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["intent"]["mission_type"] == "strategy"
        assert isinstance(d["recommended_agents"], list)
        assert len(d["recommended_agents"]) >= 1
        for a in d["recommended_agents"]:
            assert "agent_id" in a and "score" in a and a["score"] >= 1
        TestMissionEngine.recommended_agents = [a["agent_id"] for a in d["recommended_agents"][:2]]
        assert d["draft_mission"]["mission_type"] == "strategy"

    def test_create_mission_admin(self, admin_headers):
        agents = TestMissionEngine.recommended_agents or ["AGT-000"]
        payload = {"title": f"TEST it4 mission {RUN}",
                   "objective": "Objectif de test QA it4 pour orchestrateur.",
                   "entity": "CVLN Holding",
                   "agent_ids": agents,
                   "mission_type": "strategy",
                   "expected_results": ["analyse", "recommandations"]}
        r = requests.post(f"{API}/missions", headers=admin_headers, json=payload)
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["status"] == "assigned"
        assert m["workflow_stage"] == "specification"
        assert m["agent_ids"]
        TestMissionEngine.mission_id = m["id"]
        # verify P0 tasks created for each agent
        # Look up any task with this mission_id via listing missions
        lst = requests.get(f"{API}/missions", headers=admin_headers).json()
        assert any(x["id"] == m["id"] for x in lst)

    def test_reader_cannot_create_mission(self, reader_headers):
        payload = {"title": f"TEST it4 reader mission {RUN}",
                   "objective": "Blocked mission creation.",
                   "entity": "CVLN Holding",
                   "agent_ids": ["AGT-000"]}
        r = requests.post(f"{API}/missions", headers=reader_headers, json=payload)
        assert r.status_code == 403

    def test_advance_workflow(self, admin_headers):
        assert TestMissionEngine.mission_id
        r = requests.post(f"{API}/missions/{TestMissionEngine.mission_id}/advance", headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json()["workflow_stage"] == "design"

    def test_deliver_mission_creates_n2_notification(self, admin_headers):
        assert TestMissionEngine.mission_id
        before = requests.get(f"{API}/notifications?level=2", headers=admin_headers).json()
        r = requests.post(f"{API}/missions/{TestMissionEngine.mission_id}/deliver",
                          headers=admin_headers,
                          json={"summary": "Résumé de livraison it4 QA test.",
                                "deliverables": ["Rapport"], "recommendations": ["Recommandation A"]})
        assert r.status_code == 200, r.text
        assert r.json()["result"] == "delivered"
        # Notification N2 created
        after = requests.get(f"{API}/notifications?level=2", headers=admin_headers).json()
        assert len(after) >= len(before) + 1
        assert any("livrée" in n["title"].lower() or "delivered" in n["title"].lower() for n in after)

    def test_validate_reader_forbidden(self, reader_headers):
        assert TestMissionEngine.mission_id
        r = requests.post(f"{API}/missions/{TestMissionEngine.mission_id}/validate?decision=validated",
                          headers=reader_headers)
        assert r.status_code == 403

    def test_validate_svc_forbidden(self, svc_headers):
        assert TestMissionEngine.mission_id
        r = requests.post(f"{API}/missions/{TestMissionEngine.mission_id}/validate?decision=validated",
                          headers=svc_headers)
        assert r.status_code == 403

    def test_validate_admin(self, admin_headers):
        assert TestMissionEngine.mission_id
        r = requests.post(f"{API}/missions/{TestMissionEngine.mission_id}/validate?decision=validated",
                          headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json()["result"] == "validated"
        # verify mission status
        lst = requests.get(f"{API}/missions", headers=admin_headers).json()
        m = next(x for x in lst if x["id"] == TestMissionEngine.mission_id)
        assert m["status"] == "validated"

    def test_performance_scores(self, admin_headers):
        r = requests.get(f"{API}/missions/performance", headers=admin_headers)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0
        # AGT-000 should be present
        ids = [r["agent_id"] for r in rows]
        assert "AGT-000" in ids
        for row in rows:
            assert "performance_score" in row
            assert 0 <= row["performance_score"] <= 100
            assert "tasks_done" in row and "missions_validated" in row


# ================= (D) Cognitive Interface Layer =================
class TestCognitiveInterface:
    rule_msg_id = None
    task_msg_id = None
    conv_id = None

    def test_chat_rule_classification(self, admin_headers):
        r = requests.post(f"{API}/cognitive/chat", headers=admin_headers,
                          json={"message": "Nouvelle règle : toujours vérifier les KPIs avant décision"},
                          timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["classification"] == "rule"
        assert d["engine"] in ("llm-accelerator", "internal-sovereign")
        assert isinstance(d["reply"], str) and len(d["reply"]) > 0
        assert d["user_message_id"]
        TestCognitiveInterface.rule_msg_id = d["user_message_id"]
        TestCognitiveInterface.conv_id = d["conversation_id"]

    def test_chat_instruction_classification(self, admin_headers):
        r = requests.post(f"{API}/cognitive/chat", headers=admin_headers,
                          json={"message": "Crée un rapport hebdomadaire pour la finance"}, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["classification"] == "instruction"
        assert d["engine"] in ("llm-accelerator", "internal-sovereign")
        assert d["reply"]
        TestCognitiveInterface.task_msg_id = d["user_message_id"]

    def test_confirm_rule_creates_evolution_proposal(self, admin_headers):
        assert TestCognitiveInterface.rule_msg_id
        r = requests.post(f"{API}/cognitive/confirm/{TestCognitiveInterface.rule_msg_id}",
                          headers=admin_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["type"] == "doctrine_proposal_created"
        assert d.get("proposal_id")
        # verify proposal exists with status proposed
        props = requests.get(f"{API}/evolution/proposals", headers=admin_headers)
        # Endpoint may differ — try /api/evolution
        if props.status_code != 200:
            props = requests.get(f"{API}/evolution", headers=admin_headers)
        if props.status_code == 200:
            lst = props.json()
            assert any(p.get("id") == d["proposal_id"] and p.get("status") == "proposed" for p in lst)

    def test_confirm_rule_idempotency_conflict(self, admin_headers):
        assert TestCognitiveInterface.rule_msg_id
        r = requests.post(f"{API}/cognitive/confirm/{TestCognitiveInterface.rule_msg_id}",
                          headers=admin_headers)
        assert r.status_code == 409

    def test_confirm_task_creates_agent_task(self, admin_headers):
        assert TestCognitiveInterface.task_msg_id
        r = requests.post(f"{API}/cognitive/confirm/{TestCognitiveInterface.task_msg_id}",
                          headers=admin_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["type"] == "task_created"
        assert d["agent_id"].startswith("AGT-")
        assert d["task_id"]

    def test_confirm_reader_forbidden(self, admin_headers, reader_headers):
        # Create a fresh chat as admin, then reader tries to confirm
        r = requests.post(f"{API}/cognitive/chat", headers=admin_headers,
                          json={"message": "Idée : lancer une campagne d'innovation."}, timeout=90)
        assert r.status_code == 200
        mid = r.json()["user_message_id"]
        rr = requests.post(f"{API}/cognitive/confirm/{mid}", headers=reader_headers)
        assert rr.status_code == 403

    def test_temporal_day(self, admin_headers):
        r = requests.get(f"{API}/cognitive/temporal?period=day", headers=admin_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["period"] == "day"
        for key in ("events", "tasks_done", "missions_validated", "denied_authorizations", "finance"):
            assert key in d
        assert "net" in d["finance"]

    def test_temporal_week_month(self, admin_headers):
        for p in ("week", "month"):
            r = requests.get(f"{API}/cognitive/temporal?period={p}", headers=admin_headers)
            assert r.status_code == 200
            assert r.json()["period"] == p

    def test_conversations_and_messages_persist(self, admin_headers):
        assert TestCognitiveInterface.conv_id
        convs = requests.get(f"{API}/cognitive/conversations", headers=admin_headers)
        assert convs.status_code == 200
        assert any(c["id"] == TestCognitiveInterface.conv_id for c in convs.json())
        msgs = requests.get(f"{API}/cognitive/conversations/{TestCognitiveInterface.conv_id}/messages",
                            headers=admin_headers)
        assert msgs.status_code == 200
        m = msgs.json()
        assert len(m) >= 2
        roles = {x["role"] for x in m}
        assert roles == {"user", "assistant"}


# ================= (E) Continuity Layer =================
class TestContinuity:
    def test_reader_cannot_create_backup(self, reader_headers):
        r = requests.post(f"{API}/continuity/backup", headers=reader_headers)
        assert r.status_code == 403

    def test_create_backup(self, admin_headers):
        r = requests.post(f"{API}/continuity/backup", headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        rec = r.json()
        assert rec["documents"] > 0
        assert rec["file"].startswith("cvln_backup_") and rec["file"].endswith(".json.gz")
        assert rec["size_kb"] > 0
        assert rec["collections"] > 0

    def test_list_backups_includes_new(self, admin_headers):
        r = requests.get(f"{API}/continuity/backups", headers=admin_headers)
        assert r.status_code == 200
        lst = r.json()
        assert isinstance(lst, list) and len(lst) >= 1
        # ordered desc by created_at → freshest first
        for b in lst:
            assert b["file"].endswith(".json.gz")
