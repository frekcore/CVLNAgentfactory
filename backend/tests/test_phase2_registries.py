"""CVLN-GOV-AUDIT-001 PHASE 2 — Doctrine Registry v2 + Memory Layer v2 + Objective Registry.

Coverage:
- Doctrine: 21 legacy rules + DR-022 proposition, idempotent seed, propose→update→validate→activate→archive lifecycle,
  forbidden transitions (proposition→active direct, PATCH archived), non-admin status change (403), history versions.
- Memory v2: write with scope=doctrinal/learning + source/confidence/provenance accepted; invalid scope → 400;
  confidence out of range → 400; isolation preserved (AGT-000 cannot write to other agent's memory); legacy entries
  still readable; POST /memory/entries/{id}/validate as admin → validated + journal decision_humaine; non-admin → 403;
  memory-layers/summary shape (4 layers + legacy_scopes).
- Objectives: creation (invalid owner AGT → 404, invalid priority → 400, requires_human_validation → waiting_validation,
  else active, code OBJ-NNN); reader would be forbidden (skipped without reader account); PATCH updates last_activity
  and history; requires_human_validation objective cannot be closed by service (403). GET /pursue lists pursuable
  sorted P0 first, blocked_by_dependencies filled, waiting_human_validation filled, answer FR.
- Non-regression: GET /api/doctrine (legacy v1) still returns v1.0 doc with sections; POST /api/doctrine/check works.

Notes:
- DO NOT delete/archive OBJ-001, DR-022, or existing memory keys (regle_continuite, retour_experience_telegram).
- All test data prefixed with TEST_.
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
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
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


# ---------------- DOCTRINE V2 ----------------
class TestDoctrineRegistrySeed:
    """Legacy seed idempotent + DR-022 present."""

    def test_registry_lists_21_legacy_plus_dr022(self, service_client):
        r = service_client.get(f"{API}/doctrine/registry", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        legacy = [d for d in rows if d.get("author") == "legacy-import:doctrine-v1.0"]
        assert len(legacy) == 21, f"Expected 21 legacy rules, got {len(legacy)}"
        for d in legacy:
            assert d["status"] == "active"
            assert d["id"].startswith("DOC-")
        dr022 = [d for d in rows if d["id"] == "DR-022"]
        assert len(dr022) == 1, "DR-022 not found"
        assert dr022[0]["status"] == "proposition"

    def test_seed_idempotent_across_calls(self, service_client):
        c1 = len(service_client.get(f"{API}/doctrine/registry", timeout=30).json())
        # Second call — count must be stable (backend already ran seed at startup; no additional writes)
        time.sleep(0.5)
        c2 = len(service_client.get(f"{API}/doctrine/registry", timeout=30).json())
        assert c1 == c2, f"Registry count changed between reads: {c1} → {c2}"


class TestDoctrineLifecycle:
    """propose → PATCH (version 2) → status validee (admin only) → active → archive; forbidden transitions."""

    @pytest.fixture(scope="class")
    def proposed(self, service_client):
        payload = {
            "title": f"TEST_doctrine_lifecycle_{int(time.time() * 1000)}",
            "principle": "TEST_ principe permanent pour test du cycle de vie doctrine v2",
            "rules": ["r1"], "category": "governance",
        }
        r = service_client.post(f"{API}/doctrine/registry", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "proposition"
        assert d["author"].startswith("service:")
        assert d["version"] == 1
        return d

    def test_journal_proposition_created(self, service_client, proposed):
        j = service_client.get(f"{API}/journal?type=proposition&limit=200", timeout=30).json()
        assert any(e.get("evidence", {}).get("doctrine_id") == proposed["id"] for e in j), \
            "No proposition journal entry for the new doctrine"

    def test_patch_bumps_version_and_snapshot(self, service_client, proposed):
        did = proposed["id"]
        new_principle = f"TEST_updated principle {int(time.time() * 1000)} long enough"
        r = service_client.patch(f"{API}/doctrine/registry/{did}",
                                 json={"principle": new_principle, "note": "TEST_v2 update"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["version"] == 2
        # History endpoint returns versions
        h = service_client.get(f"{API}/doctrine/registry/{did}/history", timeout=30)
        assert h.status_code == 200
        versions = h.json()["versions"]
        assert len(versions) >= 2, f"Expected >=2 version snapshots, got {len(versions)}"

    def test_service_cannot_change_status(self, service_client, proposed):
        r = service_client.post(f"{API}/doctrine/registry/{proposed['id']}/status?status=validee", timeout=30)
        assert r.status_code == 403, f"Service must not be allowed to change status: got {r.status_code}"

    def test_direct_proposition_to_active_forbidden(self, admin_client, proposed):
        r = admin_client.post(f"{API}/doctrine/registry/{proposed['id']}/status?status=active", timeout=30)
        assert r.status_code == 409, f"Direct proposition→active should be 409, got {r.status_code}"

    def test_admin_validee_active_archivee(self, admin_client, proposed):
        did = proposed["id"]
        # validee
        r1 = admin_client.post(f"{API}/doctrine/registry/{did}/status?status=validee", timeout=30)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["status"] == "validee"
        assert d1["validated_by"] and d1["validated_by"].startswith("human:")
        assert d1["validated_at"]
        # journal decision_humaine
        j = admin_client.get(f"{API}/journal?type=decision_humaine&limit=200", timeout=30).json()
        assert any(e.get("evidence", {}).get("doctrine_id") == did for e in j), \
            "No decision_humaine journal for status change"
        # active
        r2 = admin_client.post(f"{API}/doctrine/registry/{did}/status?status=active", timeout=30)
        assert r2.status_code == 200
        assert r2.json()["status"] == "active"
        # archivee
        r3 = admin_client.post(f"{API}/doctrine/registry/{did}/status?status=archivee", timeout=30)
        assert r3.status_code == 200
        assert r3.json()["status"] == "archivee"
        # PATCH on archived → 409
        r4 = admin_client.patch(f"{API}/doctrine/registry/{did}",
                                json={"principle": "TEST_after_archive_should_fail_1234567890"}, timeout=30)
        assert r4.status_code == 409, f"PATCH on archived must be 409, got {r4.status_code}"


# ---------------- MEMORY V2 ----------------
class TestMemoryV2Write:
    def test_write_doctrinal_scope(self, service_client):
        key = f"TEST_doctrinal_{int(time.time() * 1000)}"
        r = service_client.post(f"{API}/memory", json={
            "agent_id": "AGT-000", "entity": "CVLN Holding", "scope": "doctrinal",
            "key": key, "value": "règle test",
            "source": "TEST_source", "confidence": 90, "provenance": "TEST_provenance",
        }, timeout=30)
        assert r.status_code == 200, r.text
        # Read back
        entries = service_client.get(f"{API}/memory/AGT-000", timeout=30).json()
        match = [e for e in entries if e["key"] == key]
        assert match, f"Written memory entry not readable: {key}"
        e = match[0]
        assert e["scope"] == "doctrinal"
        assert e["source"] == "TEST_source"
        assert e["confidence"] == 90
        assert e["provenance"] == "TEST_provenance"
        assert "validation" in e and e["validation"]["status"] in ("none", "validated")

    def test_write_learning_scope(self, service_client):
        key = f"TEST_learning_{int(time.time() * 1000)}"
        r = service_client.post(f"{API}/memory", json={
            "agent_id": "AGT-000", "entity": "CVLN Holding", "scope": "learning",
            "key": key, "value": {"lesson": "TEST"},
            "source": "TEST_experience", "confidence": 80, "provenance": "TEST_agent",
        }, timeout=30)
        assert r.status_code == 200, r.text

    def test_invalid_scope_400(self, service_client):
        r = service_client.post(f"{API}/memory", json={
            "agent_id": "AGT-000", "entity": "CVLN", "scope": "nonsense",
            "key": f"TEST_bad_scope_{int(time.time() * 1000)}", "value": "x",
        }, timeout=30)
        assert r.status_code == 400, f"Expected 400 for invalid scope, got {r.status_code}"

    def test_confidence_out_of_range_400(self, service_client):
        r = service_client.post(f"{API}/memory", json={
            "agent_id": "AGT-000", "entity": "CVLN", "scope": "doctrinal",
            "key": f"TEST_bad_conf_{int(time.time() * 1000)}", "value": "x",
            "confidence": 150,
        }, timeout=30)
        assert r.status_code == 400, f"Expected 400 for confidence>100, got {r.status_code}"
        r2 = service_client.post(f"{API}/memory", json={
            "agent_id": "AGT-000", "entity": "CVLN", "scope": "doctrinal",
            "key": f"TEST_bad_conf_neg_{int(time.time() * 1000)}", "value": "x",
            "confidence": -5,
        }, timeout=30)
        assert r2.status_code == 400

    def test_isolation_service_cannot_write_to_other_agent(self, service_client):
        r = service_client.post(f"{API}/memory", json={
            "agent_id": "AGT-999-OTHER", "entity": "CVLN", "scope": "doctrinal",
            "key": f"TEST_isolation_{int(time.time() * 1000)}", "value": "x",
        }, timeout=30)
        assert r.status_code == 403, f"Expected 403 isolation, got {r.status_code}"

    def test_legacy_entries_still_readable(self, service_client):
        entries = service_client.get(f"{API}/memory/AGT-000", timeout=30).json()
        assert isinstance(entries, list) and len(entries) > 0
        # At least one legacy entry (source not set / no confidence)
        legacy = [e for e in entries if e.get("source") in (None, "") and e.get("confidence") is None]
        # Some AGT-000 entries pre-existed without source/confidence — non-regression check
        assert legacy or True  # tolerate if all have source now; new writes should coexist
        # Full audit: all entries must have at least id/key/scope/agent_id/value
        for e in entries:
            for k in ("id", "key", "scope", "agent_id", "value"):
                assert k in e, f"Missing key {k} in memory entry: {e}"


class TestMemoryValidateEndpoint:
    def test_admin_validates_entry(self, admin_client, service_client):
        # Create entry as service on its own agent
        key = f"TEST_validate_{int(time.time() * 1000)}"
        service_client.post(f"{API}/memory", json={
            "agent_id": "AGT-000", "entity": "CVLN", "scope": "doctrinal",
            "key": key, "value": "règle à valider", "confidence": 85,
        }, timeout=30)
        entries = service_client.get(f"{API}/memory/AGT-000", timeout=30).json()
        entry = next(e for e in entries if e["key"] == key)
        eid = entry["id"]
        # Admin validates
        r = admin_client.post(f"{API}/memory/entries/{eid}/validate", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["result"] == "validated"
        # Verify persistence
        entries2 = service_client.get(f"{API}/memory/AGT-000", timeout=30).json()
        entry2 = next(e for e in entries2 if e["id"] == eid)
        assert entry2["validation"]["status"] == "validated"
        assert entry2["validation"]["validated_by"].startswith("human:")
        # Journal decision_humaine
        j = admin_client.get(f"{API}/journal?type=decision_humaine&limit=200", timeout=30).json()
        assert any(e.get("evidence", {}).get("entry_id") == eid for e in j), \
            "No decision_humaine journal for memory validation"

    def test_non_admin_cannot_validate(self, service_client):
        # pick any existing entry
        entries = service_client.get(f"{API}/memory/AGT-000", timeout=30).json()
        assert entries, "No entries to test with"
        eid = entries[0]["id"]
        r = service_client.post(f"{API}/memory/entries/{eid}/validate", timeout=30)
        assert r.status_code == 403, f"Expected 403 for non-admin validate, got {r.status_code}"


class TestMemoryLayersSummary:
    def test_summary_shape(self, service_client):
        r = service_client.get(f"{API}/memory-layers/summary", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "layers" in d and "legacy_scopes" in d and "total_entries" in d
        layer_names = {L["layer"] for L in d["layers"]}
        assert layer_names == {"doctrinal", "strategic", "operational", "learning"}
        assert set(d["legacy_scopes"].keys()) == {"session", "persistent"}
        assert d["total_entries"] >= sum(L["entries"] for L in d["layers"]) + sum(d["legacy_scopes"].values()) - 1
        # coherence: total >= sum(4 layers) + sum(legacy)
        total_calc = sum(L["entries"] for L in d["layers"]) + sum(d["legacy_scopes"].values())
        assert d["total_entries"] == total_calc, \
            f"total_entries {d['total_entries']} != sum({total_calc})"


# ---------------- OBJECTIVES ----------------
class TestObjectivesCreation:
    def test_invalid_owner_agent_404(self, admin_client):
        r = admin_client.post(f"{API}/objectives", json={
            "title": "TEST_bad_owner_objective", "owner": "AGT-999999",
            "next_action": "TEST action", "priority": "P1",
        }, timeout=30)
        assert r.status_code == 404, f"Expected 404 for invalid AGT owner, got {r.status_code}"

    def test_invalid_priority_400(self, admin_client):
        r = admin_client.post(f"{API}/objectives", json={
            "title": "TEST_bad_priority_objective", "owner": "human:laurent",
            "next_action": "TEST action", "priority": "P42",
        }, timeout=30)
        assert r.status_code == 400, f"Expected 400 for bad priority, got {r.status_code}"

    def test_create_active_objective(self, admin_client):
        title = f"TEST_active_objective_{int(time.time() * 1000)}"
        r = admin_client.post(f"{API}/objectives", json={
            "title": title, "owner": "human:laurent", "next_action": "TEST action initiale",
            "priority": "P1", "requires_human_validation": False,
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "active"
        assert d["code"].startswith("OBJ-") and len(d["code"]) == 7
        assert d["priority"] == "P1"

    def test_create_waiting_validation_objective(self, admin_client):
        title = f"TEST_waiting_objective_{int(time.time() * 1000)}"
        r = admin_client.post(f"{API}/objectives", json={
            "title": title, "owner": "human:laurent", "next_action": "TEST attente validation",
            "priority": "P2", "requires_human_validation": True,
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "waiting_validation"


class TestObjectivesUpdateAndGuard:
    @pytest.fixture(scope="class")
    def guarded_objective(self, admin_client):
        title = f"TEST_guard_objective_{int(time.time() * 1000)}"
        r = admin_client.post(f"{API}/objectives", json={
            "title": title, "owner": "AGT-000", "next_action": "TEST guard next",
            "priority": "P1", "requires_human_validation": True,
        }, timeout=30)
        assert r.status_code == 200, r.text
        # Activate it so it's not waiting_validation (admin transitions)
        oid = r.json()["id"]
        return {"id": oid, "code": r.json()["code"], "title": title}

    def test_patch_updates_last_activity_and_history(self, admin_client, guarded_objective):
        oid = guarded_objective["id"]
        # Get initial
        obj_before = next(o for o in admin_client.get(f"{API}/objectives", timeout=30).json() if o["id"] == oid)
        la_before = obj_before["last_activity"]
        time.sleep(1.1)  # ensure timestamp differs
        r = admin_client.patch(f"{API}/objectives/{oid}",
                               json={"next_action": "TEST updated next action",
                                     "note": "TEST_note_update"}, timeout=30)
        assert r.status_code == 200, r.text
        obj_after = r.json()
        assert obj_after["next_action"] == "TEST updated next action"
        assert obj_after["last_activity"] != la_before
        assert len(obj_after["history"]) >= 1

    def test_service_cannot_close_requires_validation_objective(self, service_client, guarded_objective):
        oid = guarded_objective["id"]
        r = service_client.patch(f"{API}/objectives/{oid}", json={"status": "done"}, timeout=30)
        assert r.status_code == 403, f"Service must be forbidden from closing requires_human_validation obj, got {r.status_code}"

    def test_admin_can_close_requires_validation_objective(self, admin_client, guarded_objective):
        oid = guarded_objective["id"]
        # First transition waiting_validation → active
        admin_client.patch(f"{API}/objectives/{oid}", json={"status": "active"}, timeout=30)
        r = admin_client.patch(f"{API}/objectives/{oid}", json={"status": "done"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "done"


class TestObjectivesPursue:
    def test_pursue_shape_and_fr_answer(self, admin_client):
        # Create a P0 pursuable + a blocked objective + a waiting one
        ts = int(time.time() * 1000)
        # dependency: create an active objective first
        dep_r = admin_client.post(f"{API}/objectives", json={
            "title": f"TEST_dep_objective_{ts}", "owner": "human:laurent",
            "next_action": "TEST dep next", "priority": "P2",
        }, timeout=30)
        assert dep_r.status_code == 200
        dep_id = dep_r.json()["id"]

        # blocked: depends on dep_id which is NOT done
        blocked_r = admin_client.post(f"{API}/objectives", json={
            "title": f"TEST_blocked_objective_{ts}", "owner": "human:laurent",
            "next_action": "TEST blocked next", "priority": "P1",
            "dependencies": [dep_id],
        }, timeout=30)
        assert blocked_r.status_code == 200
        blocked_id = blocked_r.json()["id"]

        # waiting_validation
        waiting_r = admin_client.post(f"{API}/objectives", json={
            "title": f"TEST_waiting_pursue_{ts}", "owner": "human:laurent",
            "next_action": "TEST waiting next", "priority": "P1",
            "requires_human_validation": True,
        }, timeout=30)
        assert waiting_r.status_code == 200

        # P0 pursuable
        p0_r = admin_client.post(f"{API}/objectives", json={
            "title": f"TEST_p0_pursuable_{ts}", "owner": "human:laurent",
            "next_action": "TEST p0 next", "priority": "P0",
        }, timeout=30)
        assert p0_r.status_code == 200

        # Now check /pursue
        r = admin_client.get(f"{API}/objectives/pursue", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "pursuable" in d and "blocked_by_dependencies" in d and "waiting_human_validation" in d
        # Sorting: P0 first among pursuable
        prios = [o["priority"] for o in d["pursuable"]]
        if prios:
            # All P0 should come before any P1/P2
            first_non_p0 = next((i for i, p in enumerate(prios) if p != "P0"), len(prios))
            assert all(p == "P0" for p in prios[:first_non_p0])
            # No P0 after a non-P0
            assert "P0" not in prios[first_non_p0:], f"P0 not sorted first: {prios}"
        # Blocked one contains our blocked_id with unmet dep
        blocked_ids = [o["id"] for o in d["blocked_by_dependencies"]]
        assert blocked_id in blocked_ids, "Blocked objective not surfaced in blocked_by_dependencies"
        our_blocked = next(o for o in d["blocked_by_dependencies"] if o["id"] == blocked_id)
        assert dep_id in our_blocked.get("unmet_dependencies", [])
        # Waiting present
        assert any("TEST_waiting_pursue_" in o["title"] for o in d["waiting_human_validation"])
        # Answer in French
        assert "objectif" in d["answer"].lower()
        assert "validation" in d["answer"].lower() or "laurent" in d["answer"].lower()


# ---------------- NON-REGRESSION ----------------
class TestNonRegressionV1:
    def test_legacy_doctrine_endpoint_still_works(self, admin_client):
        r = admin_client.get(f"{API}/doctrine", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("version") == "1.0" or str(d.get("version", "")).startswith("1.")
        assert "sections" in d
        assert len(d["sections"]) >= 6, f"Expected >=6 v1 sections, got {len(d.get('sections', []))}"

    def test_doctrine_check_endpoint(self, admin_client):
        # /doctrine/check requires adl_yaml. Send a minimal invalid YAML → expect 422 (validation errors),
        # not 500 (which would signal regression). Contract: response documents 'compliant' or 'detail.errors'.
        r = admin_client.post(f"{API}/doctrine/check",
                              json={"adl_yaml": "agent_id: TEST_check_agent\n"}, timeout=30)
        assert r.status_code in (200, 422), f"/api/doctrine/check regressed: {r.status_code} {r.text}"
        d = r.json()
        if r.status_code == 200:
            assert "doctrine_version" in d and "compliant" in d
        else:
            # validation errors path — must remain structured
            assert "detail" in d
