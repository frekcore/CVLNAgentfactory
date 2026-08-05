# AUDIT PÔLE 0B — AGT-011 à AGT-015 (S0.3 / F-007)
Date : 2026-07-10 · Auditeur : AGT-000 (exécuté par l'agent principal) · Statut : documenté, intégré au Registry maître

## Constat
5 agents générés via l'application (pilotes Autonomous Workforce, 2026-07-10) sans documentation dans les paliers structurés.

## Périmètres clarifiés (vs chevauchements suspectés)

| Agent | Rôle | Chevauchement suspecté | Résolution |
|---|---|---|---|
| AGT-011 Digital CEO | Coordination exécutive transverse des entités, arbitrages opérationnels quotidiens | AGT-000 (Architect) | **Distinct** : AGT-000 gouverne la Factory (création/validation d'agents), AGT-011 pilote l'exploitation business. Aucune écriture Registry pour AGT-011. |
| AGT-012 Digital CFO | Synthèse financière groupe, ROI par agent/entité, prévisions | Pôle 5 (AGT-104→125 Accounting/Tax/Payroll) | **Complémentaire** : AGT-012 = vision consolidée groupe (lecture Finance Layer) ; Pôle 5 = exécution comptable par domaine sous plafonds Wudy (Financial Gatekeeper). AGT-012 n'exécute aucune écriture comptable. |
| AGT-013 Knowledge Manager | Routage des connaissances vers les mémoires stratégiques des agents | Memory Service (core) | **Distinct** : le Memory Service est l'infrastructure (stockage isolé) ; AGT-013 est l'opérateur métier (classification, routage, validation d'ingestion). |
| AGT-014 Operations | Suivi des tâches/missions inter-entités, déblocage opérationnel | Pôle 7 (Project Mgmt AGT-151→175) | **Complémentaire** : AGT-014 = niveau groupe (cross-entités) ; Pôle 7 = gestion projet par entité/client. |
| AGT-015 Marketing Strategy | Stratégie marketing groupe | Pôle 6 (Sales & Marketing AGT-126→150) | **Complémentaire** : AGT-015 définit la stratégie ; Pôle 6 exécute par canal. |

## Actions réalisées
- Champ `pole_0b_audit` ajouté aux 5 fiches Registry (périmètre + date + non-chevauchement)
- ADL déjà présents au Registry (générés par pipeline) — conformité doctrine vérifiée à la génération
- Journalisation de l'audit dans l'Activity Journal v2

## Verdict
Aucune fusion nécessaire. Aucun doublon fonctionnel. Les 5 agents sont conservés en Pôle 0b avec périmètres documentés.
