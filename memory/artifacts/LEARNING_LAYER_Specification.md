# LEARNING LAYER — Moteur d'Apprentissage et d'Amélioration
## Spécification Technique v1.0 — CVLN Agent Factory

---

## 1. CONCEPT

Le Learning Layer transforme le runtime d'un **exécutant** en un **apprenant**. 

À chaque fin de cycle (closing), le système :
1. **Analyse** ce qui s'est passé (succès, échecs, anomalies)
2. **Compare** avec les projections (Simulation Layer) et les objectifs (Mission OS)
3. **Identifie** les patterns d'erreur et les opportunités d'amélioration
4. **Propose** des ajustements pour les prochains cycles
5. **Met à jour** la base de connaissances de l'agent (KnowledgeSource)

Ce n'est pas de l'apprentissage automatique au sens classique (ML). C'est de l'**apprentissage structuré** basé sur des règles, des patterns et des feedback loops explicites.

---

## 2. CYCLE D'APPRENTISSAGE

```
┌─────────────────────────────────────────────────────────────┐
│  CYCLE D'APPRENTISSAGE (exécuté à chaque closing)           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. COLLECTE                                                │
│     ├── Logs d'exécution de l'agent                         │
│     ├── Résultats des tâches (succès/échec/partial)         │
│     ├── Métriques de performance (latence, tokens, coût)    │
│     ├── Comparaison Simulation vs Réalité                   │
│     └── Feedback utilisateur (si fourni)                    │
│                                                             │
│  2. ANALYSE                                                 │
│     ├── Détection d'anomalies (écart > 20% vs baseline)     │
│     ├── Classification des erreurs                          │
│     │   ├── Technique (timeout, parsing, API down)          │
│     │   ├── Logique (mauvaise compréhension, hallucination) │
│     │   ├── Mission (hors scope, alignment faible)          │
│     │   └── Gouvernance (violation doctrine, escalade)      │
│     ├── Identification des patterns récurrents              │
│     └── Calcul du "Learning Score" (0-100)                  │
│                                                             │
│  3. SYNTHÈSE                                                │
│     ├── Résumé du cycle (succès, échecs, apprentissages)    │
│     ├── Recommandations pour le prochain cycle              │
│     └── Mise à jour des heuristiques de l'agent             │
│                                                             │
│  4. MISE À JOUR                                             │
│     ├── KnowledgeSource : ajout des nouvelles leçons        │
│     ├── ADL : ajustement des paramètres si nécessaire       │
│     ├── Heuristiques : nouvelles règles apprises            │
│     └── Simulation Layer : amélioration des modèles         │
│                                                             │
│  5. DIFFUSION                                               │
│     ├── Event Bus : `learning.cycle.completed`              │
│     ├── Agent 000 : rapport consolidé cross-agents          │
│     └── Knowledge Commons : leçons partagées si pertinent   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. SCHÉMA DE DONNÉES

### 3.1 Cycle d'Apprentissage (LearningCycle)

```yaml
learning_cycle:
  id: "LC-20260805-001"
  agent_id: "AGT-060"
  cycle_number: 42
  period: ["2026-08-05T08:00:00Z", "2026-08-05T18:00:00Z"]

  execution_summary:
    tasks_total: 15
    tasks_success: 12
    tasks_failure: 2
    tasks_partial: 1

    performance:
      avg_latency_ms: 1200
      avg_tokens_per_task: 450
      total_cost_usd: 8.50
      alignment_score_avg: 0.78

    errors:
      - id: "ERR-001"
        type: "technical"
        subtype: "api_timeout"
        task_id: "TASK-042"
        severity: "medium"
        description: "KORA API timeout après 30s"
        root_cause: "KORA API sous charge à 14h30"
        resolution: "Retry avec backoff + alerte envoyée à AGT-078 (DevOps)"
        preventable: true
        prevention_action: "Ajouter un circuit breaker sur l'API KORA"

      - id: "ERR-002"
        type: "logic"
        subtype: "hallucination"
        task_id: "TASK-038"
        severity: "high"
        description: "L'agent a prédit un churn de 45% sur un segment sain"
        root_cause: "Données d'entraînement obsolètes (modèle non réentraîné depuis 2 mois)"
        resolution: "Escalade à AGT-060 lui-même pour réentraînement"
        preventable: true
        prevention_action: "Alerte auto si dernière mise à jour modèle > 30j"

  simulation_vs_reality:
    simulation_id: "SIM-20260805-001"
    projected_cost: 8.00
    actual_cost: 8.50
    variance: 0.50
    variance_percent: 6.25
    accuracy_rating: "good"    # excellent | good | fair | poor

  learning_score: 72           # 0-100, calculé par le moteur

  lessons_learned:
    - id: "LL-001"
      category: "technical"
      description: "KORA API timeout fréquent entre 14h et 15h"
      impact: "high"
      action: "Implémenter circuit breaker + retry exponentiel"
      status: "proposed"

    - id: "LL-002"
      category: "logic"
      description: "Modèle churn doit être réentraîné mensuellement"
      impact: "critical"
      action: "Ajouter une tâche planifiée de réentraînement"
      status: "proposed"

    - id: "LL-003"
      category: "mission"
      description: "2 tâches reçues avec alignment score < 0.3 — possible confusion sur le scope"
      impact: "medium"
      action: "Clarifier la mission de KORA Data Science dans le Knowledge Commons"
      status: "proposed"

  recommendations_next_cycle:
    - "Prioriser la tâche de réentraînement du modèle churn"
    - "Tester le circuit breaker sur KORA API en staging"
    - "Réviser la documentation du scope AGT-060"

  knowledge_updates:
    - knowledge_id: "ks-003"
      update_type: "append"
      content: "Leçon : KORA API timeout fréquent 14h-15h. Solution : circuit breaker + retry."

    - knowledge_id: "ks-NEW-001"
      update_type: "create"
      content: "Best Practice : Modèles de prédiction doivent être réentraînés tous les 30j maximum."
```

---

## 4. MOTEUR D'APPRENTISSAGE

### 4.1 Calcul du Learning Score

```
Learning Score = 
  (success_rate × 30) +           # 30 points max — taux de succès
  (error_preventability × 20) +   # 20 points max — % d'erreurs évitables identifiées
  (simulation_accuracy × 20) +    # 20 points max — précision des simulations
  (knowledge_updates × 15) +      # 15 points max — nouvelles leçons documentées
  (recommendations_quality × 15)  # 15 points max — qualité des recommandations

Interprétation :
- 90-100 : Excellent — L'agent apprend efficacement
- 70-89  : Bon — Quelques améliorations possibles
- 50-69  : Moyen — Patterns d'erreur récurrents à traiter
- 30-49  : Faible — Intervention humaine recommandée
- 0-29   : Critique — L'agent doit être mis en review
```

### 4.2 Détection de Patterns

```typescript
interface IPatternDetector {
  // Détecte les erreurs récurrentes sur un même type de tâche
  detectRecurringErrors(
    agentId: string,
    lookbackCycles: number = 10
  ): Promise<IRecurringErrorPattern[]>;

  // Détecte les dégradations de performance
  detectPerformanceRegression(
    agentId: string,
    metric: 'latency' | 'cost' | 'accuracy',
    threshold: number = 0.20
  ): Promise<IPerformanceRegression[]>;

  // Détecte les dérives de mission
  detectMissionDrift(
    agentId: string,
    lookbackCycles: number = 5
  ): Promise<IMissionDriftAlert[]>;
  // Alert si alignment_score moyen < 0.5 sur N cycles

  // Détecte les opportunités d'optimisation
  detectOptimizationOpportunities(
    agentId: string
  ): Promise<IOptimizationOpportunity[]>;
  // Ex: "Cet agent utilise GPT-4 pour des tâches simples — passer à Kimi économiserait 40%"
}
```

---

## 5. APPRENTISSAGE CROSS-AGENT (KNOWLEDGE COMMONS)

Quand un agent apprend une leçon, le Learning Layer évalue si elle est **partageable** :

```
Partageable si :
- La leçon concerne un outil/service utilisé par > 3 agents
- La leçon concerne une règle de gouvernance
- La leçon concerne une best practice technique
- La leçon est classée "critical" en impact

→ Publier sur Event Bus : `learning.lesson.shareable`
→ Intégrer au Knowledge Commons
→ Notifier les agents concernés
```

**Exemple :**
- AGT-060 (Data Science KORA) apprend que "KORA API timeout à 14h"
- AGT-078 (DevOps Web) et AGT-079 (Mobile Dev) utilisent aussi KORA API
- → Leçon partagée automatiquement à AGT-078 et AGT-079
- → Leçon ajoutée au Knowledge Commons sous `shared/kora-api-best-practices`

---

## 6. API LEARNING LAYER

```typescript
interface ILearningLayer {
  // Exécuter le cycle d'apprentissage
  runLearningCycle(
    agentId: string,
    cycleData: ICycleData
  ): Promise<ILearningCycleResult>;

  // Récupérer l'historique d'apprentissage
  getLearningHistory(
    agentId: string,
    options?: { limit?: number; since?: Date }
  ): Promise<ILearningCycleResult[]>;

  // Récupérer les leçons apprises
  getLessonsLearned(
    filters?: {
      agentId?: string;
      category?: ErrorCategory;
      impact?: 'low' | 'medium' | 'high' | 'critical';
      status?: 'proposed' | 'implemented' | 'rejected';
    }
  ): Promise<ILessonLearned[]>;

  // Approuver/Implémenter une leçon
  implementLesson(
    lessonId: string,
    approver: string
  ): Promise<ILessonLearned>;

  // Métriques d'apprentissage
  getLearningMetrics(
    agentId?: string
  ): Promise<ILearningMetrics>;
  // Inclut : Learning Score moyen, taux d'erreurs récurrentes, 
  // nombre de leçons partagées, amélioration de simulation accuracy
}
```

---

## 7. INTÉGRATION AVEC L'ARCHITECTURE

```
Agent exécute une tâche
    ↓
Résultat stocké (succès/échec)
    ↓
[Fin de cycle — Closing]
    ↓
Learning Layer s'active
    ├── Récupère logs + métriques + simulation vs réalité
    ├── Analyse (PatternDetector)
    ├── Génère leçons + recommandations
    ├── Met à jour KnowledgeSource de l'agent
    ├── Si leçon partageable → Knowledge Commons
    └── Publie `learning.cycle.completed` sur Event Bus
    ↓
Agent 000 reçoit le rapport consolidé
    ↓
[Si Learning Score < 50] → Review obligatoire
[Si erreur critique] → Escalade à Wudy
```

---

## 8. EXEMPLE CONCRET

**Agent :** AGT-060 (Data Science KORA)  
**Période :** 5 cycles (1 semaine)

| Cycle | Tâches | Succès | Erreurs | Learning Score | Leçon principale |
|-------|--------|--------|---------|----------------|------------------|
| 38 | 12 | 10 | 2 | 68 | Timeout KORA API |
| 39 | 15 | 11 | 3 | 55 | Modèle churn obsolète |
| 40 | 14 | 13 | 1 | 78 | Circuit breaker testé |
| 41 | 16 | 15 | 1 | 82 | Réentraînement modèle |
| 42 | 15 | 12 | 2 | 72 | Documentation scope |

**Tendance :** Learning Score en amélioration (55 → 72) grâce aux actions correctives implémentées.

**Recommandation Learning Layer pour Cycle 43 :**
> "AGT-060 montre une amélioration constante. Prochaine étape : automatiser le réentraînement du modèle churn (tous les 30j) et intégrer le circuit breaker KORA API en production."

---

*Spécification Learning Layer — CVLN Group — Août 2026*
