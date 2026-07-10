import { createContext, useContext, useState } from "react";

const dict = {
  fr: {
    dashboard: "Tableau de bord", agents: "Annuaire des agents", adl_editor: "Éditeur ADL",
    generator: "Générateur", doctrine: "Doctrine", events: "Event Bus", audit: "Audit",
    monitoring: "Supervision", users: "Utilisateurs", logout: "Déconnexion",
    login_title: "Console Agent Factory", login_subtitle: "Agent Operating System Layer",
    email: "Email", password: "Mot de passe", sign_in: "Se connecter",
    ecosystem_state: "État de l'écosystème", agents_registered: "agents enregistrés",
    by_status: "Répartition par statut", by_pole: "Par pôle", by_entity: "Par entité",
    recent_events: "Événements récents", search: "Rechercher...", all_statuses: "Tous statuts",
    all_poles: "Tous pôles", all_entities: "Toutes entités", name: "Nom", pole: "Pôle",
    entity: "Entité", status: "Statut", version: "Version", mission: "Mission",
    vision: "Vision", objectives: "Objectifs", kpis: "KPIs", tools: "Outils",
    knowledge: "Connaissances", permissions: "Permissions", tests: "Tests",
    overview: "Fiche", timeline: "Cycle de vie", versions: "Versions", diff: "Diff",
    export_yaml: "Exporter YAML", lifecycle_transition: "Transition", note: "Note",
    compile: "Compiler", validating: "Validation...", valid_adl: "ADL valide",
    validation_errors: "Erreurs de validation", import_yaml: "Importer YAML",
    load_template: "Charger un modèle", editor_hint: "Édition YAML — validation en temps réel",
    catalog: "Catalogue maître", new_definition: "Nouvelle définition métier",
    generate: "Générer", add_to_catalog: "Ajouter au catalogue", generate_direct: "Générer directement",
    category: "Catégorie", skills: "Compétences", autonomy: "Niveau d'autonomie",
    pipeline_result: "Rapport de génération", service_token: "Token de service (affiché une seule fois)",
    doctrine_title: "Doctrine CVLN", external_systems: "Écosystème externe (systèmes indépendants)",
    topic: "Topic", source: "Source", destination: "Destination", timestamp: "Horodatage",
    payload: "Contenu", action: "Action", resource: "Ressource", allowed: "Accepté",
    denied: "Refusé", all: "Tous", actor: "Acteur", reason: "Raison",
    core_services: "Core Services", active_agents: "Agents actifs", events_24h: "Événements (24h)",
    denied_24h: "Refus d'autorisation (24h)", alerts: "Alertes", no_alerts: "Aucune alerte",
    create_user: "Créer un utilisateur", role: "Rôle", delete: "Supprimer",
    service_identities: "Identités de service", created_at: "Créé le",
    admin: "Admin", operator: "Opérateur", reader: "Lecteur",
    memory_logs: "Journal mémoire", generated: "Généré", loading: "Chargement...",
    no_results: "Aucun résultat", actions: "Actions", cancel: "Annuler", confirm: "Confirmer",
    comma_hint: "séparés par des virgules",
  },
  en: {
    dashboard: "Dashboard", agents: "Agent directory", adl_editor: "ADL Editor",
    generator: "Generator", doctrine: "Doctrine", events: "Event Bus", audit: "Audit",
    monitoring: "Monitoring", users: "Users", logout: "Log out",
    login_title: "Agent Factory Console", login_subtitle: "Agent Operating System Layer",
    email: "Email", password: "Password", sign_in: "Sign in",
    ecosystem_state: "Ecosystem state", agents_registered: "agents registered",
    by_status: "Breakdown by status", by_pole: "By pole", by_entity: "By entity",
    recent_events: "Recent events", search: "Search...", all_statuses: "All statuses",
    all_poles: "All poles", all_entities: "All entities", name: "Name", pole: "Pole",
    entity: "Entity", status: "Status", version: "Version", mission: "Mission",
    vision: "Vision", objectives: "Objectives", kpis: "KPIs", tools: "Tools",
    knowledge: "Knowledge", permissions: "Permissions", tests: "Tests",
    overview: "Overview", timeline: "Lifecycle", versions: "Versions", diff: "Diff",
    export_yaml: "Export YAML", lifecycle_transition: "Transition", note: "Note",
    compile: "Compile", validating: "Validating...", valid_adl: "Valid ADL",
    validation_errors: "Validation errors", import_yaml: "Import YAML",
    load_template: "Load template", editor_hint: "YAML editing — real-time validation",
    catalog: "Master catalog", new_definition: "New business definition",
    generate: "Generate", add_to_catalog: "Add to catalog", generate_direct: "Generate directly",
    category: "Category", skills: "Skills", autonomy: "Autonomy level",
    pipeline_result: "Generation report", service_token: "Service token (shown only once)",
    doctrine_title: "CVLN Doctrine", external_systems: "External ecosystem (independent systems)",
    topic: "Topic", source: "Source", destination: "Destination", timestamp: "Timestamp",
    payload: "Payload", action: "Action", resource: "Resource", allowed: "Allowed",
    denied: "Denied", all: "All", actor: "Actor", reason: "Reason",
    core_services: "Core Services", active_agents: "Active agents", events_24h: "Events (24h)",
    denied_24h: "Denied authorizations (24h)", alerts: "Alerts", no_alerts: "No alerts",
    create_user: "Create user", role: "Role", delete: "Delete",
    service_identities: "Service identities", created_at: "Created at",
    admin: "Admin", operator: "Operator", reader: "Reader",
    memory_logs: "Memory log", generated: "Generated", loading: "Loading...",
    no_results: "No results", actions: "Actions", cancel: "Cancel", confirm: "Confirm",
    comma_hint: "comma-separated",
  },
};

const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(localStorage.getItem("cvln_lang") || "fr");
  const setLang = (l) => { localStorage.setItem("cvln_lang", l); setLangState(l); };
  const t = (key) => dict[lang]?.[key] ?? dict.fr[key] ?? key;
  return <LanguageContext.Provider value={{ lang, setLang, t }}>{children}</LanguageContext.Provider>;
}

export const useLang = () => useContext(LanguageContext);
