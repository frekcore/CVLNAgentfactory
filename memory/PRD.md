# PRD — CVLN Agent Factory (Sovereign Cognitive Operating System)

## Vision
Infrastructure cognitive opérationnelle **souveraine** du groupe CVLN (Laurent, fondateur) : mémoire, doctrine, gouvernance, orchestration, agents, objectifs, journaux, runtime et continuité propriétaires. Les LLM (Emergent/Anthropic/etc.) sont des **accélérateurs interchangeables**, jamais le cœur. Capable de piloter plusieurs entités : Factory Maker Studio, KORA, FREKCORE, etc.

## Stack
FastAPI + MongoDB (Motor) + React (Tailwind + Shadcn, sonner pour les toasts) + JWT (admin/operator/reader) + identités service `svc_` + PWA + Telegram + Emergent LLM key (via Provider Adapter Layer uniquement).

## Utilisateur
- Admin : laurent@cvln.fr / CVLNfactory2026! (voir /app/memory/test_credentials.md)
- Service AGT-000 : Bearer svc_agt000_9f2e7c1a4b8d6f3e0a5c2d7b1e4f8a6c

## Mission en cours : CVLN SOVEREIGN RUNTIME ARCHITECTURE v1.0 (protocole CVLN-GOV-AUDIT-001)
Conditions permanentes de Laurent :
- Jamais de promotion en masse : chaque agent suit Draft→Prototype→Beta(Staging)→Production individuellement ; **la validation Production est réservée à Laurent depuis la console**
- Founder Council = fallback uniquement (AGT-000 reste nominal)
- DRY RUN obligatoire avant tout mode live du runtime autonome
- ADR obligatoires pour chaque adaptation souveraine
- Réutiliser l'existant, zéro doublon, rapport d'impact avant modif, journaliser tout, validation Laurent pour : dépenses, contrats, publication externe, suppression, stratégie, recrutement, doctrine, activation production

## Réalisé (tout testé, iterations 5→9, 100%)
- **PHASE 0** (it.5) : fix bug Telegram (200 {pushed, push_error}), snapshot pré-évolution
- **PHASE 1** (it.6) : Permission Gate v2 (6 niveaux, règles agent>mission>action, 6 actions critiques non contournables, escalade auto → validation_requests + Telegram) + Activity Journal v2 (8 types, /journal/unified fusion lecture avec audit_logs+events) + page Gouvernance
- **PHASE 2** (it.7) : Doctrine Registry v2 (statuts proposition→validee→active→archivee, versions immuables, 21 règles legacy importées, validateur humain) + Memory Layer v2 (scopes doctrinal/learning + source/confidence/provenance/validation, même collection) + Objective Registry (OBJ-NNN, next_action, dépendances, /objectives/pursue) + pages Objectifs & Doctrine v2
- **PHASE 3** (it.8) : Agent Runtime (6 états actif/sommeil/attente_validation/erreur/suspendu/termine, transitions strictes, checkpoints auto, wake avec restauration complète + missing_information signalé, transitions critiques via Gate HTTP 423, recovery au démarrage) + panneau Runtime fiche agent
- **PHASE 4 + RAPPORT AUDIT** (it.9, 34/34 + 65 non-rég) :
  - Autonomous Runtime gouverné : cycle 9 étapes déterministe (observer→closing), mode dry_run par défaut (live exige ≥1 dry run + gate), détection d'intentions critiques par mots-clés (acheter/publier/supprimer/…) → escalade Laurent, reconcile des cycles interrompus au boot, page /runtime
  - S0.1 ADL v2.0 : JSON Schema Draft-07 (fichiers Laurent), /adl/v2/validate + /migrate-preview (jamais de migration en masse)
  - S0.2 KnowledgeSource + SovereignLexicalStore (chunks+recherche lexicale Mongo, interface IVectorStore → Qdrant plus tard, ADR-005)
  - S0.3 Audit Pôle 0b : AGT-011→015 documentés (pole_0b_audit), aucun doublon — /app/memory/artifacts/AUDIT_POLE_0B.md
  - Inventaire complet : **176 agents AGT-000→175** (20 Pôle 1 créés → Beta, 135 Draft de Laurent intacts, 14 Production actifs)
  - Provider Adapter Layer (ADR-002) : IAIProvider + ModelRouter stratégies quality/cost/sovereign_only, fallback souverain garanti, modèles claude-sonnet-4-6 / gpt-5.4 / gemini-3.1-pro-preview, journal provider_calls
  - Founder Council (ADR-001) : quorum 3 fondateurs AGT-001→010, uniquement si AGT-000 indisponible (409 sinon), approbation à usage unique via header X-Council-Approval
  - Event Bus résilient (ADR-006) : spool local JSONL + DLQ + /events/replay-spool
  - Auto-healing (F-008) : monitoring publie monitoring.action (throttle 10min), /monitoring/heal répare erreur→actif depuis checkpoint
  - Secrets (ADR-007) : rotation tokens service + TTL expires_at + audit
  - Financial Gatekeeper (F-003) : ≤10K€ auto / ≤100K€ 1 validation / >100K€ 2 validateurs distincts (409 si même admin)
- ADR : /app/memory/adr/ADR-005-006-007-adaptations-souveraines.md · Artefacts Laurent : /app/memory/artifacts/

## Backlog priorisé
- P0 FAIT (2026-08) : VAGUE 1 connectivité (it.11, 14/14 + 145 non-rég) : L1 alignment⇄cycle (éval seule), L2 file financière unique gate→Gatekeeper, L3 propositions unifiées (evolution 410→doctrine_registry, quorum importé de founder_council). PHASE A Constitution (it.10) + PHASE B Mission OS livrées. Blueprint intégration écosystème 10 entités sauvegardé (/app/memory/artifacts/INTEGRATION_ECOSYSTEME.md).
- P0 FAIT (2026-08-05) : VAGUE 2 (it.12, 15/15 + 265 non-rég, 0 bug) : L4 KnowledgeSources⇄chat (top-3 lexical <200ms, seuil 0.3, signalement si réponse hors mémoire souveraine, flag disable_knowledge_search) ; L5 knowledge_sources au bundle wake (≤1Mo, testé AGT-060, remis en sommeil) ; L6 dual-write knowledge_items→sources (consistency = alerte seule, 0 incohérence, 4 legacy pré-transition en lecture) ; L7 briefing/closing governance lecture seule (Gate+dépenses+amendements pending, alignment du jour). Entités TCV+SAYD créées draft (0 agent/0 budget) + CC2027 = SO-011 rattaché à Kiltikonet (règle Laurent « une entité = une seule source de vérité », pas de doublon). ART-005 ✅, constitution fail 0. Rapport : /app/memory/artifacts/RAPPORT_VAGUE2_P1.md · Comparaison L4 : VAGUE2_L4_COMPARAISON.md. Fix bonus : notifier 500 Telegram (try/except discovery), generate-batch 500 (ValidationError → failures), tests legacy Evolution alignés circuit 410.
- **P1 SUIVANT (validation Laurent requise)** : Phase C Simulation Layer (6 intents, 3 scénarios, heuristiques) ; Phase D Learning Layer (async au closing, Commons lecture seule, score<50→notif sans action auto) ; Phase E page Sovereign (4 onglets : Constitution/Mission OS/Simulations/Learning)
- P2 reporté par Laurent : Event Bus consumers, verify auto planifié, ART-016 garde lifecycle, SO⇄OBJ (en Phase B suite)
- P0 : Laurent valide les promotions Beta→Production depuis la console (pipeline prêt) ; test quorum complet Founder Council (nécessite tokens fondateurs AGT-001→010)
- P1 : Déploiement multi-entités (Objectif 4 du PROMPT MASTER) : missions+agents+objectifs par entité KORA / FREKCORE / Factory Maker ; Morning Briefing étendu (ce qui a changé/avance/bloque/attend Laurent) — PHASE 6 initiale
- P1 : Mode souverain complet (Objectif 7) : export complet des données (endpoint dump), réplication
- P2 : Migration ADL v2.0 agent par agent (previews prêts, données v2 à compléter : vision, kpi targets) ; création des 108 agents restants non nommés ; purge périodique runtime_recoveries ; scheduler de cycles autonomes (cron interne)
- P2 : Qdrant/NATS/Vault sur infrastructure dédiée CVLN (interfaces prêtes, ADR rédigés)

## Notes techniques
- pytest : lancer les suites en série (-n 0) avec REACT_APP_BACKEND_URL exporté — 8 suites dans /app/backend/tests/ (282 tests, skips légitimes : 1 clôture/jour, doublons agents QA persistés)
- Ne JAMAIS éditer de fichier backend pendant qu'une suite pytest tourne (hot reload → 500 en plein run)
- Le proxy avale les corps des réponses 502 → toujours renvoyer 200 structuré pour les échecs d'intégrations externes
- Telegram : push échoue tant que Laurent n'a pas envoyé /start au bot (persisted_only, comportement propre)
- AGT-034 token roté avec TTL 1h par les tests (expiré) ; AGT-035 roté TTL 720h
