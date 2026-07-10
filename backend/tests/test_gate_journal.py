"""CVLN-GOV-PHASE1-001 — Permission Gate v2 + Activity Journal v2 backend tests.

Coverage:
- GET /api/gate/levels: 6 levels + critical_actions + default_action_levels
- POST /api/gate/check for levels 1-4 (service AGT-000) → allowed + journal entry
- POST /api/gate/check for critical action (service) → escalation + validation_request pending + journal action_bloquee + notification
- Escalation → admin decide approve → journal decision_humaine → re-check with validation_id → allowed + journal action_executee
- Escalation with rejected decision → re-check must remain blocked (new escalation)
- Admin direct check on critical action → allowed (implicit) + journal decision_humaine + action_executee
- Rule create/delete: agent scope forbidden → check blocked; delete → allowed. Critical action rule with level<5 → 400. Non-admin POST rule → 403
- GET /api/gate/refusals, GET /api/journal/types (8), GET /api/journal?type=..., GET /api/journal/unified (3 origins)
- Mission integration: deliver → journal action_executee; validate → journal decision_humaine
- Non-regression: POST /api/notifications/test → 200 {pushed:false, push_error}
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://agent-factory-68.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "laurent@cvln.fr"
ADMIN_PASSWORD = "CVLNfactory2026!"
SERVICE_TOKEN = "svc_agt000_9f2e7c1a4b8d6f3e0a5c2d7b1e4f8a6c"


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_client(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def service_client():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {SERVICE_TOKEN}", "Content-Type": "application/json"})
    return s


# ---------------- Gate levels & basic checks ----------------
class TestGateLevels:
    def test_levels(self, service_client):
        r = service_client.get(f"{API}/gate/levels", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert set(d["levels"].keys()) == {"1", "2", "3", "4", "5", "6"}
        assert d["levels"]["1"]["label"] == "observe"
        assert d["levels"]["6"]["label"] == "forbidden"
        expected_critical = {"expense", "external_publication", "governance_change",
                             "data_deletion", "permission_change", "critical_production_activation"}
        assert set(d["critical_actions"]) == expected_critical
        assert d["default_action_levels"]["observe"] == 1
        assert d["default_action_levels"]["analyze"] == 2
        assert d["default_action_levels"]["propose"] == 3
        assert d["default_action_levels"]["prepare"] == 4
        assert d["default_action_levels"]["execute"] == 5
        for a in expected_critical:
            assert d["default_action_levels"][a] == 5


class TestGateCheckLowLevels:
    """POST /api/gate/check by AGT-000 service token for levels 1-4 → allowed + journal entry."""

    @pytest.mark.parametrize("action,journal_type", [
        ("observe", "observation"),
        ("analyze", "analyse"),
        ("propose", "proposition"),
        ("prepare", "proposition"),
    ])
    def test_check_allowed_creates_journal(self, service_client, action, journal_type):
        summary = f"TEST_gate_{action}_{int(time.time() * 1000)}"
        r = service_client.post(f"{API}/gate/check",
                                json={"action_type": action, "summary": summary}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["allowed"] is True
        assert d["decision"] == action
        # Journal entry created of correct type
        j = service_client.get(f"{API}/journal?type={journal_type}&limit=200", timeout=30)
        assert j.status_code == 200
        summaries = [e["summary"] for e in j.json()]
        assert summary in summaries, f"Journal entry not found for {action} → type {journal_type}"


# ---------------- Critical action escalation ----------------
class TestCriticalEscalation:
    @pytest.fixture(scope="class")
    def escalated(self, service_client):
        summary = f"TEST_expense_escalation_{int(time.time() * 1000)}"
        r = service_client.post(f"{API}/gate/check",
                                json={"action_type": "expense", "summary": summary,
                                      "evidence": {"amount": 42}}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["allowed"] is False
        assert d["decision"] == "pending_human_validation"
        assert "validation_request_id" in d
        return {"summary": summary, "validation_id": d["validation_request_id"]}

    def test_validation_request_pending(self, service_client, escalated):
        r = service_client.get(f"{API}/gate/validation-requests?status=pending", timeout=30)
        assert r.status_code == 200
        ids = [v["id"] for v in r.json()]
        assert escalated["validation_id"] in ids

    def test_journal_action_bloquee_escalated(self, service_client, escalated):
        r = service_client.get(f"{API}/journal?type=action_bloquee&limit=200", timeout=30)
        assert r.status_code == 200
        matches = [e for e in r.json()
                   if escalated["summary"] in (e.get("summary") or "") and e.get("result") == "escalated"]
        assert matches, "No journal entry type=action_bloquee result=escalated for the escalated request"

    def test_notification_level2_persisted(self, admin_client, escalated):
        r = admin_client.get(f"{API}/notifications?limit=200", timeout=30)
        assert r.status_code == 200
        notifs = r.json()
        rel = [n for n in notifs if n.get("meta", {}).get("validation_request_id") == escalated["validation_id"]]
        assert rel, "No notification persisted with the validation_request_id in meta"
        assert rel[0]["level"] == 2

    def test_approve_and_recheck_executes(self, admin_client, service_client, escalated):
        vid = escalated["validation_id"]
        # Approve
        r = admin_client.post(f"{API}/gate/validation-requests/{vid}/decide?decision=approved", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["result"] == "approved"
        # Journal decision_humaine
        j = admin_client.get(f"{API}/journal?type=decision_humaine&limit=200", timeout=30)
        assert j.status_code == 200
        assert any(e.get("evidence", {}).get("validation_request_id") == vid for e in j.json()), \
            "No decision_humaine journal entry with validation_request_id"
        # Re-check with validation_id → allowed
        summary2 = f"TEST_expense_executed_{int(time.time() * 1000)}"
        r2 = service_client.post(f"{API}/gate/check",
                                 json={"action_type": "expense", "summary": summary2,
                                       "validation_id": vid}, timeout=30)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["allowed"] is True
        assert d2["decision"] == "execute_after_validation"
        # Journal action_executee
        j2 = service_client.get(f"{API}/journal?type=action_executee&limit=200", timeout=30)
        assert any(summary2 == e.get("summary") for e in j2.json()), \
            "No action_executee journal entry after approved re-check"


class TestRejectedEscalation:
    def test_reject_and_recheck_still_blocked(self, service_client, admin_client):
        # Create a fresh escalation
        summary = f"TEST_expense_reject_{int(time.time() * 1000)}"
        r = service_client.post(f"{API}/gate/check",
                                json={"action_type": "expense", "summary": summary}, timeout=30)
        assert r.status_code == 200
        vid = r.json()["validation_request_id"]
        # Reject
        rj = admin_client.post(f"{API}/gate/validation-requests/{vid}/decide?decision=rejected", timeout=30)
        assert rj.status_code == 200
        assert rj.json()["result"] == "rejected"
        # Re-check with same validation_id → must remain blocked (new escalation)
        r2 = service_client.post(f"{API}/gate/check",
                                 json={"action_type": "expense", "summary": summary + "_retry",
                                       "validation_id": vid}, timeout=30)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["allowed"] is False
        assert d2["decision"] == "pending_human_validation"
        assert d2["validation_request_id"] != vid, "A new escalation must be created for a rejected validation_id"


class TestAdminDirectCritical:
    def test_admin_critical_allowed_with_journal(self, admin_client):
        summary = f"TEST_admin_expense_direct_{int(time.time() * 1000)}"
        r = admin_client.post(f"{API}/gate/check",
                              json={"action_type": "expense", "summary": summary}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["allowed"] is True
        assert d["decision"] == "execute_after_validation"
        # Both decision_humaine (implicit) and action_executee must exist
        j_dec = admin_client.get(f"{API}/journal?type=decision_humaine&limit=200", timeout=30).json()
        j_exec = admin_client.get(f"{API}/journal?type=action_executee&limit=200", timeout=30).json()
        assert any(summary in (e.get("summary") or "") for e in j_dec), "missing decision_humaine implicit"
        assert any(e.get("summary") == summary for e in j_exec), "missing action_executee for admin direct critical"


# ---------------- Rules ----------------
class TestRules:
    def test_agent_rule_forbid_and_delete(self, admin_client, service_client):
        # Create agent rule: AGT-011 analyze level=6
        payload = {"scope": "agent", "target_id": "AGT-011", "action_type": "analyze",
                   "level": 6, "note": "TEST_rule_forbid"}
        r = admin_client.post(f"{API}/gate/rules", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        rule_id = r.json()["id"]
        # Check analyze on AGT-011 → forbidden
        summary = f"TEST_analyze_forbidden_{int(time.time() * 1000)}"
        r2 = service_client.post(f"{API}/gate/check",
                                 json={"action_type": "analyze", "summary": summary,
                                       "agent_id": "AGT-011"}, timeout=30)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["allowed"] is False
        assert d2["decision"] == "forbidden"
        # Journal action_bloquee entry
        j = service_client.get(f"{API}/journal?type=action_bloquee&limit=200", timeout=30).json()
        assert any(summary in (e.get("summary") or "") for e in j)
        # Delete rule → re-check allowed
        rd = admin_client.delete(f"{API}/gate/rules/{rule_id}", timeout=30)
        assert rd.status_code == 200
        r3 = service_client.post(f"{API}/gate/check",
                                 json={"action_type": "analyze",
                                       "summary": f"TEST_analyze_after_delete_{int(time.time() * 1000)}",
                                       "agent_id": "AGT-011"}, timeout=30)
        assert r3.status_code == 200
        assert r3.json()["allowed"] is True

    def test_critical_action_rule_level_below_5_forbidden(self, admin_client):
        r = admin_client.post(f"{API}/gate/rules",
                              json={"scope": "action_type", "target_id": None,
                                    "action_type": "expense", "level": 3,
                                    "note": "TEST_should_fail"}, timeout=30)
        assert r.status_code == 400, f"Expected 400 for critical action level<5, got {r.status_code}"

    def test_non_admin_cannot_create_rule(self, service_client):
        r = service_client.post(f"{API}/gate/rules",
                                json={"scope": "action_type", "target_id": None,
                                      "action_type": "analyze", "level": 4,
                                      "note": "TEST_forbidden_service"}, timeout=30)
        assert r.status_code == 403, f"Expected 403 for service token, got {r.status_code}: {r.text}"


# ---------------- Read endpoints ----------------
class TestReadEndpoints:
    def test_refusals(self, service_client):
        r = service_client.get(f"{API}/gate/refusals", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert all(e["type"] == "action_bloquee" for e in rows)

    def test_journal_types_8(self, service_client):
        r = service_client.get(f"{API}/journal/types", timeout=30)
        assert r.status_code == 200
        types = r.json()
        expected = {"observation", "analyse", "proposition", "decision_humaine",
                    "action_executee", "action_bloquee", "erreur", "cloture"}
        assert set(types) == expected
        assert len(types) == 8

    def test_journal_filter_by_type(self, service_client):
        r = service_client.get(f"{API}/journal?type=decision_humaine&limit=50", timeout=30)
        assert r.status_code == 200
        for e in r.json():
            assert e["type"] == "decision_humaine"

    def test_journal_unified_three_origins(self, service_client):
        r = service_client.get(f"{API}/journal/unified?limit=300", timeout=30)
        assert r.status_code == 200
        entries = r.json()
        origins = {e.get("origin") for e in entries}
        # At least journal_v2 must be present; audit_logs and events should be present since main agent already validated 3 origins are in DB
        assert "journal_v2" in origins
        assert "audit_logs" in origins, f"audit_logs origin missing (got: {origins})"
        assert "events" in origins, f"events origin missing (got: {origins})"
        # Sort desc by timestamp
        timestamps = [e["timestamp"] for e in entries if e.get("timestamp")]
        assert timestamps == sorted(timestamps, reverse=True)


# ---------------- Mission integration ----------------
class TestMissionJournalHooks:
    @pytest.fixture(scope="class")
    def created_mission(self, admin_client):
        # Find an active agent id
        agents = admin_client.get(f"{API}/registry/agents?limit=5", timeout=30).json()
        assert isinstance(agents, list) and len(agents) > 0, "No agents available for mission test"
        agent_id = agents[0]["id"]
        entity = agents[0].get("entity") or "CVLN Holding"
        payload = {
            "title": f"TEST_mission_{int(time.time())}",
            "objective": "TEST_mission objective long enough to pass validation",
            "entity": entity,
            "agent_ids": [agent_id],
            "autonomy_level": 2,
            "expected_results": ["analyse"],
            "mission_type": "analysis",
            "origin_request": "TEST_",
        }
        r = admin_client.post(f"{API}/missions", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        return r.json()

    def test_deliver_creates_journal(self, admin_client, created_mission):
        mid = created_mission["id"]
        r = admin_client.post(f"{API}/missions/{mid}/deliver",
                              json={"summary": "TEST_delivery summary long enough",
                                    "deliverables": ["doc1"],
                                    "recommendations": ["reco1"]}, timeout=30)
        assert r.status_code == 200, r.text
        j = admin_client.get(f"{API}/journal?type=action_executee&mission_id={mid}&limit=50", timeout=30).json()
        assert any(e.get("mission_id") == mid for e in j), "No action_executee journal for delivered mission"

    def test_validate_creates_journal(self, admin_client, created_mission):
        mid = created_mission["id"]
        r = admin_client.post(f"{API}/missions/{mid}/validate?decision=validated", timeout=30)
        assert r.status_code == 200, r.text
        j = admin_client.get(f"{API}/journal?type=decision_humaine&mission_id={mid}&limit=50", timeout=30).json()
        assert any(e.get("mission_id") == mid for e in j), "No decision_humaine journal for validated mission"


# ---------------- Non-regression ----------------
class TestNonRegression:
    def test_notifications_test_returns_200(self, admin_client):
        r = admin_client.post(f"{API}/notifications/test",
                              json={"message": "TEST_gov_phase1 non-regression"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # push may or may not fail depending on chat_id; but response contract must be 200 + pushed key
        assert "pushed" in d
        # if not pushed, push_error should be present
        if d.get("pushed") is False:
            assert "push_error" in d
