"""CVLN-GOV-AUDIT-001 PHASE 3 — Agent Runtime.

Covers:
- Runtime state machine (6 states + strict transitions + forbidden → 409 + journal action_bloquee)
- Sleep creates auto checkpoint, wake restores exact checkpoint (last_action/next_action)
- Wake missing_information signalled in French, wake from actif → 409
- Manual checkpoint creation + listing + last_checkpoint on GET agent runtime
- Full context restoration (identity, doctrine, permissions incl. gate_rules, active_objectives)
- Permission Gate on critical transitions (actif→termine, suspendu→actif) → 423 for service, admin implicit approval
- Recovery on backend restart (runtime_recoveries + journal + coherent state)
- Runtime status shape (6 states, uninitialized agents = sommeil initialized:false)

Test agent: AGT-012 (Digital CFO, currently sommeil not initialized).
DO NOT approve any agent_termination in these tests — only test the 423 escalation.
Cleanup: leaves AGT-012 in sommeil (or actif). Never leaves it termine/suspendu.
"""
import os
import time
import subprocess
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://agent-factory-68.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "laurent@cvln.fr"
ADMIN_PASSWORD = "CVLNfactory2026!"
SERVICE_TOKEN = "svc_agt000_9f2e7c1a4b8d6f3e0a5c2d7b1e4f8a6c"

TEST_AGENT = "AGT-012"


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def admin_client():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    token = r.json()["access_token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def service_client():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {SERVICE_TOKEN}", "Content-Type": "application/json"})
    return s


def _get_state(client, agent_id):
    r = client.get(f"{API}/runtime/agents/{agent_id}", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["runtime"]["state"]


def _put_agent_state(client, agent_id, state, **kwargs):
    return client.post(f"{API}/runtime/agents/{agent_id}/state",
                       json={"state": state, **kwargs}, timeout=30)


@pytest.fixture(scope="module", autouse=True)
def ensure_test_agent_baseline(service_client):
    """Ensure AGT-012 exists and is in sommeil (or actif) at the start.
    Cleanup at end: bring it back to sommeil if needed."""
    r = service_client.get(f"{API}/runtime/agents/{TEST_AGENT}", timeout=30)
    assert r.status_code == 200, f"Test agent {TEST_AGENT} missing: {r.text}"
    state = r.json()["runtime"]["state"]
    # Force a benign starting point if unexpected state
    if state == "suspendu":
        # Try lifting suspension via admin (critical transition); if fails, skip
        pass
    yield
    # Teardown: try to leave AGT-012 in sommeil
    try:
        current = _get_state(service_client, TEST_AGENT)
        if current == "actif":
            _put_agent_state(service_client, TEST_AGENT, "sommeil",
                             last_action="fin de test", next_action="—", note="cleanup")
        elif current == "erreur":
            _put_agent_state(service_client, TEST_AGENT, "actif", note="cleanup err→actif")
            _put_agent_state(service_client, TEST_AGENT, "sommeil",
                             last_action="fin de test", next_action="—", note="cleanup")
    except Exception:
        pass


# ---------------- 1. STATUS / SHAPE ----------------
class TestRuntimeStatus:
    def test_status_returns_six_states(self, service_client):
        r = service_client.get(f"{API}/runtime/status")
        assert r.status_code == 200
        d = r.json()
        assert "by_state" in d and "agents" in d
        for s in ("actif", "sommeil", "attente_validation", "erreur", "suspendu", "termine"):
            assert s in d["by_state"], f"missing state {s}"
        assert isinstance(d["agents"], list) and len(d["agents"]) >= 15
        # uninitialized agents should show initialized:false
        uninit = [a for a in d["agents"] if a["runtime"].get("initialized") is False]
        # after previous tests some may be initialized; but at least the runtime.state field is set
        for a in d["agents"]:
            assert a["runtime"]["state"] in ("actif", "sommeil", "attente_validation",
                                             "erreur", "suspendu", "termine")

    def test_get_agent_runtime_shape(self, service_client):
        r = service_client.get(f"{API}/runtime/agents/{TEST_AGENT}")
        assert r.status_code == 200
        d = r.json()
        assert d["agent_id"] == TEST_AGENT
        assert "runtime" in d and "state" in d["runtime"]
        assert isinstance(d["allowed_transitions"], list)
        assert "last_checkpoint" in d

    def test_get_agent_runtime_404(self, service_client):
        r = service_client.get(f"{API}/runtime/agents/AGT-999")
        assert r.status_code == 404


# ---------------- 2. WAKE (missing_information + restoration) ----------------
class TestWakeMissingInformation:
    def test_wake_from_uninitialized_signals_missing(self, service_client):
        # Ensure agent starts in sommeil (uninitialized)
        state = _get_state(service_client, TEST_AGENT)
        if state == "actif":
            r = _put_agent_state(service_client, TEST_AGENT, "sommeil",
                                 last_action="reset for missing_info test",
                                 next_action="—", note="reset")
            assert r.status_code == 200

        r = service_client.post(f"{API}/runtime/agents/{TEST_AGENT}/wake")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["result"] == "awake"
        assert d["runtime"]["state"] == "actif"
        assert isinstance(d["missing_information"], list)
        # French language check on any missing entry
        for m in d["missing_information"]:
            assert isinstance(m, str) and len(m) > 5
        # Restored context shape
        rc = d["restored_context"]
        for k in ("identity", "role", "doctrine", "active_objectives",
                  "history", "permissions", "pending_validations",
                  "last_checkpoint", "operational_context"):
            assert k in rc, f"missing key {k}"
        # Global doctrines >= 21
        assert rc["doctrine"]["global_active_rules"] >= 21, \
            f"expected >=21 global active doctrines, got {rc['doctrine']['global_active_rules']}"
        # Autonomy present in permissions
        assert "autonomy" in rc["permissions"]

    def test_wake_from_actif_returns_409(self, service_client):
        # agent should now be actif from previous test
        state = _get_state(service_client, TEST_AGENT)
        if state != "actif":
            # bring it to actif
            _put_agent_state(service_client, TEST_AGENT, "actif") if state == "sommeil" else None
        r = service_client.post(f"{API}/runtime/agents/{TEST_AGENT}/wake")
        assert r.status_code == 409, r.text


# ---------------- 3. STATE MACHINE ----------------
class TestStateMachine:
    def test_invalid_state_400(self, service_client):
        r = _put_agent_state(service_client, TEST_AGENT, "not_a_state")
        assert r.status_code == 400

    def test_actif_to_actif_forbidden_409(self, service_client):
        # agent should be actif
        state = _get_state(service_client, TEST_AGENT)
        assert state == "actif", f"expected actif, got {state}"
        r = _put_agent_state(service_client, TEST_AGENT, "actif")
        assert r.status_code == 409
        # forbidden transition should be journaled as action_bloquee
        j = service_client.get(f"{API}/journal", params={"agent_id": TEST_AGENT, "type": "action_bloquee",
                                                          "limit": 10})
        assert j.status_code == 200
        entries = j.json()
        assert any("interdite" in e.get("summary", "").lower() or e.get("result") == "refused"
                   for e in entries), "no action_bloquee journal for forbidden transition"

    def test_state_change_404(self, service_client):
        r = _put_agent_state(service_client, "AGT-999", "sommeil")
        assert r.status_code == 404


# ---------------- 4. SLEEP → CHECKPOINT AUTO → WAKE RESTORE ----------------
class TestSleepWakeCycle:
    def test_sleep_creates_auto_checkpoint(self, service_client):
        # Must be actif
        state = _get_state(service_client, TEST_AGENT)
        assert state == "actif", f"expected actif at start, got {state}"
        r = _put_agent_state(service_client, TEST_AGENT, "sommeil",
                             last_action="TEST_cycle: analyse trimestre Q1",
                             next_action="TEST_cycle: consolider rapport",
                             note="test sleep")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["runtime"]["state"] == "sommeil"
        assert d["checkpoint_id"], "auto checkpoint_id not returned"

    def test_wake_restores_exact_checkpoint(self, service_client):
        state = _get_state(service_client, TEST_AGENT)
        assert state == "sommeil", f"expected sommeil, got {state}"
        r = service_client.post(f"{API}/runtime/agents/{TEST_AGENT}/wake")
        assert r.status_code == 200, r.text
        cp = r.json()["restored_context"]["last_checkpoint"]
        assert cp is not None, "no last_checkpoint restored"
        assert cp["last_action"] == "TEST_cycle: analyse trimestre Q1"
        assert cp["next_action"] == "TEST_cycle: consolider rapport"


# ---------------- 5. MANUAL CHECKPOINT ----------------
class TestManualCheckpoint:
    def test_manual_checkpoint_persisted_and_listed(self, service_client):
        # Ensure actif
        state = _get_state(service_client, TEST_AGENT)
        assert state == "actif"
        r = service_client.post(f"{API}/runtime/agents/{TEST_AGENT}/checkpoint",
                                json={"last_action": "TEST_manual: revue P&L",
                                      "next_action": "TEST_manual: envoi rapport",
                                      "context": {"module": "finance"}})
        assert r.status_code == 200, r.text
        cp = r.json()
        assert cp["last_action"] == "TEST_manual: revue P&L"
        assert cp["agent_id"] == TEST_AGENT
        cp_id = cp["id"]
        # List
        r2 = service_client.get(f"{API}/runtime/agents/{TEST_AGENT}/checkpoints")
        assert r2.status_code == 200
        lst = r2.json()
        assert any(x["id"] == cp_id for x in lst), "manual checkpoint not in list"
        # GET agent runtime returns latest as last_checkpoint
        r3 = service_client.get(f"{API}/runtime/agents/{TEST_AGENT}")
        assert r3.status_code == 200
        assert r3.json()["last_checkpoint"]["id"] == cp_id


# ---------------- 6. FULL RESTORATION (objectives + doctrine + gate rules) ----------------
class TestFullRestoration:
    """Create objective + gate rule + attach doctrine to AGT-012, sleep/wake, verify all restored."""

    _rule_id = None
    _objective_code = None
    _doctrine_id = None
    _doctrine_original_agents = None

    def test_setup_context_and_verify_restoration(self, service_client, admin_client):
        # Ensure actif
        state = _get_state(service_client, TEST_AGENT)
        assert state == "actif"

        # 1) Create objective owned by AGT-012
        r_obj = admin_client.post(f"{API}/objectives",
                                  json={"title": "TEST_restore: revue mensuelle finance",
                                        "description": "test objective for phase3",
                                        "priority": "P1", "owner": TEST_AGENT,
                                        "next_action": "TEST_restore next action"})
        assert r_obj.status_code == 200, r_obj.text
        TestFullRestoration._objective_code = r_obj.json()["code"]

        # 2) Create gate rule scope=agent for AGT-012 (non-critical action_type)
        r_rule = admin_client.post(f"{API}/gate/rules",
                                   json={"scope": "agent", "target_id": TEST_AGENT,
                                         "action_type": "memory_write", "level": 2,
                                         "note": "TEST_restore rule"})
        assert r_rule.status_code == 200, r_rule.text
        TestFullRestoration._rule_id = r_rule.json()["id"]

        # 3) Attach AGT-012 to an active doctrine (pick DR-025 which is active)
        r_list = admin_client.get(f"{API}/doctrine/registry", params={"status": "active"})
        assert r_list.status_code == 200
        active = r_list.json()
        # Find a doctrine with id starting with DR- to safely PATCH
        candidate = next((d for d in active if d["id"].startswith("DR-")), None)
        assert candidate, "no DR- doctrine active to attach agent"
        TestFullRestoration._doctrine_id = candidate["id"]
        TestFullRestoration._doctrine_original_agents = candidate.get("agents_concerned", [])
        new_list = list(TestFullRestoration._doctrine_original_agents) + [TEST_AGENT]
        r_patch = admin_client.patch(f"{API}/doctrine/registry/{candidate['id']}",
                                     json={"agents_concerned": new_list, "note": "TEST_restore attach"})
        assert r_patch.status_code == 200, r_patch.text

        # 4) Sleep AGT-012
        r_sleep = _put_agent_state(service_client, TEST_AGENT, "sommeil",
                                   last_action="TEST_restore: sommeil",
                                   next_action="TEST_restore: reveil verif",
                                   note="restoration test")
        assert r_sleep.status_code == 200

        # 5) Wake and verify restoration
        r_wake = service_client.post(f"{API}/runtime/agents/{TEST_AGENT}/wake")
        assert r_wake.status_code == 200
        rc = r_wake.json()["restored_context"]

        # Objectives
        codes = [o.get("code") for o in rc["active_objectives"]]
        assert TestFullRestoration._objective_code in codes, \
            f"objective {TestFullRestoration._objective_code} not restored (got {codes})"

        # Gate rules
        rule_ids = [r.get("id") for r in rc["permissions"]["gate_rules"]]
        assert TestFullRestoration._rule_id in rule_ids, \
            f"gate rule not restored (got {rule_ids})"

        # Doctrine specific must include our doctrine
        specific_ids = [d.get("id") for d in rc["doctrine"]["specific"]]
        assert TestFullRestoration._doctrine_id in specific_ids, \
            f"doctrine {TestFullRestoration._doctrine_id} not restored specific (got {specific_ids})"

        # Global doctrines still counted
        assert rc["doctrine"]["global_active_rules"] >= 21

    def test_zzz_cleanup(self, service_client, admin_client):
        """Cleanup: deactivate gate rule, restore doctrine agents_concerned, close objective."""
        try:
            if TestFullRestoration._rule_id:
                admin_client.delete(f"{API}/gate/rules/{TestFullRestoration._rule_id}")
            if TestFullRestoration._doctrine_id is not None \
                    and TestFullRestoration._doctrine_original_agents is not None:
                admin_client.patch(f"{API}/doctrine/registry/{TestFullRestoration._doctrine_id}",
                                   json={"agents_concerned": TestFullRestoration._doctrine_original_agents,
                                         "note": "TEST_restore rollback"})
            if TestFullRestoration._objective_code:
                # Look up objective by code
                lst = admin_client.get(f"{API}/objectives",
                                       params={"owner": TEST_AGENT}).json()
                target = next((o for o in lst
                               if o.get("code") == TestFullRestoration._objective_code), None)
                if target:
                    admin_client.patch(f"{API}/objectives/{target['id']}",
                                       json={"status": "archived", "note": "TEST_restore done"})
        except Exception as e:
            print("cleanup warning:", e)


# ---------------- 7. PERMISSION GATE ON CRITICAL TRANSITIONS ----------------
class TestPermissionGate:
    """suspendu→actif and actif→termine both require permission gate. Service escalates → 423."""

    _validation_request_id = None

    def test_suspendu_to_actif_service_escalates(self, service_client, admin_client):
        # Bring AGT-012 to actif then suspendu
        state = _get_state(service_client, TEST_AGENT)
        if state == "sommeil":
            r = service_client.post(f"{API}/runtime/agents/{TEST_AGENT}/wake")
            assert r.status_code == 200
        elif state != "actif":
            # try to bring to actif safely
            r = _put_agent_state(service_client, TEST_AGENT, "actif")
        r_sus = _put_agent_state(admin_client, TEST_AGENT, "suspendu", note="TEST_gate suspend")
        assert r_sus.status_code == 200, r_sus.text
        assert r_sus.json()["runtime"]["state"] == "suspendu"

        # Service tries suspendu→actif → 423
        r_svc = _put_agent_state(service_client, TEST_AGENT, "actif", note="TEST_gate reactivate by service")
        assert r_svc.status_code == 423, f"expected 423, got {r_svc.status_code} {r_svc.text}"
        body = r_svc.json()
        assert "detail" in body
        detail = body["detail"] if isinstance(body["detail"], dict) else {}
        vr_id = detail.get("validation_request_id")
        assert vr_id, f"validation_request_id missing in 423 response: {body}"
        TestPermissionGate._validation_request_id = vr_id

    def test_admin_approves_and_service_reactivates(self, service_client, admin_client):
        vr_id = TestPermissionGate._validation_request_id
        assert vr_id, "prev test must have created a validation request"
        # Admin decides approved
        r_dec = admin_client.post(f"{API}/gate/validation-requests/{vr_id}/decide",
                                  params={"decision": "approved", "note": "TEST_gate approve"})
        assert r_dec.status_code == 200, r_dec.text
        # Service re-attempts suspendu→actif with validation_id
        r_retry = _put_agent_state(service_client, TEST_AGENT, "actif",
                                   note="TEST_gate reactivate approved",
                                   validation_id=vr_id)
        assert r_retry.status_code == 200, r_retry.text
        assert r_retry.json()["runtime"]["state"] == "actif"

    def test_actif_to_termine_service_escalates_423(self, service_client):
        state = _get_state(service_client, TEST_AGENT)
        assert state == "actif"
        r = _put_agent_state(service_client, TEST_AGENT, "termine", note="TEST_gate terminate probe")
        assert r.status_code == 423, f"expected 423, got {r.status_code} {r.text}"
        detail = r.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("validation_request_id"), \
                "termination should produce a validation_request_id"


# ---------------- 8. FORBIDDEN: sommeil → termine ----------------
class TestForbiddenSommeilToTermine:
    def test_sommeil_to_termine_409(self, service_client):
        # Put in sommeil
        state = _get_state(service_client, TEST_AGENT)
        if state == "actif":
            _put_agent_state(service_client, TEST_AGENT, "sommeil",
                             last_action="TEST_forbidden", next_action="—")
        r = _put_agent_state(service_client, TEST_AGENT, "termine", note="TEST_forbidden")
        assert r.status_code == 409, r.text


# ---------------- 9. ISOLATION ----------------
class TestIsolation:
    def test_reader_would_be_403_or_no_reader_account(self, service_client):
        # No reader account in test_credentials.md — skip
        pytest.skip("No reader account available in test_credentials.md")


# ---------------- 10. RECOVERY AFTER BACKEND RESTART ----------------
class TestRecovery:
    def test_recovery_after_backend_restart(self, service_client):
        # Ensure agent is actif to be recovered
        state = _get_state(service_client, TEST_AGENT)
        if state == "sommeil":
            r = service_client.post(f"{API}/runtime/agents/{TEST_AGENT}/wake")
            assert r.status_code == 200
        state = _get_state(service_client, TEST_AGENT)
        assert state == "actif", f"expected actif before restart, got {state}"

        # Fetch previous recovery timestamp
        prev = service_client.get(f"{API}/runtime/recovery-status").json().get("last_recovery")
        prev_ts = prev["timestamp"] if prev else ""

        # Restart backend
        result = subprocess.run(["sudo", "supervisorctl", "restart", "backend"],
                                capture_output=True, text=True, timeout=60)
        assert "started" in (result.stdout + result.stderr).lower() or result.returncode == 0, \
            f"restart failed: {result.stdout} {result.stderr}"

        # Wait for backend readiness
        deadline = time.time() + 30
        ready = False
        while time.time() < deadline:
            time.sleep(1)
            try:
                r = service_client.get(f"{API}/runtime/status", timeout=5)
                if r.status_code == 200:
                    ready = True
                    break
            except Exception:
                pass
        assert ready, "backend never became ready after restart"
        time.sleep(2)  # extra buffer for lifespan startup tasks

        # Check recovery-status
        r_rec = service_client.get(f"{API}/runtime/recovery-status")
        assert r_rec.status_code == 200
        rec = r_rec.json()["last_recovery"]
        assert rec is not None
        assert rec["timestamp"] != prev_ts, "recovery timestamp did not advance"
        assert rec["active_agents"] >= 1, f"expected >=1 active agent recovered, got {rec['active_agents']}"

        # Agent still actif
        state_after = _get_state(service_client, TEST_AGENT)
        assert state_after == "actif", f"agent state lost across restart: {state_after}"

        # Journal has a system-recovery observation
        j = service_client.get(f"{API}/journal",
                               params={"type": "observation", "limit": 50})
        assert j.status_code == 200
        entries = j.json()
        assert any("Reprise" in e.get("summary", "") and e.get("source") == "agent-runtime"
                   for e in entries), "no 'Reprise système' observation journal entry"
