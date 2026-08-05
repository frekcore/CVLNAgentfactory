"""
CVLN Agent Factory - Daily Closing Service (iteration 2)

Order-dependent by design: closure freezes the day.
- Phase A: submissions & authz negatives BEFORE closure
- Phase B: closure + re-closure conflict
- Phase C: read snapshots / states / briefing + submission-after-close conflict
- Phase D: memory scope validation (session/persistent/operational/strategic)
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

RUN = str(int(time.time()))[-6:]


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def svc_headers():
    return {"Authorization": f"Bearer {AGT000_TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def reader_headers(admin_headers):
    email = f"TEST_dc_reader_{RUN}@cvln.fr"
    pwd = "ReaderPass123!"
    c = requests.post(f"{API}/users", headers=admin_headers,
                      json={"email": email, "password": pwd, "name": "TEST DC Reader", "role": "reader"})
    assert c.status_code in (200, 201, 409), c.text
    login = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def operator_headers(admin_headers):
    email = f"TEST_dc_op_{RUN}@cvln.fr"
    pwd = "OpPass123!"
    c = requests.post(f"{API}/users", headers=admin_headers,
                      json={"email": email, "password": pwd, "name": "TEST DC Op", "role": "operator"})
    assert c.status_code in (200, 201, 409), c.text
    login = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}", "Content-Type": "application/json"}


def _sample_report(agent_id, confidence=88):
    return {
        "agent_id": agent_id,
        "mission": "TEST mission validation clôture quotidienne",
        "tasks_done": ["Analyser doctrine", "Vérifier permissions"],
        "results": ["Doctrine conforme"],
        "data_produced": [f"log_{agent_id}.txt"],
        "decisions": ["Confirmer routage Event Bus"],
        "difficulties": [],
        "alerts": [],
        "next_actions": ["Suivre les nouveaux agents en Beta"],
        "confidence": confidence,
        "human_intervention_needed": False,
    }


# =============================================================================
# Phase A — Pre-closure: submissions + role/service isolation
# =============================================================================
class TestPhaseA_Submissions:
    """Submissions before closure. Order matters within the module."""

    @pytest.fixture(autouse=True)
    def skip_if_day_closed(self, admin_headers):
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        r = requests.get(f"{API}/daily/closings/{today}", headers=admin_headers)
        if r.status_code == 200 and r.json().get("status") == "closed":
            pytest.skip(f"day {today} already closed — suite non same-day idempotent (une clôture/jour)")

    def test_a1_admin_submit_agt000(self, admin_headers):
        r = requests.post(f"{API}/daily/reports", headers=admin_headers, json=_sample_report("AGT-000"))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["result"] == "ok"
        assert d["agent_id"] == "AGT-000"
        assert d["date"] and len(d["date"]) == 10

    def test_a2_admin_submit_agt001(self, admin_headers):
        r = requests.post(f"{API}/daily/reports", headers=admin_headers, json=_sample_report("AGT-001", confidence=75))
        assert r.status_code == 200, r.text

    def test_a3_resubmit_same_agent_upserts(self, admin_headers):
        payload = _sample_report("AGT-000", confidence=95)
        payload["mission"] = "TEST mission mise à jour (upsert)"
        r = requests.post(f"{API}/daily/reports", headers=admin_headers, json=payload)
        assert r.status_code == 200, r.text
        # verify GET reflects the upsert
        g = requests.get(f"{API}/daily/reports?agent_id=AGT-000", headers=admin_headers)
        assert g.status_code == 200
        rows = g.json()
        assert len(rows) == 1, f"expected single upserted row, got {len(rows)}"
        assert rows[0]["confidence"] == 95
        assert "upsert" in rows[0]["mission"]

    def test_a4_agent_published_event(self, admin_headers):
        # small delay for event insert
        time.sleep(0.3)
        r = requests.get(f"{API}/events?topic=agent.daily.completed&limit=20", headers=admin_headers)
        assert r.status_code == 200
        topics = [e["topic"] for e in r.json()]
        assert "agent.daily.completed" in topics

    def test_a5_service_identity_can_submit_self(self, svc_headers):
        r = requests.post(f"{API}/daily/reports", headers=svc_headers, json=_sample_report("AGT-000"))
        assert r.status_code == 200, r.text

    def test_a6_service_identity_cannot_submit_other_agent(self, svc_headers, admin_headers):
        r = requests.post(f"{API}/daily/reports", headers=svc_headers, json=_sample_report("AGT-007"))
        assert r.status_code == 403, r.text
        # verify audit logged the deny
        time.sleep(0.3)
        a = requests.get(f"{API}/audit?allowed=false&action=daily_report_submit", headers=admin_headers)
        assert a.status_code == 200
        assert any(l["action"] == "daily_report_submit" for l in a.json()), "denied submit not in audit"

    def test_a7_reader_cannot_submit(self, reader_headers):
        r = requests.post(f"{API}/daily/reports", headers=reader_headers, json=_sample_report("AGT-001"))
        assert r.status_code == 403, r.text

    def test_a8_reader_cannot_close(self, reader_headers):
        r = requests.post(f"{API}/daily/close", headers=reader_headers, json={"note": ""})
        assert r.status_code == 403, r.text

    def test_a9_operator_cannot_close(self, operator_headers):
        # require_registry_writer requires admin (or service token) — operator must be denied
        r = requests.post(f"{API}/daily/close", headers=operator_headers, json={"note": ""})
        assert r.status_code == 403, r.text

    def test_a10_unknown_agent_404(self, admin_headers):
        r = requests.post(f"{API}/daily/reports", headers=admin_headers, json=_sample_report("AGT-999"))
        assert r.status_code == 404, r.text


# =============================================================================
# Phase B — Closure pipeline
# =============================================================================
class TestPhaseB_Closure:
    def test_b1_admin_can_close(self, admin_headers):
        r = requests.post(f"{API}/daily/close", headers=admin_headers, json={"note": "TEST closing iteration 2"})
        if r.status_code == 409 and "already closed" in r.text:
            pytest.skip("journée déjà clôturée — une seule clôture par jour")
        assert r.status_code == 200, r.text
        d = r.json()
        # pipeline steps present
        steps = [s["step"] for s in d.get("steps", [])]
        for expected in ["collect_reports", "agent000_control", "memory_snapshots",
                         "registry_daily_states", "executive_report", "system_ready_next_day"]:
            assert expected in steps, f"missing step {expected}: {steps}"
        # executive report structure
        er = d.get("executive_report", {})
        assert er.get("headline"), "executive_report.headline missing"
        assert "Laurent" in er.get("for", ""), "executive_report.for must mention Laurent"
        assert isinstance(er.get("tomorrow_top_priorities"), list)
        # global blocks
        assert d["average_confidence"] is not None
        assert "next_day_plan" in d
        assert d["status"] == "closed"

    def test_b2_recloseure_conflict(self, admin_headers):
        r = requests.post(f"{API}/daily/close", headers=admin_headers, json={"note": "second attempt"})
        assert r.status_code == 409, r.text

    def test_b3_submit_after_closure_conflict(self, admin_headers):
        r = requests.post(f"{API}/daily/reports", headers=admin_headers, json=_sample_report("AGT-002"))
        assert r.status_code == 409, r.text


# =============================================================================
# Phase C — Read snapshots / states / closings / briefing / events
# =============================================================================
class TestPhaseC_ReadArtifacts:
    def test_c1_snapshots_three_tiers_versioned(self, admin_headers):
        r = requests.get(f"{API}/daily/snapshots?agent_id=AGT-000", headers=admin_headers)
        assert r.status_code == 200, r.text
        snaps = r.json()
        tiers = {s["tier"] for s in snaps}
        assert tiers == {"session", "operational", "strategic"}, f"tiers={tiers}"
        # each tier has version >= 1
        for s in snaps:
            assert s["version"] >= 1
            assert s["agent_id"] == "AGT-000"
            assert s["content"]  # non-empty

    def test_c2_daily_states_all_agents(self, admin_headers):
        r = requests.get(f"{API}/daily/states", headers=admin_headers)
        assert r.status_code == 200
        states = r.json()
        # at least the founders (>= 11)
        assert len(states) >= 11
        # every state has performance (nullable) and evolution_recommendation
        for s in states[:5]:
            assert "performance" in s
            assert "evolution_recommendation" in s
            assert "reported" in s

    def test_c3_list_closings(self, admin_headers):
        r = requests.get(f"{API}/daily/closings", headers=admin_headers)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 1
        assert rows[0]["status"] == "closed"

    def test_c4_get_closing_by_date(self, admin_headers):
        list_r = requests.get(f"{API}/daily/closings", headers=admin_headers).json()
        date = list_r[0]["date"]
        r = requests.get(f"{API}/daily/closings/{date}", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["date"] == date
        assert d["executive_report"]["headline"]

    def test_c5_get_closing_unknown_date_404(self, admin_headers):
        r = requests.get(f"{API}/daily/closings/2020-01-01", headers=admin_headers)
        assert r.status_code == 404

    def test_c6_briefing_reflects_last_closing(self, admin_headers):
        r = requests.get(f"{API}/daily/briefing", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["first_day"] is False
        assert d["last_closing"] is not None
        assert "priorities" in d
        assert "recommendations" in d
        # missing-agent recommendation should appear (AGT-000, AGT-001 reported → others missing)
        assert any("rapport" in rec.lower() for rec in d["recommendations"]), d["recommendations"]

    def test_c7_daily_events_present(self, admin_headers):
        r = requests.get(f"{API}/events?topic=daily&limit=50", headers=admin_headers)
        assert r.status_code == 200
        topics = {e["topic"] for e in r.json()}
        for expected in ["daily.closing.started", "daily.report.generated", "agent.daily.completed"]:
            assert expected in topics, f"missing {expected}: {topics}"

    def test_c8_system_ready_next_day_event(self, admin_headers):
        r = requests.get(f"{API}/events?topic=system.ready&limit=10", headers=admin_headers)
        assert r.status_code == 200
        topics = [e["topic"] for e in r.json()]
        assert "system.ready.next.day" in topics

    def test_c9_memory_snapshot_event(self, admin_headers):
        r = requests.get(f"{API}/events?topic=memory.snapshot&limit=10", headers=admin_headers)
        assert r.status_code == 200
        topics = [e["topic"] for e in r.json()]
        assert "memory.snapshot.created" in topics


# =============================================================================
# Phase D — Memory scope validation (session/persistent/operational/strategic)
# =============================================================================
class TestPhaseD_MemoryScopes:
    @pytest.mark.parametrize("scope", ["session", "persistent", "operational", "strategic"])
    def test_d1_valid_scopes(self, admin_headers, scope):
        payload = {"agent_id": "AGT-000", "entity": "CVLN Holding", "scope": scope,
                   "key": f"TEST_scope_{scope}_{RUN}", "value": {"note": f"scope {scope}"}}
        r = requests.post(f"{API}/memory", headers=admin_headers, json=payload)
        assert r.status_code == 200, r.text

    def test_d2_invalid_scope_400(self, admin_headers):
        payload = {"agent_id": "AGT-000", "entity": "CVLN Holding", "scope": "invalid_scope_xyz",
                   "key": f"TEST_bad_{RUN}", "value": {}}
        r = requests.post(f"{API}/memory", headers=admin_headers, json=payload)
        assert r.status_code == 400, r.text
