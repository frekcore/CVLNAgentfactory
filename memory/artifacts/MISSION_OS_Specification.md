# MISSION OS — Couche d'Objectifs Stratégiques
## Spécification Technique v1.0 — CVLN Agent Factory

---

## 1. CONCEPT

Mission OS est la couche qui répond à la question : **"Pourquoi cet agent exécute-t-il cette tâche ?"**

Chaque entité (CVLN, KORA, FREKCORE, Factory Maker, TCV, SAYD, Kiltikonet, CC2027) possède :
- Une **Mission** (raison d'être, horizon 3-5 ans)
- Des **Objectifs Stratégiques** (OS-001, OS-002…) mesurables, datés, priorisés
- Des **Key Results** (résultats clés) avec cibles numériques
- Des **Initiatives** regroupant les agents qui contribuent à un objectif

Chaque agent, lorsqu'il reçoit une tâche, vérifie sa contribution à la mission de son entité. S'il ne peut pas établir de lien, il **escalade** plutôt qu'exécute aveuglément.

---

## 2. SCHÉMA DE DONNÉES

### 2.1 Entité (Entity)

```yaml
entity:
  id: "ENT-001"
  name: "KORA"
  type: "product"            # product | service | holding | event | subsidiary
  parent: "ENT-000"          # CVLN Holding = ENT-000
  status: "active"           # active | incubating | sunsetting | archived

  mission:
    statement: "Devenir la plateforme de référence pour la culture et l'impact social en Europe d'ici 2028."
    horizon: "2028-12-31"
    version: "2.1"

  strategic_objectives:
    - id: "OS-KORA-001"
      title: "Atteindre 100K utilisateurs actifs mensuels"
      priority: 1              # 1 = critique, 5 = faible
      horizon: "2026-12-31"
      weight: 0.30             # Contribution à la mission (total = 1.0)
      owner: "AGT-126"         # Agent Sales & Marketing KORA

      key_results:
        - id: "KR-KORA-001-01"
          description: "Taux d'acquisition mensuel > 5K nouveaux utilisateurs"
          target: 5000
          current: 3200
          unit: "users/month"
          frequency: "monthly"

        - id: "KR-KORA-001-02"
          description: "Taux de rétention D30 > 40%"
          target: 0.40
          current: 0.28
          unit: "percent"
          frequency: "weekly"

      initiatives:
        - id: "INI-KORA-001-A"
          name: "Campagne CC2027 — Pré-lancement"
          agents: ["AGT-126", "AGT-127", "AGT-128"]
          budget: 50000
          status: "in_progress"

    - id: "OS-KORA-002"
      title: "Générer 2M€ de revenus récurrents (ARR)"
      priority: 1
      horizon: "2027-06-30"
      weight: 0.25
      owner: "AGT-104"         # Agent Business Development KORA

      key_results:
        - id: "KR-KORA-002-01"
          description: "MRR (Monthly Recurring Revenue) > 170K€"
          target: 170000
          current: 85000
          unit: "EUR"
          frequency: "monthly"
```

### 2.2 Lien Agent-Objectif (AgentObjectiveLink)

```yaml
agent_objective_link:
  agent_id: "AGT-060"
  objective_id: "OS-KORA-003"
  contribution_type: "direct"     # direct | support | cross_entity
  contribution_weight: 0.15        # % de temps/allocation de l'agent
  tasks:
    - "Analyser le churn pour réduire la perte d'utilisateurs"
    - "Prédire les segments à risque pour les campagnes de rétention"
  alignment_score: 0.85            # 0-1, calculé par Mission OS
  last_reviewed: "2026-08-01"
```

### 2.3 Tâche avec Contexte Mission (TaskContext)

Quand un agent reçoit une tâche, Mission OS enrichit le prompt :

```
[MISSION CONTEXT]
Entité : KORA
Mission : "Devenir la plateforme de référence pour la culture et l'impact social en Europe d'ici 2028."
Objectif Stratégique Prioritaire : OS-KORA-001 "Atteindre 100K utilisateurs actifs mensuels" (P1, poids 30%)
Votre contribution : Analyse churn → réduction perte utilisateurs → acquisition nette
Alignment Score : 0.85/1.0

[TÂCHE]
Analyser les données Q3 et identifier les segments à risque de churn.

[CONTRAINTE]
Si cette tâche ne contribue pas à OS-KORA-001 ou OS-KORA-002, ESCALADER à AGT-000.
```

---

## 3. MOTEUR DE CALCUL — Alignment Score

L'**Alignment Score** mesure à quel point une tâche contribue à la mission de l'entité :

```
Alignment Score = Σ (objective_weight × task_relevance × completion_likelihood)

Où :
- objective_weight : poids de l'objectif stratégique (0-1)
- task_relevance : similarité sémantique entre la description de la tâche et les key results (embedding cosine)
- completion_likelihood : probabilité de succès basée sur les KPIs historiques de l'agent

Règles :
- Score < 0.3 → ESCALADE (tâche hors mission)
- Score 0.3-0.6 → AVERTISSEMENT (tâche marginale, confirmation requise)
- Score > 0.6 → EXÉCUTION AUTORISÉE
```

---

## 4. API MISSION OS

```typescript
interface IMissionOS {
  // CRUD Entités
  createEntity(entity: IEntity): Promise<IEntity>;
  updateEntity(id: string, updates: Partial<IEntity>): Promise<IEntity>;
  getEntity(id: string): Promise<IEntity>;
  listEntities(): Promise<IEntity[]>;

  // CRUD Objectifs Stratégiques
  createObjective(objective: IStrategicObjective): Promise<IStrategicObjective>;
  updateObjective(id: string, updates: Partial<IStrategicObjective>): Promise<IStrategicObjective>;
  getObjective(id: string): Promise<IStrategicObjective>;
  listObjectives(entityId?: string): Promise<IStrategicObjective[]>;

  // Lien Agent-Objectif
  linkAgentToObjective(link: IAgentObjectiveLink): Promise<IAgentObjectiveLink>;
  getAgentObjectives(agentId: string): Promise<IAgentObjectiveLink[]>;

  // Évaluation
  calculateAlignmentScore(agentId: string, taskDescription: string): Promise<number>;
  enrichTaskWithMissionContext(agentId: string, task: ITask): Promise<ITaskEnriched>;

  // Tableau de bord
  getEntityDashboard(entityId: string): Promise<IEntityDashboard>;
  getAgentContributionReport(agentId: string): Promise<IContributionReport>;
}
```

---

## 5. INTÉGRATION AVEC L'ARCHITECTURE EXISTANTE

```
Laurentia (Interface)
    ↓
CVLN Agent Factory
    ├── Mission OS (NOUVEAU)
    │   ├── Entity Registry
    │   ├── Strategic Objectives
    │   ├── Key Results Tracker
    │   └── Alignment Engine
    │
    ├── Provider Adapter Layer
    │   ├── ClaudeAdapter
    │   ├── KimiAdapter
    │   └── ModelRouter
    │
    └── Agents Spécialisés
        └── Chaque agent reçoit son [MISSION CONTEXT] avant sa tâche
```

**Stockage :** MongoDB (collections `entities`, `strategic_objectives`, `agent_objective_links`)
**Vector Store :** Index de recherche interne (embeddings des missions/objectifs pour le calcul de relevance)
**Event Bus :** Événements `mission.objective.updated`, `mission.alignment.low`, `mission.kr.achieved`

---

## 6. EXEMPLE D'EXÉCUTION

**Scénario :** AGT-060 (Data Science Analyst KORA) reçoit la tâche "Créer un rapport sur les tendances météorologiques en Europe."

**Étape 1 — Mission OS intercepte la tâche :**
```
Tâche reçue : "Créer un rapport sur les tendances météorologiques en Europe."
Entité : KORA
Mission : "Devenir la plateforme de référence pour la culture et l'impact social..."
```

**Étape 2 — Calcul de l'Alignment Score :**
```
Relevance avec OS-KORA-001 (100K utilisateurs) : 0.02 (météo ≠ culture)
Relevance avec OS-KORA-002 (2M€ ARR) : 0.01
Relevance avec OS-KORA-003 (Cultural Impact Score) : 0.05
Alignment Score = 0.03
```

**Étape 3 — Décision :**
```
Score 0.03 < 0.3 → ESCALADE
Message à l'utilisateur : "Cette tâche semble hors mission de KORA. 
Voulez-vous la réaffecter à une autre entité (ex: CC2027 événementiel) 
ou confirmer l'exécution malgré le faible alignment ?"
```

**Scénario alternatif :** Même agent, tâche "Analyser le churn Q3 et prédire les segments à risque."
```
Relevance avec OS-KORA-001 : 0.92 (churn → rétention → utilisateurs actifs)
Alignment Score = 0.92 × 0.30 × 0.85 = 0.77
Score 0.77 > 0.6 → EXÉCUTION AUTORISÉE
Contexte enrichi : "Cette tâche contribue directement à OS-KORA-001 (30% de la mission)."
```

---

## 7. RÈGLES DE GOUVERNANCE

1. **Chaque entité DOIT avoir au moins 1 objectif stratégique et au maximum 7.**
2. **La somme des poids des objectifs d'une entité DOIT être égale à 1.0.**
3. **Un agent NE PEUT PAS être lié à plus de 3 objectifs simultanément.**
4. **Les objectifs sont revus trimestriellement par Agent 000 + Founder Council.**
5. **Un objectif atteint à 100% est archivé et célébré (Event Bus : `mission.kr.achieved`).**
6. **Un objectif à 0% après 50% du temps imparti déclenche une alerte critique.**

---

*Spécification Mission OS — CVLN Group — Août 2026*
