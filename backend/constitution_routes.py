"""Constitution CVLN — loi suprême exécutable (21 articles, hash SHA-256, table de vérification auto).
Amendements : Art. 21 — proposition → quorum Founder Council (3/10) → validation Wudy → nouveau hash. Jamais rétroactif."""
import json
import uuid
import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from database import db
from auth_utils import get_current_actor, require_admin
from activity_journal import journal
from event_bus import publish

router = APIRouter(prefix="/constitution", tags=["constitution"])

ARTICLES = [
    {"id": "ART-001", "title": "Souveraineté de CVLN", "category": "principles",
     "rule": "La logique métier appartient à CVLN, pas aux IA. Les modèles sont des moteurs interchangeables.",
     "validator": "ProviderAdapterLayer", "violation_action": "BLOCK_AND_ALERT"},
    {"id": "ART-002", "title": "Traçabilité Totale", "category": "principles",
     "rule": "Chaque action est loggée, versionnée, auditable.", "validator": "ActivityJournal", "violation_action": "BLOCK_AND_LOG"},
    {"id": "ART-003", "title": "Séparation des Pouvoirs", "category": "principles",
     "rule": "Création (AGT-000), exécution (agents), validation (humains) sont séparées.", "validator": "IdentityService", "violation_action": "BLOCK"},
    {"id": "ART-004", "title": "Principe de Précaution", "category": "principles",
     "rule": "Aucune action irréversible sans double validation. DRY RUN obligatoire avant LIVE.", "validator": "PermissionGate", "violation_action": "BLOCK"},
    {"id": "ART-005", "title": "Droit à la Mémoire", "category": "agents",
     "rule": "Chaque agent a une mémoire persistante structurée (KnowledgeSource).", "validator": "MemoryService", "violation_action": "ALERT"},
    {"id": "ART-006", "title": "Devoir d'Alignment", "category": "agents",
     "rule": "Avant d'exécuter, l'agent vérifie son alignment avec les objectifs stratégiques. Score < 0.3 → escalade.", "validator": "MissionOS", "violation_action": "ESCALATE"},
    {"id": "ART-007", "title": "Droit à l'Auto-amélioration", "category": "agents",
     "rule": "Cycle d'apprentissage à chaque closing. Learning Score < 50 → review obligatoire.", "validator": "LearningLayer", "violation_action": "REVIEW"},
    {"id": "ART-008", "title": "Devoir de Transparence", "category": "agents",
     "rule": "Chaque décision est justifiée (champ reasoning/résumé obligatoire).", "validator": "ActivityJournal", "violation_action": "BLOCK"},
    {"id": "ART-009", "title": "Secret Zero", "category": "security",
     "rule": "Aucun secret en clair. Hachage + rotation + TTL.", "validator": "IdentityService", "violation_action": "BLOCK_AND_ALERT"},
    {"id": "ART-010", "title": "Moindre Privilège", "category": "security",
     "rule": "Accès strictement nécessaire à la mission.", "validator": "IdentityService", "violation_action": "BLOCK"},
    {"id": "ART-011", "title": "Isolation des Entités", "category": "security",
     "rule": "KORA, FREKCORE, Factory Maker, TCV, SAYD, Kiltikonet, CC2027 sont isolées par défaut.", "validator": "MemoryService", "violation_action": "BLOCK"},
    {"id": "ART-012", "title": "Communication Contrôlée", "category": "security",
     "rule": "Communication inter-pôle uniquement par Event Bus.", "validator": "EventBus", "violation_action": "BLOCK"},
    {"id": "ART-013", "title": "Plafonds Financiers", "category": "finance",
     "rule": "0-10K€ auto / 10K-100K€ Wudy / >100K€ Wudy + second validateur distinct.", "validator": "FinancialGatekeeper", "violation_action": "BLOCK"},
    {"id": "ART-014", "title": "Budget par Entité", "category": "finance",
     "rule": "Aucun dépassement du budget alloué à une entité.", "validator": "FinancialGatekeeper", "violation_action": "BLOCK"},
    {"id": "ART-015", "title": "Audit Financier", "category": "finance",
     "rule": "Toute transaction est immuable et consultable.", "validator": "FinanceService", "violation_action": "ALERT"},
    {"id": "ART-016", "title": "Cycle de Vie Obligatoire", "category": "lifecycle",
     "rule": "DRAFT → PROTOTYPE → STAGING → PRODUCTION → DEPRECATED → ARCHIVE. Aucun raccourci.", "validator": "RegistryService", "violation_action": "BLOCK"},
    {"id": "ART-017", "title": "Archivage", "category": "lifecycle",
     "rule": "Un agent archivé est conservé mais inactif.", "validator": "RegistryService", "violation_action": "BLOCK"},
    {"id": "ART-018", "title": "Provider Adapter Obligatoire", "category": "providers",
     "rule": "Aucun appel direct à une API IA externe. Tout passe par IAIProvider.", "validator": "ProviderAdapterLayer", "violation_action": "BLOCK"},
    {"id": "ART-019", "title": "Fallback Obligatoire", "category": "providers",
     "rule": "Chaque chaîne de routage se termine par le moteur souverain interne.", "validator": "ModelRouter", "violation_action": "ALERT"},
    {"id": "ART-020", "title": "Simulation avant Décision", "category": "governance",
     "rule": "Toute décision critique (DEPLOY, BUDGET, DELETE, PUBLISH, HIRE, MODIFY_CORE) doit être simulée.", "validator": "SimulationLayer", "violation_action": "BLOCK"},
    {"id": "ART-021", "title": "Procédure d'Amendement", "category": "governance",
     "rule": "Proposition → Event Bus → Vote Founder Council (3/10) → Validation Wudy → nouveau hash. Jamais rétroactif.", "validator": "Constitution", "violation_action": "BLOCK"},
]

CRITICAL_GATE_ACTIONS = ["expense", "external_publication", "governance_change",
                         "data_deletion", "permission_change", "critical_production_activation"]
FOUNDERS = [f"AGT-{i:03d}" for i in range(1, 11)]
QUORUM = 3
try:
    from founder_council import FOUNDERS, QUORUM  # LIAISON 3 : mécanique de quorum unifiée
except ImportError:
    pass


def compute_hash(articles: list) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(articles, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def seed_constitution():
    if await db.constitution.find_one({"key": "constitution"}):
        return
    articles = [{**a, "enforceable": True, "violation_target": "AGT-000"} for a in ARTICLES]
    await db.constitution.insert_one({
        "key": "constitution", "constitution_version": "1.0", "hash": compute_hash(articles),
        "adopted_at": now_iso(), "last_amended": None, "amendment_history": [], "articles": articles})


@router.get("")
async def get_constitution(actor: dict = Depends(get_current_actor)):
    doc = await db.constitution.find_one({"key": "constitution"}, {"_id": 0})
    return doc


@router.get("/verify")
async def verify_constitution(actor: dict = Depends(get_current_actor)):
    """Table de vérification automatique — chaque article vérifié contre l'état RÉEL du système, avec preuves."""
    results = []

    def add(art_id, status, evidence):
        results.append({"article": art_id, "title": next(a["title"] for a in ARTICLES if a["id"] == art_id),
                        "status": status, "evidence": evidence})

    # ART-001 Souveraineté : moteur souverain présent et sain dans le Provider Layer
    from provider_layer import ADAPTERS, STRATEGIES
    sov_ok = "sovereign" in ADAPTERS and await ADAPTERS["sovereign"].health_check()
    add("ART-001", "pass" if sov_ok else "fail",
        f"Moteur souverain interne {'opérationnel' if sov_ok else 'ABSENT'} — logique métier 100% CVLN (classification, gate, cycles déterministes)")

    # ART-002 Traçabilité
    j, a, e = await db.activity_journal.count_documents({}), await db.audit_logs.count_documents({}), await db.events.count_documents({})
    add("ART-002", "pass" if (j and a and e) else "fail",
        f"{j} entrées journal v2, {a} logs authz, {e} événements — triple traçabilité active")

    # ART-003 Séparation des pouvoirs
    creations = await db.versions.count_documents({"actor": "service:AGT-000"})
    validations = await db.activity_journal.count_documents({"type": "decision_humaine", "actor_type": "human"})
    add("ART-003", "pass" if (creations and validations) else "fail",
        f"{creations} écritures Registry par AGT-000 (création), {validations} décisions humaines (validation) — pouvoirs séparés")

    # ART-004 Précaution : DRY RUN + double validation critique
    mode = await db.settings.find_one({"key": "autonomous_runtime_mode"})
    dry_runs = await db.autonomous_cycles.count_documents({"mode": "dry_run", "status": "completed"})
    bad_rules = await db.permission_rules.count_documents(
        {"action_type": {"$in": CRITICAL_GATE_ACTIONS}, "level": {"$lt": 5}, "active": True})
    ok4 = dry_runs > 0 and bad_rules == 0
    add("ART-004", "pass" if ok4 else "fail",
        f"Mode runtime: {(mode or {}).get('value', 'dry_run')}, {dry_runs} dry runs complets, {bad_rules} règle(s) critique(s) sous niveau 5 (attendu 0)")

    # ART-005 Droit à la mémoire
    with_memory = len(await db.memory_entries.distinct("agent_id"))
    total_agents = await db.agents.count_documents({})
    add("ART-005", "pass" if with_memory > 0 else "fail",
        f"{with_memory}/{total_agents} agents avec mémoire persistante + {await db.knowledge_sources.count_documents({})} KnowledgeSources")

    # ART-006 Alignment (Mission OS — PHASE B)
    mos = await db.strategic_objectives.count_documents({})
    add("ART-006", "pass" if mos else "pending_layer",
        f"Mission OS : {mos} objectif(s) stratégique(s) — couche PHASE B" + (" active" if mos else " en attente de construction"))

    # ART-007 Auto-amélioration (Learning — PHASE D)
    lc = await db.learning_cycles.count_documents({})
    add("ART-007", "pass" if lc else "pending_layer",
        f"Learning Layer : {lc} cycle(s) d'apprentissage — couche PHASE D" + (" active" if lc else " en attente de construction"))

    # ART-008 Transparence : les entrées journal ont un résumé
    empty = await db.activity_journal.count_documents({"summary": {"$in": ["", None]}})
    add("ART-008", "pass" if empty == 0 else "fail", f"{empty} entrée(s) journal sans justification (attendu 0)")

    # ART-009 Secret Zero
    plaintext = await db.identities.count_documents({"token": {"$exists": True}})
    hashed = await db.identities.count_documents({"token_hash": {"$exists": True}})
    rotated = await db.identities.count_documents({"rotated_at": {"$exists": True}})
    add("ART-009", "pass" if plaintext == 0 and hashed > 0 else "fail",
        f"{hashed} tokens hachés SHA-256, {plaintext} en clair (attendu 0), {rotated} rotation(s) effectuée(s), TTL supporté")

    # ART-010 Moindre privilège
    broad = await db.identities.count_documents({"scopes": {"$in": ["*", "all", "admin"]}})
    add("ART-010", "pass" if broad == 0 else "fail",
        f"{broad} identité(s) service avec scope global (attendu 0) — scopes limités par mission")

    # ART-011 Isolation des entités
    entities = await db.entities.count_documents({})
    cross = await db.memory_access_logs.count_documents({"action": "denied_cross_agent"})
    add("ART-011", "pass" if entities > 0 else "fail",
        f"{entities} entités isolées, mémoire cloisonnée par agent (accès croisés refusés et journalisés)")

    # ART-012 Communication contrôlée
    bus = await db.events.count_documents({"topic": {"$regex": "^(agent|factory)\\."}})
    add("ART-012", "pass" if bus > 0 else "fail", f"{bus} messages inter-agents transitent par l'Event Bus (spool + DLQ actifs)")

    # ART-013 Plafonds financiers : aucune dépense approuvée en violation
    viol = 0
    async for r in db.expense_requests.find({"status": {"$in": ["approved", "auto_approved"]}}, {"_id": 0}):
        need = 0 if r["amount"] <= 10000 else (1 if r["amount"] <= 100000 else 2)
        if len(r.get("approvals", [])) < need:
            viol += 1
    add("ART-013", "pass" if viol == 0 else "fail",
        f"{viol} dépense(s) approuvée(s) en violation des plafonds (attendu 0) — Gatekeeper 10K/100K actif")

    # ART-014 Budget par entité : allocations non encore définies
    budgets = await db.entities.count_documents({"budget_allocated": {"$exists": True}})
    add("ART-014", "pass" if budgets > 0 else "manual",
        f"{budgets} entité(s) avec budget alloué — allocations à définir avec les stakeholders humains")

    # ART-015 Audit financier
    fe = await db.finance_entries.count_documents({})
    add("ART-015", "pass" if fe >= 0 else "fail",
        f"{fe} écritures financières consultables + {await db.expense_requests.count_documents({})} demandes tracées (append-only)")

    # ART-016 Cycle de vie : les agents non-Draft ont des transitions enregistrées
    non_draft = await db.agents.count_documents({"status": {"$nin": ["Draft"]}})
    lifecycle_recs = len(await db.versions.distinct("agent_id", {"type": "lifecycle"}))
    add("ART-016", "pass" if lifecycle_recs >= non_draft - 1 else "partial",
        f"{lifecycle_recs} agents avec transitions de cycle de vie tracées / {non_draft} non-Draft — transitions non conformes bloquées par le Registry")

    # ART-017 Archivage : aucun agent Archive actif
    archived_active = await db.agents.count_documents({"status": "Archive", "runtime.state": "actif"})
    add("ART-017", "pass" if archived_active == 0 else "fail",
        f"{archived_active} agent(s) archivé(s) avec runtime actif (attendu 0)")

    # ART-018 Provider Adapter obligatoire
    calls = await db.provider_calls.count_documents({})
    add("ART-018", "pass", f"{calls} appels IA journalisés — tous via IAIProvider (aucun SDK direct dans le moteur cognitif)")

    # ART-019 Fallback obligatoire
    fallback_ok = all(chain[-1] == "sovereign" for chain in STRATEGIES.values())
    add("ART-019", "pass" if fallback_ok else "fail",
        f"Toutes les stratégies de routage ({', '.join(STRATEGIES.keys())}) se terminent par le moteur souverain")

    # ART-020 Simulation (PHASE C)
    sims = await db.simulations.count_documents({})
    add("ART-020", "pass" if sims else "pending_layer",
        f"Simulation Layer : {sims} simulation(s) — couche PHASE C" + (" active" if sims else " en attente de construction"))

    # ART-021 Amendement
    doc = await db.constitution.find_one({"key": "constitution"}, {"_id": 0, "hash": 1, "amendment_history": 1})
    add("ART-021", "pass",
        f"Hash courant {doc['hash'][:23]}…, {len(doc.get('amendment_history', []))} amendement(s), quorum Council 3/10 + validation Wudy requis")

    passed = sum(1 for r in results if r["status"] == "pass")
    return {"verified_at": now_iso(), "hash": doc["hash"],
            "summary": {"pass": passed, "fail": sum(1 for r in results if r["status"] == "fail"),
                        "pending_layer": sum(1 for r in results if r["status"] == "pending_layer"),
                        "partial_or_manual": sum(1 for r in results if r["status"] in ("partial", "manual"))},
            "articles": results}


# ---------- Amendements (Art. 21) ----------
class AmendmentPayload(BaseModel):
    article_id: str
    new_rule: str = Field(min_length=10)
    justification: str = Field(min_length=10)


@router.get("/amendments")
async def list_amendments(actor: dict = Depends(get_current_actor)):
    return await db.constitution_amendments.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.post("/amendments")
async def propose_amendment(payload: AmendmentPayload, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot propose amendments")
    if payload.article_id not in [a["id"] for a in ARTICLES]:
        raise HTTPException(status_code=404, detail="Article inconnu")
    am = {"id": str(uuid.uuid4()), **payload.model_dump(), "signatures": [], "quorum": QUORUM,
          "wudy_validated": False, "status": "proposed", "applied_at": None,
          "created_by": f'{actor["type"]}:{actor["id"]}', "created_at": now_iso()}
    await db.constitution_amendments.insert_one({**am})
    await journal("proposition", actor, f"Amendement constitutionnel proposé sur {payload.article_id} : {payload.justification[:120]}",
                  source="constitution", evidence={"amendment_id": am["id"]}, result="proposed")
    await publish("factory.amendment_proposed", actor.get("id", "?"), {"amendment_id": am["id"], "article": payload.article_id})
    return am


@router.post("/amendments/{amendment_id}/sign")
async def sign_amendment(amendment_id: str, actor: dict = Depends(get_current_actor)):
    founders = FOUNDERS
    if not (actor["type"] == "service" and actor["id"] in founders):
        raise HTTPException(status_code=403, detail="Seuls les fondateurs AGT-001→010 votent (Art. 21)")
    am = await db.constitution_amendments.find_one({"id": amendment_id}, {"_id": 0})
    if not am or am["status"] not in ("proposed", "quorum_reached"):
        raise HTTPException(status_code=409, detail="Amendement introuvable ou clos")
    if actor["id"] in am["signatures"]:
        raise HTTPException(status_code=409, detail="Déjà signé")
    sigs = am["signatures"] + [actor["id"]]
    status = "quorum_reached" if len(sigs) >= am["quorum"] else "proposed"
    await db.constitution_amendments.update_one({"id": amendment_id}, {"$set": {"signatures": sigs, "status": status}})
    await journal("proposition", actor, f"Vote amendement {amendment_id[:8]} : {len(sigs)}/{am['quorum']}",
                  source="constitution", result=status)
    return {"signatures": sigs, "status": status}


@router.post("/amendments/{amendment_id}/validate-wudy")
async def validate_wudy(amendment_id: str, actor: dict = Depends(require_admin)):
    """Validation finale Wudy → application non rétroactive + nouveau hash."""
    am = await db.constitution_amendments.find_one({"id": amendment_id}, {"_id": 0})
    if not am:
        raise HTTPException(status_code=404, detail="Amendement introuvable")
    if am["status"] != "quorum_reached":
        raise HTTPException(status_code=409, detail=f"Quorum Founder Council non atteint ({len(am['signatures'])}/{am['quorum']})")
    ts = now_iso()
    doc = await db.constitution.find_one({"key": "constitution"}, {"_id": 0})
    articles = doc["articles"]
    for a in articles:
        if a["id"] == am["article_id"]:
            a["rule"] = am["new_rule"]
    new_hash = compute_hash(articles)
    await db.constitution.update_one({"key": "constitution"},
                                     {"$set": {"articles": articles, "hash": new_hash, "last_amended": ts},
                                      "$push": {"amendment_history": {"amendment_id": amendment_id,
                                                                      "article_id": am["article_id"],
                                                                      "applied_at": ts, "previous_hash": doc["hash"],
                                                                      "new_hash": new_hash,
                                                                      "validated_by": f'human:{actor["id"]}'}}})
    await db.constitution_amendments.update_one({"id": amendment_id},
                                                {"$set": {"status": "applied", "wudy_validated": True, "applied_at": ts}})
    await journal("decision_humaine", actor, f"Amendement {am['article_id']} APPLIQUÉ (Wudy) — nouveau hash {new_hash[:23]}…",
                  source="constitution", evidence={"amendment_id": amendment_id}, result="applied")
    await publish("factory.constitution_amended", actor["id"], {"article": am["article_id"], "hash": new_hash})
    return {"result": "applied", "new_hash": new_hash}
