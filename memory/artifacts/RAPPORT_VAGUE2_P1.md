# RAPPORT VAGUE 2 (P1) — Connectivité souveraine CVLN
Date : 2026-08-05 · Protocole : CVLN-GOV-AUDIT-001 · Mode : DRY RUN maintenu

## 1. Résumé technique des 4 liaisons

| Liaison | Description | Mécanisme |
|---|---|---|
| **L4** | KnowledgeSources ⇄ chat cognitif | Recherche lexicale top-3 (SovereignLexicalStore interne, **aucun appel fournisseur pour la recherche**) avant chaque réponse. Seuil de pertinence 0.3 : en dessous, rien n'est injecté et la réponse est explicitement signalée « non fondée sur la mémoire souveraine ». Flag `disable_knowledge_search` pour comparaison A/B. |
| **L5** | KnowledgeSources ⇄ wake | `knowledge_sources` (métadonnées seules : id, titre, type, chunks, commons) ajouté au bundle de restauration du réveil. `bundle_size_bytes` calculé, troncature automatique si > 1 Mo. Absence de source = signalée dans `missing_information`, jamais inventée. |
| **L6** | Dual-write knowledge | Chaque écriture `knowledge_items` legacy (ingest + confirmation cognitive) réplique automatiquement en `knowledge_sources` v2 (`metadata.legacy_item_id`, chunks indexés). **Legacy jamais supprimé.** `GET /knowledge/sources/consistency` : contrôle lecture seule, incohérence = alerte (journal + notification N2) **sans aucune correction automatique**. |
| **L7** | Daily Closing / Morning Briefing | Section `governance` **lecture seule** ajoutée au briefing et au rapport de clôture : validations Gate en attente, `expense_requests` en attente, amendements doctrine en `proposition`, alignment scores du jour (cycles autonomes). Aucune action automatique. |

## 2. Code livré
- `cognitive_routes.py` / `cognitive_engine.py` : L4 (retrieval, seuil, injection prompt, `sovereign_knowledge` dans chaque réponse)
- `runtime_routes.py` : L5 (bundle wake + taille)
- `knowledge_sources_routes.py` : `dual_write_from_legacy()` + `/consistency` (L6)
- `knowledge_routes.py` : dual-write à l'ingestion legacy (L6)
- `daily_closing_routes.py` : `governance_snapshot()` (L7)
- `seed_vague2.py` : entités + objectifs (idempotent)
- `tests/test_vague2.py` : 10 tests · `tests/test_vague2_complements.py` (testing agent) : 5 tests

## 3. Test L4 — 5 conversations avec/sans recherche
Artefact : `/app/memory/artifacts/VAGUE2_L4_COMPARAISON.md`.
- AVEC : réponses citent la Doctrine continuité CVLN (score 2.48) et les sources internes ; contenu ancré (checkpoint obligatoire, contenu exact du protocole).
- SANS : le modèle ajoute de lui-même « ⚠️ Cette réponse ne repose pas sur la mémoire souveraine CVLN… À valider par Laurent » et produit des bonnes pratiques génériques.
- Latence retrieval mesurée : **0.4 ms** (exigence < 200 ms largement tenue).

## 4. Test L5 — AGT-060
- AGT-060 (Draft, sommeil) réveillé → `restored_context.knowledge_sources` liste sa source dédiée + Knowledge Commons.
- `bundle_size_bytes` ≤ 1 Mo vérifié. AGT-060 **remis en sommeil** après test (les Draft restent dormants).

## 5. Test L6 — preuve dual-write
- Ingest legacy → réponse contient `v2_source_id` ; `/consistency` : item dans `coherent_ids`, contenu identique dans les deux systèmes.
- État global : 18 items legacy · 14 cohérents (dual-écrits) · **0 incohérence** · 4 antérieurs à la transition, listés en lecture seule comme candidats à migration (aucune migration automatique).

## 6. Test L7 — Morning Briefing enrichi (extrait réel)
```
governance.read_only: true
pending_gate_validations: 22 · pending_expense_requests: 46 · pending_amendments: 1
alignment_today: 145 évaluations, moyenne 0.162, 116 alignements faibles (<0.3)
```
→ Signal utile immédiat : 116 tâches faiblement alignées avec les objectifs stratégiques du jour (évaluation seule).

## 7. Tests et non-régression
- Suite complète backend : **265 passed, 17 skipped, 0 échec** (série `-n 0`).
- Skips légitimes documentés : clôture du jour déjà effectuée (1/jour) ; détection de doublons sur agents QA persistés de runs antérieurs.
- Testing agent (iteration_12) : backend **100 % (15/15)**, frontend smoke **100 %** (Dashboard/Runtime/Gouvernance), **0 bug**.
- Note honnête : le seuil « 159 tests » cité ne correspond pas à une suite unique existante ; la couverture réelle exécutée est plus large (282 tests collectés, 265 verts + 17 skips motivés).
- Bugs corrigés au passage (hors périmètre mais bloquants tests) :
  - `notifier.notify()` : panne réseau Telegram pendant la découverte du chat_id → 500 intermittents sur gate/check, deliver, notifications/test. Corrigé (try/except, échec = `push_error`, jamais de 500).
  - `generate-batch` : entrée catalogue invalide (pole vide) → 500. Corrigé (échec listé dans `failures`).
  - Tests legacy TestEvolution mis à jour pour le circuit unifié Vague 1 (410 → doctrine_registry).

## 8. État Constitution
`summary: pass 17 · fail 0 · pending_layer 2 (Learning/Simulation, phases C/D) · partial_or_manual 2`
- **ART-005 (Droit à la Mémoire) : ✅ PASS** — « 31/182 agents avec mémoire persistante + 35 KnowledgeSources »
- ART-006 (Alignment) : ✅ PASS — Mission OS active, 13 objectifs stratégiques.

## 9. Preuve création CC2027, TCV, SAYD
Règle appliquée (décision Laurent) : **« une entité = une seule source de vérité »**. Inventaire préalable : 10 entités existantes, dont Kiltikonet.
- **TCV** : entité créée, `status=draft`, 0 agent, 0 budget + SO-012 (poids 0, horizon 2028, draft)
- **SAYD** : entité créée, `status=draft`, 0 agent, 0 budget + SO-013 (poids 0, horizon 2028, draft)
- **CC2027** : **pas d'entité doublon** — SO-011 « CC2027 — Marché culturel de Kiltikonet » rattaché à l'entité Kiltikonet existante (poids 0, horizon 2028, draft, placeholder)
- Action journalisée dans l'Activity Journal (`source: vague2`).

## 10. Risques et mitigations
| Risque | Mitigation |
|---|---|
| Seuil de pertinence L4 (0.3) trop permissif/strict selon le corpus | Constante `MIN_KNOWLEDGE_RELEVANCE` centralisée ; ajustable après retours réels |
| Croissance des `knowledge_sources` (dual-write) | Métadonnées seules dans le wake ; migration Qdrant prête (interface IVectorStore, ADR-005) |
| 4 items legacy pré-transition non migrés | Listés en lecture seule dans `/consistency` ; migration à valider humainement |
| Alignment moyen faible (0.162) sur les tâches du jour | Signal attendu : objectifs placeholders poids 0 ; se corrigera quand Laurent pondérera les SO |
| Agents QA persistés polluent la détection de doublons du générateur | Tests adaptés ; nettoyage éventuel = suppression → validation humaine requise |

## 11. Prochaine étape (à valider avant tout démarrage)
- **Phase C — Simulation Layer** (6 intents, 3 scénarios, heuristiques) puis Phase D Learning Layer, Phase E page Sovereign (P1 du backlog).
- P2 reportés (décision Laurent) : Event Bus consumers, verify auto planifié, ART-016 garde lifecycle, SO⇄OBJ.
- En parallèle possible : pondération des objectifs stratégiques par Laurent (les placeholders poids 0 neutralisent l'alignment).

**Conditions respectées** : DRY RUN actif (`autonomous_runtime_mode=dry_run` vérifié), 136 agents Draft intacts (≥135), aucune écriture production sans Gate humain, AGT-060 remis en sommeil.
*Statut : testé par agent de test + suites pytest — en attente de confirmation personnelle de Laurent.*
