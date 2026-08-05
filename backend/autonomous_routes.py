import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from database import db
from auth_utils import get_current_actor, require_admin, log_authz
from activity_journal import journal
from event_bus import publish
from gate_routes import gate_check
from notifier import notify

router = APIRouter(prefix="/autonomous", tags=["autonomous-runtime"])

RUNTIME_ACTOR = {"type": "system", "id": "autonomous-runtime", "name": "CVLN Autonomous Runtime"}

# Séparation autonomie / validation — détection déterministe d'intentions critiques (souverain, sans LLM)
CRITICAL_KEYWORDS = {
    "expense": ("dépense", "depense", "achat", "acheter", "payer", "budget", "financier", "engagement financier", "investir"),
    "external_publication": ("publier", "publication", "poster", "diffuser", "communiqué", "annonce externe"),
    "data_deletion": ("supprimer", "suppression", "effacer", "purger"),
    "governance_change": ("doctrine", "gouvernance", "recrutement", "recruter", "contrat", "stratégique", "strategique"),
}


class ModePayload(BaseModel):
    mode: str  # dry_run | live


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def detect_critical_intent(text: str) -> Optional[str]:
    low = (text or "").lower()
    for action_type, words in CRITICAL_KEYWORDS.items():
        if any(w in low for w in words):
            return action_type
    return None


async def get_mode() -> str:
    s = await db.settings.find_one({"key": "autonomous_runtime_mode"})
    return s["value"] if s else "dry_run"


@router.get("/mode")
async def read_mode(actor: dict = Depends(get_current_actor)):
    completed_dry_runs = await db.autonomous_cycles.count_documents({"mode": "dry_run", "status": "completed"})
    return {"mode": await get_mode(), "completed_dry_runs": completed_dry_runs,
            "live_available": completed_dry_runs > 0}


@router.post("/mode")
async def set_mode(payload: ModePayload, actor: dict = Depends(require_admin)):
    if payload.mode not in ("dry_run", "live"):
        raise HTTPException(status_code=400, detail="mode must be dry_run or live")
    if payload.mode == "live":
        done = await db.autonomous_cycles.count_documents({"mode": "dry_run", "status": "completed"})
        if done == 0:
            raise HTTPException(status_code=409,
                                detail="DRY RUN obligatoire : au moins un cycle dry_run complet requis avant activation live")
        decision = await gate_check(actor, "critical_production_activation",
                                    "Activation du mode LIVE de l'Autonomous Runtime CVLN",
                                    source="autonomous-runtime")
        if not decision["allowed"]:
            raise HTTPException(status_code=423, detail=decision["reason"])
    await db.settings.update_one({"key": "autonomous_runtime_mode"},
                                 {"$set": {"value": payload.mode, "updated_at": now_iso(),
                                           "updated_by": f'human:{actor["id"]}'}}, upsert=True)
    await journal("decision_humaine", actor, f"Mode Autonomous Runtime → {payload.mode}",
                  source="autonomous-runtime", result=payload.mode)
    return {"mode": payload.mode}


@router.get("/cycles")
async def list_cycles(limit: int = 20, actor: dict = Depends(get_current_actor)):
    return await db.autonomous_cycles.find({}, {"_id": 0}).sort("started_at", -1).to_list(min(limit, 100))


@router.get("/cycles/{cycle_id}")
async def get_cycle(cycle_id: str, actor: dict = Depends(get_current_actor)):
    c = await db.autonomous_cycles.find_one({"id": cycle_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Cycle not found")
    return c


@router.post("/cycle")
async def run_cycle(actor: dict = Depends(get_current_actor)):
    """Cycle autonome gouverné 9 étapes. Pas une IA libre : un runtime déterministe, interne, traçable."""
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot run cycles")
    if actor["type"] == "service" and actor["id"] != "AGT-000":
        raise HTTPException(status_code=403, detail="Only AGT-000 or humans (operator/admin) run cycles")

    mode = await get_mode()
    dry = mode == "dry_run"
    number = await db.autonomous_cycles.count_documents({}) + 1
    cycle = {"id": str(uuid.uuid4()), "number": number, "mode": mode, "status": "running",
             "triggered_by": f'{actor["type"]}:{actor["id"]}',
             "started_at": now_iso(), "finished_at": None,
             "steps": [], "actions_prepared": [], "actions_executed": [],
             "actions_blocked": [], "validations_requested": [], "errors": [], "summary": ""}
    await db.autonomous_cycles.insert_one({**cycle})
    cycle.pop("_id", None)

    def step(n, name, detail):
        cycle["steps"].append({"step": n, "name": name, "detail": detail, "timestamp": now_iso()})

    try:
        # 1. Observer l'état système
        observations = {
            "agents_by_runtime": {}, "open_tasks": await db.agent_tasks.count_documents({"status": {"$in": ["open", "in_progress"]}}),
            "pending_validations": await db.validation_requests.count_documents({"status": "pending"}),
            "missions_in_progress": await db.missions.count_documents({"status": {"$in": ["assigned", "in_progress"]}}),
            "missions_delivered_awaiting": await db.missions.count_documents({"status": "delivered"}),
        }
        async for a in db.agents.find({}, {"_id": 0, "runtime.state": 1}):
            st = (a.get("runtime") or {}).get("state", "sommeil")
            observations["agents_by_runtime"][st] = observations["agents_by_runtime"].get(st, 0) + 1
        cycle["observations"] = observations
        step(1, "observer", f"{observations['open_tasks']} tâches ouvertes, "
                            f"{observations['pending_validations']} validations en attente, "
                            f"{observations['missions_in_progress']} missions en cours")
        await journal("observation", RUNTIME_ACTOR, f"Cycle #{number} — observation système : {step_detail(observations)}",
                      source="autonomous-runtime", evidence={"cycle_id": cycle["id"], **observations}, result="observed")

        # 2. Lire les objectifs actifs
        active = await db.objectives.find({"status": "active"}, {"_id": 0}).to_list(200)
        done_ids = {o["id"] async for o in db.objectives.find({"status": "done"}, {"_id": 0, "id": 1})}
        pursuable = [o for o in active if all(d in done_ids for d in o.get("dependencies", []))]
        blocked = [o for o in active if o not in pursuable]
        step(2, "lire_objectifs", f"{len(pursuable)} objectif(s) poursuivable(s), {len(blocked)} bloqué(s) par dépendances")

        # 3. Prioriser (P0 > P1 > P2, activité la plus ancienne d'abord)
        prio_weight = {"P0": 0, "P1": 1, "P2": 2}
        pursuable.sort(key=lambda o: (prio_weight.get(o["priority"], 9), o.get("last_activity", "")))
        top = pursuable[:5]
        step(3, "prioriser", f"Top {len(top)} : {', '.join(o['code'] for o in top)}" if top else "Aucun objectif à prioriser")

        # 4. Analyser chaque objectif prioritaire
        analyses = []
        for o in top:
            owner_agent = await db.agents.find_one({"id": o["owner"]}, {"_id": 0, "id": 1, "runtime.state": 1}) \
                if o["owner"].startswith("AGT-") else None
            owner_state = (owner_agent or {}).get("runtime", {}).get("state", "sommeil") if owner_agent else None
            existing_task = await db.agent_tasks.find_one(
                {"agent_id": o["owner"], "title": {"$regex": f"^\\[OBJ\\] {o['code']}"},
                 "status": {"$in": ["open", "in_progress"]}}, {"_id": 0, "id": 1})
            critical = detect_critical_intent(o.get("next_action", ""))
            analyses.append({"objective": o["code"], "owner": o["owner"], "owner_state": owner_state,
                             "next_action": o.get("next_action", ""), "has_open_task": bool(existing_task),
                             "critical_intent": critical})
        cycle["analyses"] = analyses
        step(4, "analyser", f"{len(analyses)} objectif(s) analysé(s), "
                            f"{sum(1 for a in analyses if a['critical_intent'])} intention(s) critique(s) détectée(s)")
        if analyses:
            await journal("analyse", RUNTIME_ACTOR,
                          f"Cycle #{number} — analyse de {len(analyses)} objectif(s) prioritaire(s)",
                          source="autonomous-runtime", evidence={"cycle_id": cycle["id"], "analyses": analyses},
                          result="analyzed")

        # 5. Préparer les actions possibles
        for a in analyses:
            if a["critical_intent"]:
                cycle["actions_prepared"].append({
                    "type": "escalate_validation", "objective": a["objective"],
                    "action_type": a["critical_intent"],
                    "detail": f"Action critique détectée ({a['critical_intent']}) : « {a['next_action']} » — validation Laurent requise"})
                continue
            if a["owner_state"] == "sommeil" and a["owner"]:
                cycle["actions_prepared"].append({
                    "type": "wake_agent", "objective": a["objective"], "agent_id": a["owner"],
                    "detail": f"Réveiller {a['owner']} (propriétaire de {a['objective']} endormi)"})
            if not a["has_open_task"] and a["next_action"]:
                cycle["actions_prepared"].append({
                    "type": "create_task", "objective": a["objective"], "agent_id": a["owner"],
                    "detail": f"Matérialiser la prochaine action de {a['objective']} en tâche : « {a['next_action'][:80]} »"})
        step(5, "preparer", f"{len(cycle['actions_prepared'])} action(s) préparée(s)")
        for ap in cycle["actions_prepared"]:
            await journal("proposition", RUNTIME_ACTOR, f"Cycle #{number} — action préparée : {ap['detail']}",
                          source="autonomous-runtime",
                          agent_id=ap.get("agent_id"), evidence={"cycle_id": cycle["id"], **ap}, result="prepared")

        # 6-7. Vérifier permissions puis exécuter uniquement si autorisé
        for ap in cycle["actions_prepared"]:
            if dry:
                simulated = "would_escalate_to_laurent" if ap["type"] == "escalate_validation" else "would_execute"
                cycle["actions_executed" if simulated == "would_execute" else "actions_blocked"].append(
                    {**ap, "decision": simulated, "dry_run": True})
                continue
            if ap["type"] == "escalate_validation":
                decision = await gate_check(RUNTIME_ACTOR, ap["action_type"], ap["detail"],
                                            agent_id=ap.get("agent_id"), source="autonomous-runtime")
                cycle["actions_blocked"].append({**ap, "decision": decision["decision"],
                                                 "validation_request_id": decision.get("validation_request_id")})
                if decision.get("validation_request_id"):
                    cycle["validations_requested"].append(decision["validation_request_id"])
                continue
            decision = await gate_check(RUNTIME_ACTOR, "prepare", ap["detail"],
                                        agent_id=ap.get("agent_id"), source="autonomous-runtime")
            if not decision["allowed"]:
                cycle["actions_blocked"].append({**ap, "decision": decision["decision"]})
                continue
            ts = now_iso()
            if ap["type"] == "wake_agent":
                await db.agents.update_one({"id": ap["agent_id"]},
                                           {"$set": {"runtime": {"state": "actif", "since": ts, "initialized": True,
                                                                 "previous_state": "sommeil",
                                                                 "note": f"réveillé par cycle autonome #{number}",
                                                                 "last_transition_by": "system:autonomous-runtime"},
                                                     "updated_at": ts}})
                await publish("agent.woken", "autonomous-runtime", {"agent_id": ap["agent_id"], "cycle": number})
            elif ap["type"] == "create_task":
                obj = await db.objectives.find_one({"code": ap["objective"]}, {"_id": 0})
                await db.agent_tasks.insert_one({
                    "id": str(uuid.uuid4()), "agent_id": ap["agent_id"], "entity": "",
                    "title": f"[OBJ] {ap['objective']} — {obj['next_action'][:100]}",
                    "description": f"Tâche générée par le cycle autonome #{number} depuis l'objectif {ap['objective']} : {obj['title']}",
                    "priority": obj["priority"], "status": "open", "objective_id": obj["id"],
                    "created_by": "system:autonomous-runtime", "created_at": ts, "updated_at": ts})
                await db.objectives.update_one({"code": ap["objective"]}, {"$set": {"last_activity": ts}})
            cycle["actions_executed"].append({**ap, "decision": "executed"})
            await journal("action_executee", RUNTIME_ACTOR, f"Cycle #{number} — {ap['detail']}",
                          source="autonomous-runtime", agent_id=ap.get("agent_id"),
                          evidence={"cycle_id": cycle["id"], **ap}, result="executed")
        step(6, "verifier_permissions", f"{len(cycle['actions_executed'])} autorisée(s), "
                                        f"{len(cycle['actions_blocked'])} bloquée(s)/escaladée(s)")
        step(7, "executer", "DRY RUN — aucune modification métier appliquée" if dry
             else f"{len(cycle['actions_executed'])} action(s) exécutée(s)")

        # 8. Journaliser (fil rouge : chaque étape a déjà journalisé) + 9. Closing
        cycle["status"] = "completed"
        cycle["finished_at"] = now_iso()
        cycle["summary"] = (f"Cycle #{number} ({mode}) : {len(top)} objectif(s) traité(s), "
                            f"{len(cycle['actions_prepared'])} action(s) préparée(s), "
                            f"{len(cycle['actions_executed'])} exécutée(s)"
                            + (" [simulation]" if dry else "")
                            + f", {len(cycle['actions_blocked'])} bloquée(s)/escaladée(s), "
                            f"{len(cycle['validations_requested'])} validation(s) demandée(s) à Laurent.")
        step(8, "journaliser", "Toutes les étapes tracées dans l'Activity Journal v2")
        step(9, "closing", cycle["summary"])
        await db.autonomous_cycles.update_one({"id": cycle["id"]}, {"$set": {k: cycle[k] for k in
                                              ("status", "finished_at", "steps", "observations", "analyses",
                                               "actions_prepared", "actions_executed", "actions_blocked",
                                               "validations_requested", "summary")}})
        await journal("cloture", RUNTIME_ACTOR, cycle["summary"], source="autonomous-runtime",
                      evidence={"cycle_id": cycle["id"], "mode": mode}, result="completed")
        await log_authz(actor, "autonomous_cycle", cycle["id"], True, f"cycle #{number} {mode}")
        await publish("factory.cycle_completed", "autonomous-runtime",
                      {"cycle_id": cycle["id"], "number": number, "mode": mode})
        if cycle["validations_requested"]:
            await notify(2, "Cycle autonome — validations requises",
                         f"Le cycle #{number} a escaladé {len(cycle['validations_requested'])} action(s) critique(s) "
                         f"nécessitant votre validation.", source="autonomous-runtime")
        return cycle

    except Exception as e:
        cycle["status"] = "error"
        cycle["finished_at"] = now_iso()
        cycle["errors"].append(str(e)[:300])
        await db.autonomous_cycles.update_one({"id": cycle["id"]},
                                              {"$set": {"status": "error", "finished_at": cycle["finished_at"],
                                                        "errors": cycle["errors"], "steps": cycle["steps"]}})
        await journal("erreur", RUNTIME_ACTOR, f"Cycle #{number} en erreur : {str(e)[:200]}",
                      source="autonomous-runtime", evidence={"cycle_id": cycle["id"]}, result="error")
        raise HTTPException(status_code=500, detail=f"Cycle failed: {str(e)[:200]}")


def step_detail(obs: dict) -> str:
    return (f"{obs['open_tasks']} tâches ouvertes, {obs['pending_validations']} validations en attente, "
            f"{obs['missions_in_progress']} missions en cours")


async def reconcile_interrupted_cycles():
    """Continuité : au démarrage, les cycles restés 'running' sont marqués interrompus (repris au prochain cycle)."""
    ts = now_iso()
    stale = await db.autonomous_cycles.count_documents({"status": "running"})
    if stale:
        await db.autonomous_cycles.update_many({"status": "running"},
                                               {"$set": {"status": "interrupted", "finished_at": ts}})
        await journal("observation", RUNTIME_ACTOR,
                      f"Reprise : {stale} cycle(s) interrompu(s) détecté(s) et marqué(s) — "
                      f"le prochain cycle reprendra les objectifs là où ils en étaient (checkpoints/objectifs persistants)",
                      source="autonomous-runtime", result="reconciled")
