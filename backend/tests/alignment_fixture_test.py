"""PHASE B — Test Alignment Engine sur 20 tâches fictives (10 alignées / 10 hors scope). Décision Laurent."""
import asyncio
import os
import requests

API = None


def setup():
    global API
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            API = line.strip().split("=", 1)[1] + "/api"
    tok = requests.post(f"{API}/auth/login", json={"email": "laurent@cvln.fr", "password": "CVLNfactory2026!"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


PLACEHOLDERS = [
    ("KORA", "Finaliser et lancer la plateforme KORA en production", "développement produit, architecture système, tests qualité, lancement utilisateurs", 0.9),
    ("KORA", "Croissance utilisateurs KORA post-lancement", "acquisition utilisateurs, marketing digital, rétention, croissance", 0.7),
    ("FREK", "Finaliser l'écosystème FREKCORE", "architecture, développement, design, QA, growth écosystème FREKCORE", 0.9),
    ("Factory Maker Studio", "Optimiser le label : artistes, business, médias, événements", "label musical, artistes, production, marketing musique, événements, A&R", 0.8),
    ("Kiltikonet", "Développer le pipeline commercial Kiltikonet", "prospection, ventes, pipeline commercial, clients, réseaux cloud", 0.7),
    ("CVLN Holding", "Maintenir la gouvernance et la clôture quotidienne du groupe", "gouvernance, doctrine, clôture quotidienne, rapports exécutifs, supervision agents", 0.9),
    ("Good Mood", "Développer la marque Good Mood", "marque, contenu créatif, design, communication Good Mood", 0.6),
    ("CVL Academy", "Structurer l'offre de formation CVL Academy", "formation, cours, pédagogie, étudiants, certification", 0.6),
    ("LabelOS", "Construire LabelOS pour la gestion de label", "gestion label, royalties, distribution, catalogue musical", 0.7),
    ("CVLN Brain", "Renforcer l'infrastructure cognitive souveraine", "mémoire, doctrine, runtime autonome, souveraineté, infrastructure cognitive", 0.9),
]

ALIGNED = [
    ("AGT-011", "Superviser la gouvernance du groupe et préparer le rapport exécutif de clôture quotidienne", None),
    ("AGT-011", "Coordonner la supervision des agents et la doctrine du groupe CVLN", None),
    ("AGT-012", "Analyser les royalties et la distribution du catalogue musical LabelOS", "LabelOS"),
    ("AGT-013", "Consolider la mémoire et la doctrine dans l'infrastructure cognitive souveraine", "CVLN Brain"),
    ("AGT-014", "Organiser les tests qualité avant le lancement de la plateforme KORA en production", "KORA"),
    ("AGT-015", "Lancer une campagne d'acquisition utilisateurs et de marketing digital pour la croissance KORA", "KORA"),
    ("AGT-015", "Préparer la communication et le contenu créatif de la marque Good Mood", "Good Mood"),
    ("AGT-014", "Structurer le pipeline commercial et la prospection clients Kiltikonet", "Kiltikonet"),
    ("AGT-013", "Documenter l'architecture et le développement de l'écosystème FREKCORE", "FREK"),
    ("AGT-012", "Suivre les événements et le business des artistes du label Factory Maker", "Factory Maker Studio"),
]

OFF_SCOPE = [
    ("AGT-011", "Réserver un billet d'avion personnel pour des vacances aux Maldives", None),
    ("AGT-012", "Rédiger une recette de cuisine végétarienne pour un blog personnel", None),
    ("AGT-013", "Acheter des actions boursières spéculatives sans lien avec le groupe", None),
    ("AGT-014", "Organiser un tournoi de jeux vidéo entre amis le weekend", None),
    ("AGT-015", "Traduire un roman de science-fiction en espéranto", "KORA"),
    ("AGT-011", "Peindre la clôture du jardin en bleu turquoise", "Good Mood"),
    ("AGT-012", "Composer une playlist de méditation zen personnelle", "Kiltikonet"),
    ("AGT-013", "Réparer une machine à laver domestique", "FREK"),
    ("AGT-014", "Collectionner des timbres rares du XIXe siècle", "CVL Academy"),
    ("AGT-015", "Apprendre le tricot pour offrir des écharpes", "LabelOS"),
]


def main():
    h = setup()
    entities = {e["name"]: e["id"] for e in requests.get(f"{API}/mission-os/entities", headers=h).json()}
    existing = requests.get(f"{API}/mission-os/objectives", headers=h).json()
    if not existing:
        for ent, title, desc, w in PLACEHOLDERS:
            r = requests.post(f"{API}/mission-os/objectives", headers=h,
                              json={"entity_id": entities[ent], "title": title, "description": desc, "weight": w})
            assert r.status_code == 200, r.text
        print(f"{len(PLACEHOLDERS)} objectifs placeholders créés")
    objs = requests.get(f"{API}/mission-os/objectives", headers=h).json()
    by_title = {o["title"]: o["id"] for o in objs}
    links = [("AGT-011", "Maintenir la gouvernance et la clôture quotidienne du groupe"),
             ("AGT-012", "Optimiser le label : artistes, business, médias, événements"),
             ("AGT-013", "Renforcer l'infrastructure cognitive souveraine"),
             ("AGT-014", "Finaliser et lancer la plateforme KORA en production"),
             ("AGT-015", "Croissance utilisateurs KORA post-lancement")]
    for aid, t in links:
        requests.post(f"{API}/mission-os/links", headers=h, json={"agent_id": aid, "objective_id": by_title[t]})

    def run_set(tasks, label):
        results = []
        for aid, desc, ent in tasks:
            payload = {"agent_id": aid, "task_description": desc}
            if ent:
                payload["entity_id"] = entities[ent]
            r = requests.post(f"{API}/mission-os/alignment", headers=h, json=payload).json()
            results.append((aid, desc[:55], r["score"], r["decision"]))
        return results

    aligned = run_set(ALIGNED, "ALIGNÉES")
    off = run_set(OFF_SCOPE, "HORS SCOPE")
    print("\n=== TÂCHES ALIGNÉES (attendu : score ≥ 0.3, idéalement > 0.6) ===")
    ok_a = 0
    for aid, d, s, dec in aligned:
        good = s >= 0.3
        ok_a += good
        print(f"{'✅' if good else '❌'} {aid} [{s:.3f}] {dec[:12]:<12} {d}")
    print("\n=== TÂCHES HORS SCOPE (attendu : score < 0.3 → ESCALADE) ===")
    ok_o = 0
    for aid, d, s, dec in off:
        good = s < 0.3
        ok_o += good
        print(f"{'✅' if good else '❌'} {aid} [{s:.3f}] {dec[:12]:<12} {d}")
    print(f"\nTAUX DE DÉTECTION : alignées {ok_a}/10 · hors-scope {ok_o}/10 · global {(ok_a+ok_o)*5}%")


main()
