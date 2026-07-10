import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useAuth } from "../context/AuthContext";
import { BookOpen, CheckCircle } from "@phosphor-icons/react";

const EMPTY = { title: "", source_type: "document", category: "", content: "", target_agents: [] };

export default function Knowledge() {
  const { t } = useLang();
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [agents, setAgents] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [detail, setDetail] = useState(null);

  const load = () => {
    api.get("/knowledge/items").then((r) => setItems(r.data)).catch(() => {});
    api.get("/knowledge/brain/stats").then((r) => setStats(r.data)).catch(() => {});
  };
  useEffect(() => { load(); api.get("/registry/agents").then((r) => setAgents(r.data)).catch(() => {}); }, []);

  const ingest = async (e) => {
    e.preventDefault();
    try {
      const { data } = await api.post("/knowledge/ingest", { ...form, category: form.category || null });
      toast.success(`${data.title} → ${data.category}${data.auto_classified ? " (auto)" : ""}`);
      setForm(EMPTY); load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const validate = async (id) => {
    try { await api.post(`/knowledge/items/${id}/validate`); toast.success(t("validated")); load(); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const field = "bg-background border border-input rounded-sm px-3 py-2 text-xs font-mono focus:outline-none focus:border-primary";
  const label = "text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground block mb-1.5";
  const CATS = ["doctrine", "strategy", "process", "business", "history", "research", "founding_decisions"];

  return (
    <div data-testid="knowledge-page" className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3"><BookOpen size={28} className="text-primary" /> Knowledge Sovereignty</h1>
        <p className="text-xs text-muted-foreground font-mono mt-1">Source → Ingestion → AGT-002 → CVLN Brain → mémoire des agents</p>
      </div>

      {stats && (
        <div className="flex flex-wrap gap-2">
          <span className="border border-primary/40 text-primary px-3 py-1 text-xs font-mono rounded-sm">CVLN Brain : {stats.total} items</span>
          {Object.entries(stats.by_category).map(([c, n]) => (
            <span key={c} className="border border-border px-3 py-1 text-xs font-mono rounded-sm text-muted-foreground">{c} : {n}</span>
          ))}
        </div>
      )}

      <form onSubmit={ingest} className="border border-border rounded-sm bg-card p-6 space-y-3">
        <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-primary">{t("ingest_knowledge")}</p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div><label className={label}>{t("title")}</label>
            <input data-testid="knowledge-title-input" required className={`${field} w-full`} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></div>
          <div><label className={label}>Source</label>
            <select data-testid="knowledge-source-select" className={`${field} w-full`} value={form.source_type} onChange={(e) => setForm({ ...form, source_type: e.target.value })}>
              {["obsidian", "document", "note", "chatgpt", "claude", "markdown", "pdf", "other"].map((s) => <option key={s}>{s}</option>)}
            </select></div>
          <div><label className={label}>{t("category")} ({t("auto_if_empty")})</label>
            <select data-testid="knowledge-category-select" className={`${field} w-full`} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              <option value="">auto</option>
              {CATS.map((c) => <option key={c}>{c}</option>)}
            </select></div>
          <div><label className={label}>{t("target_agents")}</label>
            <select data-testid="knowledge-agents-select" multiple className={`${field} w-full h-16`} value={form.target_agents}
              onChange={(e) => setForm({ ...form, target_agents: [...e.target.selectedOptions].map((o) => o.value) })}>
              {agents.map((a) => <option key={a.id} value={a.id}>{a.id} — {a.name}</option>)}
            </select></div>
        </div>
        <div><label className={label}>{t("content")}</label>
          <textarea data-testid="knowledge-content-input" required className={`${field} w-full h-28 resize-none`} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} /></div>
        <button data-testid="knowledge-ingest-btn" type="submit"
          className="bg-primary text-primary-foreground px-5 py-2 text-xs font-semibold rounded-sm hover:opacity-90 transition-opacity duration-150">
          {t("ingest")}
        </button>
      </form>

      <div className="border border-border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-left">
              {[t("title"), "Source", t("category"), t("target_agents"), "V", t("status"), ""].map((h, i) => (
                <th key={i} className="px-4 py-3 text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border font-mono">
            {items.map((k) => (
              <tr key={k.id} data-testid={`knowledge-row-${k.id}`} className="hover:bg-secondary/40 cursor-pointer transition-colors duration-100"
                onClick={async () => setDetail((await api.get(`/knowledge/items/${k.id}`)).data)}>
                <td className="px-4 py-2.5 font-sans font-medium">{k.title}</td>
                <td className="px-4 py-2.5 text-muted-foreground">{k.source_type}</td>
                <td className="px-4 py-2.5 text-primary">{k.category}{k.auto_classified && <span className="text-amber-400 ml-1">*</span>}</td>
                <td className="px-4 py-2.5 text-muted-foreground">{(k.target_agents || []).join(", ") || "—"}</td>
                <td className="px-4 py-2.5 text-muted-foreground">v{k.version}</td>
                <td className="px-4 py-2.5">
                  <span className={`text-[9px] uppercase tracking-widest px-1.5 py-0.5 border rounded-sm ${k.status === "validated" ? "text-emerald-400 border-emerald-900" : "text-amber-400 border-amber-900"}`}>{k.status}</span>
                </td>
                <td className="px-4 py-2.5">
                  {user?.role === "admin" && k.status === "ingested" && (
                    <button data-testid={`validate-knowledge-${k.id}`} onClick={(e) => { e.stopPropagation(); validate(k.id); }}
                      className="text-emerald-400 hover:text-emerald-300 flex items-center gap-1"><CheckCircle size={14} /> {t("validate")}</button>
                  )}
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">{t("no_results")}</td></tr>}
          </tbody>
        </table>
      </div>

      {detail && (
        <div data-testid="knowledge-detail" className="border border-border rounded-sm bg-card p-6">
          <p className="text-sm font-semibold mb-2">{detail.title} <span className="text-primary font-mono text-xs ml-2">{detail.category}</span></p>
          <pre className="text-xs font-mono text-muted-foreground whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto">{detail.content}</pre>
        </div>
      )}
    </div>
  );
}
