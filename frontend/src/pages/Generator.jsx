import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useLang } from "../lib/i18n";
import { Factory, CheckCircle, WarningCircle, Trash, Copy } from "@phosphor-icons/react";

const EMPTY = { name: "", category: "", pole: "", entity: "", mission: "", objectives: "", skills: "", tools: "", autonomy_level: "supervised", kpis: "" };

const toList = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function Generator() {
  const { t } = useLang();
  const [catalog, setCatalog] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [report, setReport] = useState(null);
  const [generating, setGenerating] = useState(false);

  const load = () => api.get("/generator/catalog").then((r) => setCatalog(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const buildDefinition = () => ({
    name: form.name, category: form.category, pole: form.pole, entity: form.entity,
    mission: form.mission, objectives: toList(form.objectives), skills: toList(form.skills),
    tools: toList(form.tools), autonomy_level: form.autonomy_level, kpis: toList(form.kpis),
  });

  const addToCatalog = async () => {
    try {
      await api.post("/generator/catalog", buildDefinition());
      toast.success("Définition ajoutée au catalogue");
      setForm(EMPTY); load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const generate = async (payload) => {
    setGenerating(true); setReport(null);
    try {
      const { data } = await api.post("/generator/generate", payload);
      setReport(data);
      toast.success(`Agent ${data.agent_id} généré — statut ${data.status}`);
      setForm(EMPTY); load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail?.steps) setReport({ steps: detail.steps, error: formatApiError(detail) });
      toast.error(formatApiError(detail));
    } finally { setGenerating(false); }
  };

  const field = "w-full bg-background border border-input rounded-sm px-3 py-2 text-xs font-mono focus:outline-none focus:border-primary transition-colors duration-150";
  const label = "text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground block mb-1.5";

  return (
    <div data-testid="generator-page" className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Agent Generator Engine</h1>
        <p className="text-xs text-muted-foreground font-mono mt-1">AGT-000 · définition métier → ADL → doctrine → Registry → cycle de vie</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="border border-border rounded-sm bg-card p-6 space-y-4">
          <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-primary">{t("new_definition")}</p>
          <div className="grid grid-cols-2 gap-3">
            <div><label className={label}>{t("name")}</label>
              <input data-testid="gen-name-input" className={field} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
            <div><label className={label}>{t("category")}</label>
              <input data-testid="gen-category-input" className={field} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="AI Services" /></div>
            <div><label className={label}>{t("pole")}</label>
              <input data-testid="gen-pole-input" className={field} value={form.pole} onChange={(e) => setForm({ ...form, pole: e.target.value })} /></div>
            <div><label className={label}>{t("entity")}</label>
              <input data-testid="gen-entity-input" className={field} value={form.entity} onChange={(e) => setForm({ ...form, entity: e.target.value })} /></div>
          </div>
          <div><label className={label}>{t("mission")}</label>
            <textarea data-testid="gen-mission-input" className={`${field} h-20 resize-none`} value={form.mission} onChange={(e) => setForm({ ...form, mission: e.target.value })} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className={label}>{t("objectives")} ({t("comma_hint")})</label>
              <input data-testid="gen-objectives-input" className={field} value={form.objectives} onChange={(e) => setForm({ ...form, objectives: e.target.value })} /></div>
            <div><label className={label}>{t("kpis")} ({t("comma_hint")})</label>
              <input data-testid="gen-kpis-input" className={field} value={form.kpis} onChange={(e) => setForm({ ...form, kpis: e.target.value })} /></div>
            <div><label className={label}>{t("skills")} ({t("comma_hint")})</label>
              <input data-testid="gen-skills-input" className={field} value={form.skills} onChange={(e) => setForm({ ...form, skills: e.target.value })} /></div>
            <div><label className={label}>{t("tools")} ({t("comma_hint")})</label>
              <input data-testid="gen-tools-input" className={field} value={form.tools} onChange={(e) => setForm({ ...form, tools: e.target.value })} /></div>
          </div>
          <div><label className={label}>{t("autonomy")}</label>
            <select data-testid="gen-autonomy-select" className={field} value={form.autonomy_level} onChange={(e) => setForm({ ...form, autonomy_level: e.target.value })}>
              <option value="supervised">supervised</option>
              <option value="semi-autonomous">semi-autonomous</option>
              <option value="autonomous">autonomous</option>
            </select></div>
          <div className="flex gap-3 pt-2">
            <button data-testid="add-catalog-btn" onClick={addToCatalog}
              className="border border-border px-4 py-2 text-xs font-mono rounded-sm hover:border-primary hover:text-primary transition-colors duration-150">
              {t("add_to_catalog")}
            </button>
            <button data-testid="generate-direct-btn" onClick={() => generate({ definition: buildDefinition() })} disabled={generating}
              className="flex items-center gap-2 bg-primary text-primary-foreground px-5 py-2 text-xs font-semibold rounded-sm hover:opacity-90 transition-opacity duration-150 disabled:opacity-40">
              <Factory size={14} weight="fill" /> {generating ? "..." : t("generate_direct")}
            </button>
          </div>
        </div>

        <div className="border border-border rounded-sm bg-card">
          <div className="px-6 py-4 border-b border-border">
            <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">{t("catalog")}</p>
          </div>
          <div className="divide-y divide-border max-h-[480px] overflow-y-auto">
            {catalog.map((c) => (
              <div key={c.id} data-testid={`catalog-entry-${c.id}`} className="px-6 py-3 flex items-center gap-4">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{c.name}</p>
                  <p className="text-[10px] font-mono text-muted-foreground truncate">{c.category} · {c.pole} · {c.entity} · {c.autonomy_level}</p>
                </div>
                {c.generated_agent_id ? (
                  <Link to={`/agents/${c.generated_agent_id}`} className="text-xs font-mono text-emerald-400 hover:underline shrink-0">{c.generated_agent_id}</Link>
                ) : (
                  <>
                    <button data-testid={`catalog-generate-${c.id}`} onClick={() => generate({ catalog_id: c.id })} disabled={generating}
                      className="text-xs font-mono text-primary border border-primary/40 px-3 py-1 rounded-sm hover:bg-primary/10 transition-colors duration-150 shrink-0">
                      {t("generate")}
                    </button>
                    <button onClick={async () => { await api.delete(`/generator/catalog/${c.id}`); load(); }}
                      className="text-muted-foreground hover:text-destructive transition-colors duration-150 shrink-0"><Trash size={14} /></button>
                  </>
                )}
              </div>
            ))}
            {catalog.length === 0 && <p className="px-6 py-8 text-center text-xs font-mono text-muted-foreground">{t("no_results")}</p>}
          </div>
        </div>
      </div>

      {report && (
        <div data-testid="pipeline-report" className="border border-border rounded-sm bg-card p-6 space-y-4">
          <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-primary">{t("pipeline_result")}
            {report.agent_id && <Link to={`/agents/${report.agent_id}`} className="ml-3 text-emerald-400 hover:underline normal-case tracking-normal font-mono">→ {report.agent_id}</Link>}
          </p>
          <div className="space-y-1.5">
            {report.steps?.map((s, i) => (
              <div key={i} className="flex items-start gap-3 text-xs font-mono">
                {s.status === "ok" ? <CheckCircle size={15} weight="fill" className="text-emerald-400 shrink-0 mt-0.5" />
                  : <WarningCircle size={15} weight="fill" className={`${s.status === "warning" ? "text-amber-400" : "text-destructive"} shrink-0 mt-0.5`} />}
                <span className="text-foreground w-48 shrink-0">{s.step}</span>
                <span className="text-muted-foreground">{s.detail}</span>
              </div>
            ))}
          </div>
          {report.service_token && (
            <div className="border border-amber-900 bg-amber-950/20 rounded-sm p-4">
              <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-amber-400 mb-2">{t("service_token")}</p>
              <div className="flex items-center gap-3">
                <code data-testid="service-token-value" className="text-xs font-mono text-amber-300 break-all">{report.service_token}</code>
                <button onClick={() => { navigator.clipboard.writeText(report.service_token); toast.success("Copié"); }}
                  className="text-amber-400 hover:text-amber-200 shrink-0"><Copy size={15} /></button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
