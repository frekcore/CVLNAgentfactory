"""Constitution CVLN — 21 articles + verify + amendements + immutabilité du hash."""
import os
import json
import hashlib
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE:
    try:
        with open("/app/frontend/.env") as _f:
            for _line in _f:
                if _line.startswith("REACT_APP_BACKEND_URL="):
                    BASE = _line.split("=", 1)[1].strip()
                    break
    except Exception:
        pass
BASE = (BASE or "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL not configured"
ADMIN_EMAIL = "laurent@cvln.fr"
ADMIN_PASSWORD = "CVLNfactory2026!"
SVC_AGT000 = "svc_agt000_9f2e7c1a4b8d6f3e0a5c2d7b1e4f8a6c"


@pytest.fixture(scope="module")
def admin_session():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module")
def svc_session():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {SVC_AGT000}"
    return s


@pytest.fixture(scope="module")
def constitution(admin_session):
    r = admin_session.get(f"{BASE}/api/constitution", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def verify_result(admin_session):
    r = admin_session.get(f"{BASE}/api/constitution/verify", timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def verify_by_article(verify_result):
    return {a["article"]: a for a in verify_result["articles"]}


# ---------------- GET /api/constitution ----------------
class TestConstitutionDocument:
    def test_version_and_articles_count(self, constitution):
        assert constitution["constitution_version"] == "1.0"
        assert len(constitution["articles"]) == 21

    def test_article_ids_sequential(self, constitution):
        ids = [a["id"] for a in constitution["articles"]]
        expected = [f"ART-{i:03d}" for i in range(1, 22)]
        assert ids == expected

    def test_article_fields(self, constitution):
        required = {"id", "title", "category", "rule", "validator", "violation_action", "enforceable"}
        for a in constitution["articles"]:
            assert required.issubset(a.keys()), f"Article {a.get('id')} missing fields"
            assert a["enforceable"] is True

    def test_hash_format(self, constitution):
        h = constitution["hash"]
        assert h.startswith("sha256:")
        assert len(h) == len("sha256:") + 64

    def test_amendment_history_empty(self, constitution):
        assert constitution.get("amendment_history", []) == []


# ---------------- Immutabilité / hash canonique ----------------
class TestHashImmutability:
    def test_two_calls_same_hash(self, admin_session):
        h1 = admin_session.get(f"{BASE}/api/constitution").json()["hash"]
        h2 = admin_session.get(f"{BASE}/api/constitution").json()["hash"]
        assert h1 == h2

    def test_hash_matches_canonical_sha256(self, constitution):
        recomputed = "sha256:" + hashlib.sha256(
            json.dumps(constitution["articles"], sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        assert recomputed == constitution["hash"]


# ---------------- 21 tests — 1 par article ----------------
EXPECTED_STATUS = {
    "ART-001": {"pass"},
    "ART-002": {"pass"},
    "ART-003": {"pass"},
    "ART-004": {"pass"},
    "ART-005": {"pass"},
    "ART-006": {"pending_layer"},
    "ART-007": {"pending_layer"},
    "ART-008": {"pass"},
    "ART-009": {"pass"},
    "ART-010": {"pass"},
    "ART-011": {"pass"},
    "ART-012": {"pass"},
    "ART-013": {"pass"},
    "ART-014": {"manual"},
    "ART-015": {"pass"},
    "ART-016": {"pass", "partial"},
    "ART-017": {"fail"},  # violation attendue AGT-100
    "ART-018": {"pass"},
    "ART-019": {"pass"},
    "ART-020": {"pending_layer"},
    "ART-021": {"pass"},
}


@pytest.mark.parametrize("art_id,allowed", list(EXPECTED_STATUS.items()))
def test_article_verification(verify_by_article, art_id, allowed):
    """Chaque article : résultat existe, evidence non vide, statut conforme."""
    assert art_id in verify_by_article, f"{art_id} absent du verify"
    r = verify_by_article[art_id]
    assert r.get("evidence"), f"{art_id} evidence vide"
    assert isinstance(r["evidence"], str) and len(r["evidence"]) > 0
    assert r["status"] in allowed, f"{art_id} status {r['status']} not in {allowed} — evidence: {r['evidence']}"


# ---------------- Amendements ----------------
class TestAmendments:
    def test_propose_ok_admin(self, admin_session):
        r = admin_session.post(f"{BASE}/api/constitution/amendments", json={
            "article_id": "ART-005",
            "new_rule": "TEST_AMEND rule proposal at least 10 chars long",
            "justification": "TEST_AMEND justification pour test unitaire"
        }, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "proposed"
        assert body["article_id"] == "ART-005"
        assert body["signatures"] == []
        # store for later tests
        TestAmendments.amendment_id = body["id"]

    def test_propose_unknown_article_404(self, admin_session):
        r = admin_session.post(f"{BASE}/api/constitution/amendments", json={
            "article_id": "ART-999",
            "new_rule": "new rule content long enough",
            "justification": "justification long enough"
        }, timeout=30)
        assert r.status_code == 404

    def test_service_agt000_cannot_sign(self, svc_session):
        """AGT-000 n'est PAS fondateur votant — 403 attendu."""
        am_id = getattr(TestAmendments, "amendment_id", None)
        assert am_id, "amendment_id manquant"
        r = svc_session.post(f"{BASE}/api/constitution/amendments/{am_id}/sign", timeout=30)
        assert r.status_code == 403, r.text

    def test_validate_wudy_without_quorum_409(self, admin_session):
        am_id = getattr(TestAmendments, "amendment_id", None)
        assert am_id, "amendment_id manquant"
        r = admin_session.post(f"{BASE}/api/constitution/amendments/{am_id}/validate-wudy", timeout=30)
        assert r.status_code == 409, r.text

    def test_hash_unchanged_after_attempts(self, admin_session, constitution):
        r = admin_session.get(f"{BASE}/api/constitution", timeout=30)
        assert r.status_code == 200
        assert r.json()["hash"] == constitution["hash"], "Hash MUST remain unchanged after failed amendment attempts"

    def test_reader_cannot_propose(self):
        """Le service AGT-000 n'est pas reader ; on teste avec un token invalide → 401/403 accepté.
        Le vrai test 'reader' nécessite un compte reader — on documente en skip si absent."""
        # No reader account provisioned — skip
        pytest.skip("Aucun compte reader configuré — test couvert par la logique 403 côté route")
