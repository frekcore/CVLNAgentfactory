# SIMULATION LAYER — Moteur de Scénarios
## Spécification Technique v1.0 — CVLN Agent Factory

---

## 1. CONCEPT

Avant qu'une décision importante ne soit exécutée (même en dry_run), la Simulation Layer génère **plusieurs scénarios** et leurs impacts prévus sur :
- **Budget** (coût direct, coût opportunité, ROI estimé)
- **Utilisateurs** (acquisition, rétention, churn, satisfaction)
- **Risques** (technique, juridique, réputation, opérationnel)
- **Dépendances** (quels autres agents/services sont impactés)
- **Temps** (durée estimée, points de blocage potentiels)

Le système présente les scénarios à l'utilisateur (ou à Agent 000) avec une **recommandation** et un **niveau de confiance**.

---

## 2. DÉCLENCHEURS

Une simulation est automatiquement déclenchée si la tâche contient un **intent critique** :

| Intent | Exemple de déclencheur | Scénarios générés |
|--------|------------------------|-------------------|
| `DEPLOY` | "Déployer en production", "Activer le runtime" | 3 scénarios : rollback, progressive, full |
| `BUDGET` | "Allouer", "Acheter", "Investir", "Dépenser" | 3 scénarios : conservateur, nominal, optimiste |
| `DELETE` | "Supprimer", "Archiver", "Retirer" | 3 scénarios : soft delete, hard delete, migration |
| `PUBLISH` | "Publier", "Rendre public", "Communiquer" | 3 scénarios : preview interne, beta restreinte, public |
| `HIRE` | "Créer un agent", "Recruter", "Engager" | 3 scénarios : minimal, standard, premium |
| `MODIFY_CORE` | "Modifier l'ADL", "Changer le schéma", "Refactor" | 3 scénarios : patch, migration partielle, réécriture |

---

## 3. SCHÉMA DE DONNÉES

### 3.1 Scénario (Scenario)

```yaml
simulation:
  id: "SIM-20260805-001"
  triggered_by: "AGT-000"
  task_id: "TASK-20260805-042"
  intent: "DEPLOY"
  timestamp: "2026-08-05T14:30:00Z"
  status: "pending_review"      # pending_review | approved | rejected | expired

  baseline:                     # État actuel avant la décision
    current_state:
      active_agents: 176
      monthly_cost: 45000
      user_base: 45000
      system_health: "healthy"

  scenarios:
    - id: "SC-A"
      name: "Conservateur (Safe)"
      description: "Déploiement minimal avec rollback immédiat si anomalie"
      probability: 0.30

      actions:
        - "Déployer sur 5% du traffic (canary)"
        - "Monitoring intensif 24h"
        - "Rollback auto si error_rate > 1%"

      projections:
        budget:
          cost: 2000
          risk: "low"
          roi_3m: 0.05
        users:
          impact: "neutre"
          acquisition_delta: 0
          churn_delta: 0
        risks:
          technical: 0.05
          legal: 0.01
          reputation: 0.02
        timeline:
          duration: "48h"
          blockers: ["Aucun"]

      confidence: 0.85
      recommendation: "FAVORI pour les déploiements à haut risque"

    - id: "SC-B"
      name: "Nominal (Standard)"
      description: "Déploiement progressif avec validation intermédiaire"
      probability: 0.50

      actions:
        - "Déployer sur 25% du traffic (beta)"
        - "Validation manuelle après 48h"
        - "Déploiement complet si OK"

      projections:
        budget:
          cost: 5000
          risk: "medium"
          roi_3m: 0.12
        users:
          impact: "positif"
          acquisition_delta: 500
          churn_delta: -0.02
        risks:
          technical: 0.15
          legal: 0.05
          reputation: 0.08
        timeline:
          duration: "5 jours"
          blockers: ["Validation humaine requise à J+2"]

      confidence: 0.70
      recommendation: "RECOMMANDÉ pour la plupart des déploiements"

    - id: "SC-C"
      name: "Aggressif (Fast)"
      description: "Déploiement complet immédiat avec hotfix si nécessaire"
      probability: 0.20

      actions:
        - "Déploiement 100% immédiat"
        - "Équipe de crise en standby"
        - "Hotfix prioritaire si régression"

      projections:
        budget:
          cost: 12000
          risk: "high"
          roi_3m: 0.25
        users:
          impact: "fortement positif"
          acquisition_delta: 2000
          churn_delta: -0.05
        risks:
          technical: 0.35
          legal: 0.10
          reputation: 0.20
        timeline:
          duration: "2 jours"
          blockers: ["Hotfix potentiel coûteux", "Impact utilisateurs si régression"]

      confidence: 0.55
      recommendation: "DÉCONSEILLÉ sans validation explicite de Wudy"

  recommendation:
    chosen_scenario: "SC-B"
    reason: "Meilleur ratio risque/bénéfice. Confiance 70% suffisante. Nécessite validation humaine à J+2 ce qui réduit le risque."
    required_approvals:
      - role: "AGT-000"
        status: "pending"
      - role: "Wudy"
        status: "pending"
        condition: "Si budget > 5000€"
```

---

## 4. MOTEUR DE SIMULATION

### 4.1 Modèles de Projection

Le moteur utilise 3 types de modèles :

**A. Modèles Historiques (Data-Driven)**
```
Si une action similaire a été faite dans le passé :
  → Utiliser les résultats réels comme base de projection
  → Ajuster selon les différences de contexte (taille, complexité, date)
```

**B. Modèles Heuristiques (Règles)**
```
Règles codées par domaine :
- Déploiement : "Canary 5% = risque × 0.2, temps × 2.0"
- Budget : "Investissement marketing = acquisition × 0.1 (taux de conversion moyen)"
- Delete : "Suppression agent = impact nul si agent inactif depuis 30j"
```

**C. Modèles IA (Génération de Scénarios)**
```
Le Provider Adapter génère les scénarios via un prompt structuré :

"Tu es le Simulation Engine de CVLN. Analyse cette décision et génère 
3 scénarios (Conservateur, Nominal, Aggressif) avec projections sur 
budget, utilisateurs, risques et timeline. Base-toi sur les données 
historiques fournies et les heuristiques du domaine."

→ Le modèle IA (Claude/Kimi/GPT) génère le contenu des scénarios
→ Le Simulation Engine valide la cohérence (somme des probabilités = 1.0, 
  coûts cohérents, risques dans les bornes)
→ Les scénarios sont stockés et présentés
```

### 4.2 Calcul de Confiance

```
Confidence Score = 
  (data_quality × 0.4) +      # Qualité des données historiques disponibles
  (model_accuracy × 0.3) +    # Précision des modèles sur ce domaine
  (heuristic_coverage × 0.2) + # % de règles applicables
  (expert_validation × 0.1)    # A déjà été validé par un humain ?

Si Confidence < 0.5 → "INSUFFISANT — Demander plus de données ou avis expert"
Si Confidence 0.5-0.7 → "MOYEN — Scénarios indicatifs, validation recommandée"
Si Confidence > 0.7 → "ÉLEVÉ — Scénarios fiables, exécution possible"
```

---

## 5. API SIMULATION LAYER

```typescript
interface ISimulationLayer {
  // Déclencher une simulation
  simulate(
    task: ITask,
    intent: CriticalIntent,
    context: ISimulationContext
  ): Promise<ISimulationResult>;

  // Récupérer une simulation
  getSimulation(id: string): Promise<ISimulationResult>;

  // Approuver/Rejeter un scénario
  approveScenario(
    simulationId: string,
    scenarioId: string,
    approver: string
  ): Promise<ISimulationResult>;

  // Historique des simulations
  listSimulations(
    filters: {
      entityId?: string;
      intent?: CriticalIntent;
      status?: SimulationStatus;
      dateRange?: [Date, Date];
    }
  ): Promise<ISimulationResult[]>;

  // Métriques du moteur
  getAccuracyMetrics(): Promise<IAccuracyMetrics>;
  // Compare les projections vs réalité pour améliorer les modèles
}
```

---

## 6. INTÉGRATION AVEC L'ARCHITECTURE

```
Tâche reçue par Agent
    ↓
Intent Detector (analyse le texte de la tâche)
    ↓
[Si intent critique détecté]
    ↓
Simulation Layer
    ├── Récupère données historiques (MongoDB)
    ├── Applique heuristiques (règles codées)
    ├── Génère scénarios via Provider Adapter (Claude/Kimi)
    ├── Valide cohérence (moteur de règles)
    └── Stocke la simulation (MongoDB)
    ↓
Présentation à l'utilisateur / Agent 000
    ↓
[Si scénario approuvé]
    ↓
Exécution de la tâche via Agent Factory
    ↓
Post-mortem : comparaison projection vs réalité → alimente Learning Layer
```

---

## 7. EXEMPLE CONCRET

**Décision :** "Lancer la fonctionnalité 'Cultural Impact Score' sur KORA en production"

**Simulation générée :**

| Scénario | Coût | Risque | Impact Utilisateurs | Timeline | Confiance | Recommandation |
|----------|------|--------|---------------------|----------|-----------|----------------|
| **A — Safe** | 3K€ | Faible | +200 users/mois | 7 jours | 82% | ✅ Favori |
| **B — Standard** | 8K€ | Moyen | +800 users/mois | 4 jours | 68% | Recommandé |
| **C — Fast** | 15K€ | Élevé | +1500 users/mois | 2 jours | 45% | ❌ Déconseillé |

**Recommandation du système :** Scénario B (Standard) — meilleur équilibre risque/bénéfice avec validation intermédiaire.

**Action utilisateur :** Approuve le Scénario B → Exécution lancée avec monitoring à J+2.

---

*Spécification Simulation Layer — CVLN Group — Août 2026*
