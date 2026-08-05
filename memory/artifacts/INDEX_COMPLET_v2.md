# INDEX COMPLET — LIVRABLES ARCHITECTURE CVLN v2.0
## CVLN Agent Factory — Tous les documents de référence — Août 2026

---

## 📦 PHASE 0-1 — AUDIT & FONDATIONS (déjà livrés)

| # | Fichier | Description | Taille |
|---|---------|-------------|--------|
| 1 | `RAPPORT_AUDIT_CVLN_AGENT_FACTORY.md` | Rapport d'audit complet — 10 fragilités, 4 phases, 4 ADR | 15 Ko |
| 2 | `ADL_v2_0_SCHEMA.yaml` | Schéma ADL v2.0 normalisé — structure, KnowledgeSource, cycle de vie | 4.7 Ko |
| 3 | `ADL_v2_0_JSON_SCHEMA.json` | JSON Schema strict — validation machine des ADL | 10 Ko |
| 4 | `ProviderAdapterLayer.ts` | Code TypeScript — IAIProvider + KimiAdapter + ClaudeAdapter + ModelRouter | 20 Ko |
| 5 | `EXEMPLE_MIGRATION_ADL_v1_to_v2.yaml` | Migration AGT-060 — avant/après avec 9 transformations | 8.3 Ko |

---

## 🆕 PHASE 2 — 4 NOUVELLES COUCHES (cette livraison)

| # | Fichier | Description | Taille |
|---|---------|-------------|--------|
| 6 | `MISSION_OS_Specification.md` | Couche d'objectifs — Entités, OS, Key Results, Alignment Engine | 8.3 Ko |
| 7 | `SIMULATION_LAYER_Specification.md` | Couche de simulation — Intents, 3 scénarios, projections, confiance | 8.9 Ko |
| 8 | `LEARNING_LAYER_Specification.md` | Couche d'apprentissage — Cycle, Pattern Detector, Learning Score, Commons | 11 Ko |
| 9 | `CONSTITUTION_CVLN.md` | Constitution — 21 articles, table de vérification auto, format JSON exécutable | 11 Ko |
| 10 | `SYNTHESE_4_COUCHES_Architecture_v2.md` | Architecture cible complète — flux de décision, matrice d'impact, déploiement | 11 Ko |

---

## 🎯 ORDRE DE LECTURE RECOMMANDÉ

**Pour comprendre l'ensemble :**
1. `SYNTHESE_4_COUCHES_Architecture_v2.md` — Vue d'ensemble
2. `CONSTITUTION_CVLN.md` — Règles fondamentales
3. `MISSION_OS_Specification.md` — Pourquoi les agents exécutent
4. `SIMULATION_LAYER_Specification.md` — Comment évaluer avant de décider
5. `LEARNING_LAYER_Specification.md` — Comment s'améliorer après

**Pour implémenter :**
1. `ADL_v2_0_SCHEMA.yaml` + `ADL_v2_0_JSON_SCHEMA.json` — Structure des agents
2. `ProviderAdapterLayer.ts` — Code prêt à l'emploi
3. `CONSTITUTION_CVLN.md` — Vérificateurs à implémenter
4. Les 4 spécifications — Une par une, dans l'ordre Constitution → Mission OS → Simulation → Learning

---

## 📊 STATISTIQUES

- **Total de fichiers :** 10
- **Total de spécifications :** 5 nouvelles couches
- **Total de code :** 1 fichier TypeScript prêt à l'emploi
- **Total de schémas :** 2 (YAML + JSON)
- **Articles de Constitution :** 21
- **Fragilités identifiées :** 10 (2 critiques, 4 hautes, 4 moyennes)
- **Agents cibles :** 263 (176 en production + 87 à créer)

---

*Index complet — CVLN Group — Août 2026*
