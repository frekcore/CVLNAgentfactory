# PRD — CVLN Agent Factory (Agent Operating System Layer)

## Problem statement (original)
Plateforme Palier 3 (V1 : Registry + ADL) : système d'exploitation pour agents IA — backend réel des 5 Core Services (Registry, Identity, Memory, Event Bus, Monitoring) + console web React de pilotage. Indépendance fournisseur (pas d'exécution LLM en V1). Extension demandée : Agent Generator Engine (génération industrielle d'agents depuis un catalogue maître, pas de création manuelle des 283 agents), Doctrine Engine (règles CVLN héritées automatiquement), endpoints API réservés pour les systèmes externes indépendants (Laurent.ia, KORA, FREK, Kiltikonet, LabelOS, Good Mood, CVL Academy, CVLN Central).

## User choices
- Interface FR/EN dès le départ (toggle dans la console)
- Endpoint placeholder réservé pour Laurent.ia (501)
- 11 agents fondateurs fournis par Laurent : AGT-000 (CVLN Agent Architect) → AGT-010, seedés en Production
- Admin : laurent@cvln.fr / CVLNfactory2026! · Token service AGT-000 : voir /app/memory/test_credentials.md

## Architecture
- Backend FastAPI modulaire (un module par Core Service, déployables ensemble) : server.py, registry_routes.py, identity_routes.py, core_routes.py (events/memory/audit/monitoring), generator_routes.py, doctrine.py, external_routes.py, adl_schema.py (Pydantic), auth_utils.py (JWT + tokens service), event_bus.py, seed_data.py
- MongoDB collections : agents, versions (historique immuable version+lifecycle), events, identities, users, memory_entries, memory_access_logs, audit_logs, catalog_entries, doctrine
- Frontend React (JS/JSX + Tailwind + shadcn base, Phosphor icons, thème dark void/cyan) : pages Dashboard, Agents, AgentDetail (fiche/ADL/timeline/diff), ADLEditor, Generator, Doctrine, Events, Audit, Monitoring, Users + i18n FR/EN + AuthContext

## Règles de gouvernance encodées
- Seul AGT-000 (identité de service) ou un admin écrit dans le Registry (require_registry_writer)
- Beta → Production exige une validation humaine admin
- Aucune communication inter-pôle hors Event Bus (publish restreint + topics normés)
- Chaque décision d'autorisation journalisée (audit_logs)
- Monitoring lecture seule stricte

## Implémenté (2026-06 → 2026-07)
- [x] Phase 1 : Schéma ADL Pydantic + Registry (CRUD, cycle de vie, versions, doublons id/nom/mission-similarité) + seed 11 fondateurs
- [x] Phase 2 : Identity (JWT 8h, rôles admin/opérateur/lecteur, identités de service svc_, journalisation authz)
- [x] Phase 3 : Console web complète (annuaire filtrable, fiches, éditeur ADL validation temps réel + compile + import/export YAML + diff versions, timeline)
- [x] Phase 4 : Event Bus (journal complet, publish contrôlé) + Memory (espaces isolés, journal d'accès) + journaux d'audit console
- [x] Phase 5 : Monitoring (santé 5 services, dashboard supervision, alertes)
- [x] Agent Generator Engine : catalogue maître + pipeline auto 11 étapes (analyse → ADL → doctrine → doublon → ID auto → identité → permissions → mémoire → events → Registry → cycle de vie jusqu'à Beta / Production si admin)
- [x] Daily Closing Service (2026-07-10) : rapports quotidiens par agent (isolation identité de service), pipeline de clôture AGT-000 (collecte → contrôle anomalies → snapshots mémoire versionnés 3 niveaux session/operational/strategic sans suppression → états quotidiens Registry → Daily Report global → CVLN Daily Executive Report pour Laurent), Morning Briefing au démarrage, événements daily.closing.started / daily.report.generated / agent.daily.completed / memory.snapshot.created / system.ready.next.day, clôture idempotente (409), page console "Clôture quotidienne" — testé iteration_2 (100%)
- [x] Autonomous Workforce Layer (2026-07-10, testé iteration_3 100%) :
  - Entity Registry (Business Reality Layer) : 10 entités CVLN seedées, CRUD, association d'agents (page Entités)
  - 5 agents pilotes opérationnels AGT-011→AGT-015 (Digital CEO, Digital CFO, Knowledge Manager, Operations, Marketing Strategy) seedés en Beta avant industrialisation
  - Niveaux d'autonomie 1-4 (observation → recommandation → exécution contrôlée → autonomie opérationnelle), L3-L4 réservés à la validation humaine admin
  - Agent Workspace : tâches (P0-P2, open/in_progress/done/blocked), briefing quotidien par agent, mémoire, connaissances (onglet Workspace de la fiche agent)
  - Financial Intelligence Layer : écritures cost/revenue, ROI par agent/entité, prévision 30j (page Finance)
  - Knowledge Sovereignty Layer : ingestion (Obsidian/docs/archives ChatGPT-Claude/MD/PDF), classification auto 7 catégories, versionnée, routage vers la mémoire strategic des agents cibles via AGT-002, validation admin (page Connaissances)
  - Improvement Loop : propositions d'évolution (improve_agent/create_agent/modify_workflow/optimize_procedure) proposables par AGT-000, décision humaine admin uniquement
  - Founder Control Center : vue souveraine pour Laurent (état groupe, validations en attente, finance, dernière clôture)
  - Industrial Mode : import en masse du catalogue maître (CSV avec listes ';' ou JSON) + génération batch all_pending jusqu'à Beta "Ready For Assignment"
- [x] Doctrine Engine : 6 sections de règles (architecture, sécurité, communication, autonomie, gouvernance, stratégie), héritage auto, /api/doctrine/check
- [x] 8 endpoints externes réservés 501 (/api/external/*, /api/laurent-ia)
- [x] Testing agent iteration_1 : 100% backend + frontend

## Backlog priorisé
- P0 : rien de bloquant
- P1 : lockout brute-force (5 tentatives / 15 min) sur le login ; CORS origins explicites (actuellement * — cookies inutilisés côté cross-origin, Bearer utilisé) ; validation enum autonomy_level au niveau du schéma ADL (actuellement contrôlé par doctrine seulement)
- P2 : pagination annuaire (>284 agents), import CSV/JSON en masse du catalogue maître, éditeur ADL vue formulaire bidirectionnelle, refresh token, graphe interactif de l'écosystème (D3), contrats d'interface réels des systèmes externes (V2), couche d'exécution LLM provider-agnostic (V2)

## Next tasks
1. Import réel du catalogue maître des 283 agents (l'infrastructure bulk-import + generate-batch est prête — attendre la validation du pilote par Laurent)
2. Scheduler automatique de clôture (cron 23h59 UTC) + soumission auto des rapports par les agents au Runtime (V2)
3. Contrats d'interface réels vers les entités (Laurent.ia, KORA, FREK… — endpoints 501 réservés en place)
4. Brute-force lockout + refresh token
5. UX : multi-select agents cibles (Knowledge) en composant chips
