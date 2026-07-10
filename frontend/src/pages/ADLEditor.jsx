import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useLang } from "../lib/i18n";
import { CheckCircle, WarningCircle, Play, UploadSimple, FileCode } from "@phosphor-icons/react";

const TEMPLATE = `adl_version: "1.0"
agent:
  id: AGT-011
  name: Nouvel Agent
  pole: Infrastructure IA
  entity: CVLN Holding
  version: 0.1.0
  mission: Décrire ici la mission complète de l'agent (10 caractères minimum).
  vision: ""
  objectives:
    - Premier objectif
  kpis:
    - Premier KPI
brain:
  registry:
    registered: true
  memory:
    scope: persistent
    owner: AGT-011
  identity:
    autonomy_level: supervised
  events:
    subscribe: []
    publish: []
  monitoring:
    health_check: true
tools: []
knowledge:
  - source: Doctrine CVLN
    type: doctrine
    description: Doctrine CVLN héritée
permissions:
  read:
    - registry
  write: []
  entities:
    - CVLN Holding
tests:
  - name: identity_check
    assertion: agent.id == 'AGT-011'
`;

export default function ADLEditor() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [yamlText, setYamlText] = useState(TEMPLATE);
  const [validation, setValidation] = useState(null);
  const [validating, setValidating] = useState(false);
  const [compiling, setCompiling] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => {
    setValidating(true);
    const id = setTimeout(async () => {
      try {
        const { data } = await api.post("/adl/validate", { adl_yaml: yamlText });
        setValidation(data);
      } catch (e) { /* ignore */ }
      setValidating(false);
    }, 600);
    return () => clearTimeout(id);
  }, [yamlText]);

  const compile = async () => {
    setCompiling(true);
    try {
      const { data } = await api.post("/registry/compile", { adl_yaml: yamlText });
      toast.success(`${data.result === "created" ? "Agent créé (Draft)" : "Version compilée"} — ${data.agent_id} v${data.version}`);
      setTimeout(() => navigate(`/agents/${data.agent_id}`), 800);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail?.type === "duplicate") {
        toast.error(`Doublon détecté : ${detail.duplicates.map((d) => `${d.id} (${d.reasons.join(", ")})`).join(" · ")}`, { duration: 8000 });
      } else {
        toast.error(formatApiError(detail));
      }
    } finally { setCompiling(false); }
  };

  const importFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setYamlText(String(reader.result));
    reader.readAsText(file);
    e.target.value = "";
  };

  return (
    <div data-testid="adl-editor-page" className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("adl_editor")}</h1>
          <p className="text-xs text-muted-foreground font-mono mt-1">{t("editor_hint")}</p>
        </div>
        <div className="flex items-center gap-3">
          <input ref={fileRef} type="file" accept=".yaml,.yml" onChange={importFile} className="hidden" />
          <button data-testid="import-yaml-btn" onClick={() => fileRef.current?.click()}
            className="flex items-center gap-2 border border-border px-3 py-2 text-xs font-mono rounded-sm hover:border-primary hover:text-primary transition-colors duration-150">
            <UploadSimple size={14} /> {t("import_yaml")}
          </button>
          <button data-testid="load-template-btn" onClick={() => setYamlText(TEMPLATE)}
            className="flex items-center gap-2 border border-border px-3 py-2 text-xs font-mono rounded-sm hover:border-primary hover:text-primary transition-colors duration-150">
            <FileCode size={14} /> {t("load_template")}
          </button>
          <button data-testid="compile-adl-btn" onClick={compile} disabled={compiling || !validation?.valid}
            className="flex items-center gap-2 bg-primary text-primary-foreground px-5 py-2 text-xs font-semibold rounded-sm hover:opacity-90 transition-opacity duration-150 disabled:opacity-40">
            <Play size={14} weight="fill" /> {compiling ? "..." : t("compile")}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <textarea data-testid="adl-yaml-textarea" value={yamlText} onChange={(e) => setYamlText(e.target.value)}
          spellCheck={false}
          className="lg:col-span-2 h-[600px] bg-card border border-border rounded-sm p-5 text-xs font-mono leading-relaxed focus:outline-none focus:border-primary resize-none text-emerald-300/90 transition-colors duration-150" />
        <div className="space-y-4">
          <div data-testid="validation-panel" className={`border rounded-sm p-5 ${validation?.valid ? "border-emerald-900 bg-emerald-950/20" : "border-border bg-card"}`}>
            {validating ? (
              <p className="text-xs font-mono text-muted-foreground animate-pulse">{t("validating")}</p>
            ) : validation?.valid ? (
              <div className="flex items-center gap-2 text-emerald-400">
                <CheckCircle size={18} weight="fill" />
                <p className="text-sm font-semibold">{t("valid_adl")}</p>
              </div>
            ) : (
              <div>
                <div className="flex items-center gap-2 text-destructive mb-3">
                  <WarningCircle size={18} weight="fill" />
                  <p className="text-sm font-semibold">{t("validation_errors")}</p>
                </div>
                <ul className="space-y-2">
                  {(validation?.errors || []).map((e, i) => (
                    <li key={i} className="text-xs font-mono">
                      <span className="text-amber-400">{e.path}</span>
                      <span className="text-muted-foreground"> — {e.message}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          {validation?.valid && validation.parsed && (
            <div className="border border-border rounded-sm bg-card p-5 space-y-2">
              <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-2">Preview</p>
              <p className="text-sm font-mono text-primary">{validation.parsed.agent.id} · v{validation.parsed.agent.version}</p>
              <p className="text-sm font-semibold">{validation.parsed.agent.name}</p>
              <p className="text-xs text-muted-foreground">{validation.parsed.agent.pole} — {validation.parsed.agent.entity}</p>
              <p className="text-xs text-muted-foreground leading-relaxed">{validation.parsed.agent.mission}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
