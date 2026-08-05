"""VAGUE 2 — L4 chat⇄knowledge, L5 wake bundle, L6 dual-write, L7 briefing gouverné, entités TCV/SAYD/CC2027."""
import os
import uuid
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


@pytest.fixture(scope="session")
def admin():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="session")
def kb_source(admin):
    """Source dédiée AGT-060 avec marqueur lexical unique (sert L4 et L5)."""
    marker = f"zorglubprotocole{uuid.uuid4().hex[:6]}"
    r = admin.post(f"{BASE}/api/knowledge/sources", json={
        "type": "doctrine", "title": f"Protocole test Vague2 {marker}",
        "content": f"Le {marker} définit la procédure souveraine de sauvegarde contextuelle "
                   f"des agents CVLN avant hibernation prolongée. Le {marker} exige un checkpoint complet.",
        "agent_ids": ["AGT-060"]}, timeout=30)
    assert r.status_code == 200, r.text
    return {"marker": marker, "source": r.json()}


# ---------- Entités (corrections d'omission) ----------
def test_entities_tcv_sayd_draft_no_cc2027_duplicate(admin):
    r = admin.get(f"{BASE}/api/entities", timeout=30)
    assert r.status_code == 200
    by_name = {e["name"]: e for e in r.json()}
    for name in ("TCV", "SAYD"):
        assert name in by_name, f"entité {name} absente"
        assert by_name[name].get("status") == "draft"
        assert by_name[name].get("agent_ids") == []
    assert "CC2027" not in by_name, "CC2027 ne doit PAS être une entité doublon (rattaché à Kiltikonet)"


def test_cc2027_objective_on_kiltikonet(admin):
    ents = {e["name"]: e for e in admin.get(f"{BASE}/api/entities", timeout=30).json()}
    kilti_id = ents["Kiltikonet"]["id"]
    objs = admin.get(f"{BASE}/api/mission-os/objectives", timeout=30).json()
    cc = next((o for o in objs if o["title"].startswith("CC2027")), None)
    assert cc, "objectif stratégique CC2027 absent"
    assert cc["entity_id"] == kilti_id
    assert cc["weight"] == 0.0 and cc["horizon"] == "2028"
    assert cc["status"] == "draft" and cc.get("placeholder") is True
    for name in ("TCV", "SAYD"):
        so = next((o for o in objs if o["title"].startswith(name)), None)
        assert so and so["weight"] == 0.0 and so["horizon"] == "2028" and so["entity_id"] == ents[name]["id"]


# ---------- L4 — KnowledgeSources ⇄ chat cognitif ----------
def test_l4_chat_uses_sovereign_knowledge(admin, kb_source):
    r = admin.post(f"{BASE}/api/cognitive/chat",
                   json={"message": f"Explique le {kb_source['marker']} de sauvegarde contextuelle"},
                   timeout=90)
    assert r.status_code == 200, r.text
    sk = r.json()["sovereign_knowledge"]
    assert sk["used"] is True
    assert sk["retrieval_ms"] < 200, f"recherche trop lente : {sk['retrieval_ms']} ms"
    assert any(s["source_id"] == kb_source["source"]["id"] for s in sk["sources"])


def test_l4_chat_without_relevant_source_flags_it(admin):
    r = admin.post(f"{BASE}/api/cognitive/chat",
                   json={"message": "qwrtplmzx florbnik xylotempz vrandopilk"}, timeout=90)
    assert r.status_code == 200, r.text
    sk = r.json()["sovereign_knowledge"]
    assert sk["used"] is False
    assert sk["note"] and "mémoire souveraine" in sk["note"]


def test_l4_disable_search_flag(admin):
    r = admin.post(f"{BASE}/api/cognitive/chat",
                   json={"message": "checkpoint sauvegarde agent sommeil", "disable_knowledge_search": True},
                   timeout=90)
    assert r.status_code == 200, r.text
    sk = r.json()["sovereign_knowledge"]
    assert sk["used"] is False and sk["retrieval_ms"] == 0


# ---------- L5 — KnowledgeSources ⇄ wake (AGT-060) ----------
def test_l5_wake_agt060_lists_knowledge_sources(admin, kb_source):
    rt = admin.get(f"{BASE}/api/runtime/agents/AGT-060", timeout=30).json()
    if rt.get("runtime", rt).get("state") == "actif" or rt.get("state") == "actif":
        admin.post(f"{BASE}/api/runtime/agents/AGT-060/state",
                   json={"state": "sommeil", "note": "préparation test Vague2 L5"}, timeout=30)
    r = admin.post(f"{BASE}/api/runtime/agents/AGT-060/wake", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    ks = body["restored_context"]["knowledge_sources"]
    assert ks, "le bundle wake doit lister les KnowledgeSources"
    assert any(s["id"] == kb_source["source"]["id"] for s in ks), "AGT-060 doit lister sa source dédiée"
    assert body["bundle_size_bytes"] <= 1_000_000, f"bundle {body['bundle_size_bytes']} octets > 1 Mo"
    # remise en sommeil : AGT-060 est un agent Draft, il reste dormant
    r2 = admin.post(f"{BASE}/api/runtime/agents/AGT-060/state",
                    json={"state": "sommeil", "note": "fin test Vague2 L5 — retour dormant"}, timeout=30)
    assert r2.status_code == 200, r2.text


def test_l5_constitution_art005_passes(admin):
    r = admin.get(f"{BASE}/api/constitution/verify", timeout=60)
    assert r.status_code == 200, r.text
    checks = r.json().get("articles", [])
    art5 = next((c for c in checks if c.get("article") == "ART-005"), None)
    assert art5, "ART-005 absent du verify"
    assert art5["status"] == "pass", art5


# ---------- L6 — Dual write knowledge ----------
def test_l6_dual_write_coherent(admin):
    title = f"Test L6 dual-write {uuid.uuid4().hex[:6]}"
    r = admin.post(f"{BASE}/api/knowledge/ingest", json={
        "title": title, "source_type": "note",
        "content": "Contenu de test dual write vague deux pour la cohérence souveraine CVLN."},
        timeout=30)
    assert r.status_code == 200, r.text
    item = r.json()
    assert item.get("v2_source_id"), "dual write : v2_source_id manquant"
    rc = admin.get(f"{BASE}/api/knowledge/sources/consistency", timeout=30)
    assert rc.status_code == 200, rc.text
    report = rc.json()
    assert "aucune correction automatique" in report["policy"]
    assert item["id"] in report["coherent_ids"], "le nouvel item doit être cohérent legacy⇄v2"
    assert item["id"] not in [m["item_id"] for m in report["mismatches"]]


def test_l6_consistency_alert_only_structure(admin):
    r = admin.get(f"{BASE}/api/knowledge/sources/consistency", timeout=30)
    assert r.status_code == 200
    body = r.json()
    for key in ("total_legacy_items", "coherent", "mismatches", "legacy_without_v2", "policy"):
        assert key in body


# ---------- L7 — Daily Closing / Morning Briefing enrichis ----------
def test_l7_briefing_governance_read_only(admin):
    r = admin.get(f"{BASE}/api/daily/briefing", timeout=30)
    assert r.status_code == 200, r.text
    g = r.json().get("governance")
    assert g and g["read_only"] is True
    for key in ("pending_gate_validations", "pending_expense_requests", "pending_amendments", "alignment_today"):
        assert key in g, f"{key} absent"
        if key != "alignment_today":
            assert isinstance(g[key]["count"], int)
    assert "evaluations" in g["alignment_today"]
