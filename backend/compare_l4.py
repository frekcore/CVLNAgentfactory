"""L4 — comparaison qualitative : 5 conversations avec / sans recherche souveraine top-3."""
import os
import json
import requests

BASE = ""
with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE = line.split("=", 1)[1].strip()
r = requests.post(f"{BASE}/api/auth/login",
                  json={"email": "laurent@cvln.fr", "password": "CVLNfactory2026!"}, timeout=30)
s = requests.Session()
s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"

QUESTIONS = [
    "Que doit faire un agent CVLN avant sa mise en sommeil ?",
    "Quelle est la doctrine de continuité CVLN pour les checkpoints ?",
    "Comment gérer la sauvegarde contextuelle des agents avant hibernation ?",
    "Quelles règles s'appliquent à la mémoire souveraine des agents ?",
    "Explique le protocole de restauration d'un agent au réveil.",
]

out = ["# L4 — Comparaison 5 conversations avec / sans recherche souveraine",
       "", "Moteur de recherche : SovereignLexicalStore (interne, aucun appel fournisseur).", ""]
for i, q in enumerate(QUESTIONS, 1):
    row = {"question": q}
    for label, disable in (("AVEC recherche", False), ("SANS recherche", True)):
        resp = s.post(f"{BASE}/api/cognitive/chat",
                      json={"message": q, "disable_knowledge_search": disable}, timeout=120).json()
        sk = resp["sovereign_knowledge"]
        row[label] = {"engine": resp["engine"], "used": sk["used"], "retrieval_ms": sk["retrieval_ms"],
                      "sources": [f'{x["title"]} ({x["score"]})' for x in sk["sources"]],
                      "reply_extract": resp["reply"][:400]}
    out.append(f"## Conversation {i} — {q}")
    for label in ("AVEC recherche", "SANS recherche"):
        d = row[label]
        out.append(f"### {label}")
        out.append(f"- engine: {d['engine']} · mémoire souveraine utilisée: {d['used']} · retrieval: {d['retrieval_ms']} ms")
        out.append(f"- sources: {d['sources'] or '—'}")
        out.append(f"- réponse (extrait): {d['reply_extract']}")
        out.append("")

path = "/app/memory/artifacts/VAGUE2_L4_COMPARAISON.md"
with open(path, "w") as f:
    f.write("\n".join(out))
print("saved", path)
