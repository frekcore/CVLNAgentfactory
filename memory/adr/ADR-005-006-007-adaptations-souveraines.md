# ADR-005 — Vector Store : MongoDB lexical souverain vs Qdrant
Date : 2026-07-10 · Statut : Approuvé (temporaire) · Décideur : Laurent (validation conversation)

## Contexte
ADR-003 du rapport d'audit préconise Qdrant pour le KnowledgeSource. Qdrant n'est pas déployable dans l'environnement actuel (pas de service dédié, pas d'embeddings sans dépendance LLM externe — contraire au principe de souveraineté en l'état).

## Décision
Implémenter `SovereignLexicalStore` : chunking (600c/100 overlap) + index lexical MongoDB (termes tokenisés, score TF pondéré). Interface `IVectorStore` stable : `ingest() / search() / delete_source()`.

## Limites documentées
- Recherche lexicale (pas sémantique) : synonymes non couverts, français/anglais séparés
- Score TF simple, pas de reranking
- Performance acceptable < ~50k chunks (index Mongo sur `terms`)

## Plan de migration future
1. Déployer Qdrant sur le serveur dédié CVLN (self-hosted, open-source)
2. Créer `QdrantStore(IVectorStore)` avec embeddings (modèle local type sentence-transformers ou provider via Adapter Layer)
3. Ré-ingérer `knowledge_sources.content` (conservé intégralement en base) — zéro perte
4. Basculer `vector_store = QdrantStore()` — aucune modification des routes

# ADR-006 — Event Bus : MongoDB persistant + spool local vs NATS JetStream
Date : 2026-07-10 · Statut : Approuvé (temporaire)

## Contexte
ADR-004 du rapport préconise NATS JetStream. Non déployable ici (pas de cluster).

## Décision
Conserver l'Event Bus MongoDB (déjà persistant/durable) et ajouter : (1) spool local JSONL en cas d'indisponibilité Mongo (mode dégradé), (2) Dead Letter Queue (`events_dlq`), (3) endpoint replay du spool.

## Limites
- Pas de consumers/streams temps réel (polling), pas de clustering natif
- Le spool local est mono-nœud

## Plan de migration
Interface `publish()` inchangée → adaptateur NATS JetStream (subjects = topics actuels `agent.*`, `factory.*`) sur le futur cloud CVLN ; replay du spool et de `events` vers les streams.

# ADR-007 — Secrets : rotation interne + TTL vs HashiCorp Vault
Date : 2026-07-10 · Statut : Approuvé (temporaire)

## Contexte
F-010 : stratégie secrets non détaillée. Vault non déployable ici.

## Décision
Hardening interne : rotation des tokens de service (`POST /identity/service/{agent_id}/rotate`), TTL optionnel (`expires_at` vérifié à l'authentification), scope par agent, audit trail complet (audit_logs + journal).

## Limites
- Pas de chiffrement d'enveloppe ni de moteur de secrets dynamiques
- Les hashs SHA-256 des tokens restent en Mongo (pas de HSM)

## Plan de migration
`secrets_scope: cvln/agents/AGT-XXX` (déjà dans l'ADL v2) mappe directement sur des chemins Vault KV ; l'Identity Service lira Vault au lieu de `identities.token_hash`.
