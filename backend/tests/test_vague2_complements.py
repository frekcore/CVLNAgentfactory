"""VAGUE 2 — Compléments : multi-tours conversation, non-régression, constitution summary."""
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip()
                break
BASE = (BASE or "").rstrip("/")


@pytest.fixture(scope="module")
def admin():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "laurent@cvln.fr", "password": "CVLNfactory2026!"}, timeout=30)
    assert r.status_code == 200, r.text
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


# ---------- L4 — Multi-tours conversation persistence ----------
def test_l4_multi_turn_conversation_persists(admin):
    r1 = admin.post(f"{BASE}/api/cognitive/chat",
                    json={"message": "Bonjour, ceci est le tour 1",
                          "disable_knowledge_search": True}, timeout=90)
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    conv_id = body1.get("conversation_id")
    assert conv_id, "conversation_id manquant sur la réponse chat"
    sk1 = body1["sovereign_knowledge"]
    assert sk1["used"] is False and sk1["retrieval_ms"] == 0

    r2 = admin.post(f"{BASE}/api/cognitive/chat",
                    json={"message": "Et voici le tour 2 dans la même conversation",
                          "conversation_id": conv_id,
                          "disable_knowledge_search": True}, timeout=90)
    assert r2.status_code == 200, r2.text
    assert r2.json().get("conversation_id") == conv_id

    hist = admin.get(f"{BASE}/api/cognitive/conversations/{conv_id}/messages", timeout=30)
    assert hist.status_code == 200, hist.text
    messages = hist.json()
    if isinstance(messages, dict):
        messages = messages.get("messages", [])
    user_msgs = [m for m in messages if m.get("role") == "user"]
    assert len(user_msgs) >= 2, f"attendu ≥2 messages user, reçu {len(user_msgs)}"


# ---------- Constitution — summary fail == 0 ----------
def test_constitution_summary_no_failures(admin):
    r = admin.get(f"{BASE}/api/constitution/verify", timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    summary = body.get("summary") or {}
    assert summary.get("fail", 0) == 0, f"constitution: fails={summary.get('fail')} → {body}"


# ---------- Non-régression ----------
def test_registry_agents_ok_and_135_drafts_intact(admin):
    r = admin.get(f"{BASE}/api/registry/agents", timeout=30)
    assert r.status_code == 200, r.text
    agents = r.json()
    if isinstance(agents, dict):
        agents = agents.get("agents", agents.get("items", []))
    drafts = [a for a in agents if (a.get("lifecycle_status") or a.get("status")) == "Draft"]
    assert len(drafts) >= 135, f"attendu ≥135 Draft, reçu {len(drafts)}"


def test_gate_validation_requests_ok(admin):
    r = admin.get(f"{BASE}/api/gate/validation-requests", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    # accept liste ou objet paginé
    assert isinstance(body, (list, dict))


def test_login_admin_ok():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "laurent@cvln.fr", "password": "CVLNfactory2026!"}, timeout=30)
    assert r.status_code == 200
    assert "access_token" in r.json()
