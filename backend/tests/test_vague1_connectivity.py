"""VAGUE 1 (P0) — Audit de connectivité : 3 liaisons câblées + Mission OS Phase B.
L1 : Alignment Engine → étape 4 cycle autonome (évaluation seule, apply=false)
L2 : File financière unique — expense délègue au Financial Gatekeeper
L3 : Propositions unifiées — /api/evolution/proposals → 410 redirect
Mission OS : entités, objectifs SO-NNN, alignment, dashboard read-only
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as _f:
            for _line in _f:
                if _line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = _line.split("=", 1)[1].strip().rstrip("/")
                    break
    except FileNotFoundError:
        pass
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "laurent@cvln.fr"
ADMIN_PASSWORD = "CVLNfactory2026!"
AGT000_TOKEN = "svc_agt000_9f2e7c1a4b8d6f3e0a5c2d7b1e4f8a6c"


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def agt000_headers():
    return {"Authorization": f"Bearer {AGT000_TOKEN}", "Content-Type": "application/json"}


# ============================================================
# LIAISON 1 — Alignment Engine dans le cycle autonome (étape 4)
# ============================================================
class TestL1AlignmentInAutonomousCycle:
    def test_cycle_analyses_carry_alignment_and_step4_mentions_apply_false(self, admin_headers):
        # Count validation_requests before
        before = requests.get(f"{API}/gate/validation-requests?status=pending",
                              headers=admin_headers, timeout=15)
        assert before.status_code == 200
        before_count = len(before.json())

        # Ensure dry_run mode
        mode_r = requests.get(f"{API}/autonomous/mode", headers=admin_headers, timeout=15)
        assert mode_r.status_code == 200
        assert mode_r.json().get("mode") == "dry_run", "must be dry_run for this test"

        # Run cycle
        r = requests.post(f"{API}/autonomous/cycle", headers=admin_headers, timeout=60)
        assert r.status_code == 200, f"cycle failed: {r.status_code} {r.text[:200]}"
        cycle = r.json()

        # analyses[] carries alignment
        analyses = cycle.get("analyses", [])
        assert len(analyses) > 0, "no analyses in cycle"
        with_alignment = [a for a in analyses if a.get("alignment")]
        assert len(with_alignment) > 0, "no alignment attached to analyses"
        for a in with_alignment:
            al = a["alignment"]
            assert "score" in al and "decision" in al
            assert isinstance(al["score"], (int, float))
            assert al["decision"] in (
                "EXECUTION_AUTORISEE", "AVERTISSEMENT_CONFIRMATION_REQUISE", "ESCALADE_HORS_MISSION")

        # Step 4 detail mentions alignment + apply=false
        step4 = next((s for s in cycle["steps"] if s["step"] == 4), None)
        assert step4 is not None
        detail = step4["detail"].lower()
        assert "alignment" in detail
        assert "apply=false" in detail

        # No new validation_request created *from alignment*
        after = requests.get(f"{API}/gate/validation-requests?status=pending",
                             headers=admin_headers, timeout=15)
        assert after.status_code == 200
        # In dry_run, no gate_check triggered from alignment (apply=false) → same or ≤ (dry_run doesn't escalate)
        # We assert count did not increase (dry_run doesn't call gate)
        assert len(after.json()) == before_count, \
            f"unexpected validation_requests created: before={before_count}, after={len(after.json())}"


# ============================================================
# LIAISON 2 — File financière unique (Financial Gatekeeper)
# ============================================================
class TestL2FinancialGatekeeperQueue:
    def test_expense_check_creates_expense_request_not_validation(self, agt000_headers, admin_headers):
        payload = {
            "action_type": "expense",
            "summary": "TEST_VAGUE1 achat licence outil dev",
            "evidence": {"amount": 75, "entity": "TEST"}
        }
        r = requests.post(f"{API}/gate/check", headers=agt000_headers, json=payload, timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert data["decision"] == "pending_human_validation"
        assert data.get("queue") == "financial-gatekeeper"
        req_id = data.get("validation_request_id")
        assert req_id

        # exists in /api/finance/expense-requests
        er = requests.get(f"{API}/finance/expense-requests", headers=admin_headers, timeout=15)
        assert er.status_code == 200
        ids = [e["id"] for e in er.json()]
        assert req_id in ids, "expense request not found in financial queue"

        # NOT in validation_requests
        vr = requests.get(f"{API}/gate/validation-requests", headers=admin_headers, timeout=15)
        assert vr.status_code == 200
        vids = [v["id"] for v in vr.json()]
        assert req_id not in vids, "id should NOT be in validation_requests"

    def test_expense_approved_then_recheck_allows_execution(self, agt000_headers, admin_headers):
        # Create small expense (amount=75, required_approvals=1)
        r = requests.post(f"{API}/gate/check", headers=agt000_headers, json={
            "action_type": "expense",
            "summary": "TEST_VAGUE1 recheck small expense",
            "evidence": {"amount": 75, "entity": "TEST"}
        }, timeout=15)
        assert r.status_code == 200
        req_id = r.json()["validation_request_id"]

        # Approve via financial route
        ap = requests.post(f"{API}/finance/expense-requests/{req_id}/approve",
                           headers=admin_headers, params={"decision": "approved"}, timeout=15)
        assert ap.status_code == 200, f"approve failed: {ap.status_code} {ap.text}"

        # Re-check with validation_id
        rc = requests.post(f"{API}/gate/check", headers=agt000_headers, json={
            "action_type": "expense",
            "summary": "TEST_VAGUE1 recheck small expense",
            "validation_id": req_id,
            "evidence": {"amount": 75}
        }, timeout=15)
        assert rc.status_code == 200
        d = rc.json()
        assert d["allowed"] is True, f"expected allowed after approval, got {d}"

    def test_expense_large_amount_requires_two_approvals(self, agt000_headers, admin_headers):
        r = requests.post(f"{API}/gate/check", headers=agt000_headers, json={
            "action_type": "expense",
            "summary": "TEST_VAGUE1 large expense",
            "evidence": {"amount": 150000, "entity": "TEST"}
        }, timeout=15)
        assert r.status_code == 200
        req_id = r.json()["validation_request_id"]

        er = requests.get(f"{API}/finance/expense-requests", headers=admin_headers, timeout=15)
        assert er.status_code == 200
        item = next((e for e in er.json() if e["id"] == req_id), None)
        assert item is not None
        assert item.get("required_approvals") == 2, f"expected 2 approvals, got {item.get('required_approvals')}"


# ============================================================
# LIAISON 3 — Propositions unifiées (410 redirect)
# ============================================================
class TestL3UnifiedProposals:
    def test_post_evolution_proposals_returns_410_with_redirect(self, admin_headers):
        r = requests.post(f"{API}/evolution/proposals", headers=admin_headers, json={
            "type": "improve_agent",
            "title": "TEST_VAGUE1 proposition unifiée",
            "description": "Test que ce POST est bien redirigé"
        }, timeout=15)
        assert r.status_code == 410, f"expected 410, got {r.status_code} {r.text}"
        body = r.json()
        detail = body.get("detail", {})
        assert isinstance(detail, dict)
        assert detail.get("redirect") == "/api/doctrine/registry"

    def test_get_evolution_proposals_still_readable(self, admin_headers):
        r = requests.get(f"{API}/evolution/proposals", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        # Historic proposals preserved
        data = r.json()
        assert isinstance(data, list)


# ============================================================
# MISSION OS (PHASE B)
# ============================================================
class TestMissionOSPhaseB:
    def test_entities_list_with_strategic_objectives_count(self, admin_headers):
        r = requests.get(f"{API}/mission-os/entities", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        ents = r.json()
        assert isinstance(ents, list)
        assert len(ents) >= 1
        for e in ents:
            assert "id" in e
            assert "strategic_objectives" in e
            assert isinstance(e["strategic_objectives"], int)

    def test_objectives_list_has_placeholders(self, admin_headers):
        r = requests.get(f"{API}/mission-os/objectives", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        objs = r.json()
        assert isinstance(objs, list)
        assert len(objs) >= 1
        # SO-NNN codes
        codes = [o.get("code", "") for o in objs]
        assert any(c.startswith("SO-") for c in codes), f"no SO-NNN placeholders found: {codes[:5]}"

    def test_create_objective_unknown_entity_returns_404(self, admin_headers):
        r = requests.post(f"{API}/mission-os/objectives", headers=admin_headers, json={
            "entity_id": "ENT-UNKNOWN-TEST",
            "title": "TEST_VAGUE1 objectif orphelin",
            "description": "test",
            "weight": 0.5
        }, timeout=15)
        assert r.status_code == 404

    def test_create_objective_non_admin_returns_403(self, agt000_headers):
        r = requests.post(f"{API}/mission-os/objectives", headers=agt000_headers, json={
            "entity_id": "ENT-001",
            "title": "TEST_VAGUE1 objectif svc",
            "description": "test"
        }, timeout=15)
        assert r.status_code == 403, f"expected 403 for non-admin, got {r.status_code} {r.text[:200]}"

    def test_alignment_relevant_task_high_score(self, admin_headers):
        r = requests.post(f"{API}/mission-os/alignment", headers=admin_headers, json={
            "agent_id": "AGT-011",
            "task_description": "Superviser la gouvernance et la clôture quotidienne du groupe"
        }, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "score" in d and "decision" in d and "reasoning" in d
        assert "breakdown" in d
        assert d.get("mode") == "evaluation_only"
        assert d["score"] > 0.6, f"expected score>0.6, got {d['score']}"
        assert d["decision"] == "EXECUTION_AUTORISEE"

    def test_alignment_absurd_task_low_score_escalate(self, admin_headers):
        r = requests.post(f"{API}/mission-os/alignment", headers=admin_headers, json={
            "agent_id": "AGT-011",
            "task_description": "réparer une machine à laver domestique cassée dans la buanderie"
        }, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["score"] < 0.3, f"expected <0.3, got {d['score']}"
        assert d["decision"] == "ESCALADE_HORS_MISSION"
        assert d.get("mode") == "evaluation_only"

    def test_dashboard_entity_read_only(self, admin_headers):
        # Get first entity
        er = requests.get(f"{API}/mission-os/entities", headers=admin_headers, timeout=15)
        entity_id = er.json()[0]["id"]
        r = requests.get(f"{API}/mission-os/dashboard/{entity_id}", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("read_only") is True
        assert "objectives" in d
        assert "agent_links" in d
        assert "recent_alignments" in d
        assert "entity" in d


# ============================================================
# CONSTITUTION — ART-006 & ART-017 PASS, fail=0
# ============================================================
class TestConstitutionArticlesPass:
    def test_verify_art006_and_art017_pass_and_fail_zero(self, admin_headers):
        r = requests.get(f"{API}/constitution/verify", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        v = r.json()
        articles = {a["article"]: a for a in v.get("articles", [])}
        assert "ART-006" in articles
        assert articles["ART-006"]["status"] == "pass", \
            f"ART-006 expected pass, got {articles['ART-006']['status']}"
        assert "ART-017" in articles
        assert articles["ART-017"]["status"] == "pass", \
            f"ART-017 expected pass, got {articles['ART-017']['status']}"
        summary = v.get("summary", {})
        assert summary.get("fail", 0) == 0, f"expected fail=0, got {summary}"
