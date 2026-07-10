import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useLang } from "../lib/i18n";
import { Crown, CheckCircle, XCircle, Warning } from "@phosphor-icons/react";

const EMPTY = { type: "improve_agent", title: "", description: "", target_agent_id: "" };

export default function FounderCenter() {
  const { t } = useLang();
  const [ov, setOv] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [agents, setAgents] = useState([]);

  const load = () => api.get("/founder/overview").then((r) => setOv(r.data)).catch(() => {});
  useEffect(() => { load(); api.get("/registry/agents").then((r) => setAgents(r.data)).catch(() => {}); }, []);

  const decide = async (id, decision) => {
    try { await api.post(`/evolution/proposals/${id}/decide`, { decision, note: "" }); toast.success(decision); load(); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const propose = async (e) => {
    e.preventDefault();
    try {
      await api.post("/evolution/proposals", { ...form, target_agent_id: form.target_agent_id || null });
      toast.success(t("proposal_created")); setForm(EMPTY); load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  if (!ov) return <p className="text-muted-foreground font-mono text-sm">...</p>;

  const field = "bg-background border border-input rounded-sm px-3 py-2 text-xs font-mono focus:outline-none focus:border-primary";
  const label = "text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground block mb-1.5";
  const fmt = (n) => `${(n ?? 0).toLocaleString("fr-FR")} €`;
  const pv = ov.pending_validations;
  const pendingCount = pv.evolution_proposals.length + pv.beta_awaiting_production.length + pv.human_interventions.length + pv.knowledge_to_validate;

  return (
    <div data-testid="founder-page" className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3"><Crown size={28} className="text-amber-400" /> Founder Control Center</h1>
        <p className="text-xs text-muted-foreground font-mono mt-1">{ov.governance_model}</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-[1px] bg-border border border-border rounded-sm overflow-hidden">
        {[["Agents", `${ov.ecosystem.total_agents}/${ov.ecosystem.target}`, "text-primary"],
          [t("entities"), ov.ecosystem.entities, "text-foreground"],
          [t("pending_validations"), pendingCount, pendingCount > 0 ? "text-amber-400" : "text-emerald-400"],
          ["Net", fmt(ov.finance.net), ov.finance.net >= 0 ? "text-emerald-400" : "text-red-400"],
          [t("open_tasks_label"), ov.operations.open_tasks, "text-foreground"],
          ["CVLN Brain", ov.knowledge.total, "text-foreground"]].map(([l, v, c]) => (
          <div key={l} className="bg-card p-5">
            <p className={label}>{l}</p>
            <p className={`text-2xl font-bold font-mono ${c}`}>{v}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div data-testid="pending-validations" className="border border-amber-900/60 rounded-sm bg-amber-950/10">
          <div className="px-6 py-4 border-b border-amber-900/40 flex items-center gap-2">
            <Warning size={14} className="text-amber-400" />
            <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-amber-400">{t("pending_validations")} ({pendingCount})</p>
          </div>
          <div className="divide-y divide-border">
            {pv.evolution_proposals.map((p) => (
              <div key={p.id} data-testid={`proposal-${p.id}`} className="px-6 py-3 flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{p.title}</p>
                  <p className="text-[10px] font-mono text-muted-foreground">{p.type} · {p.target_agent_id || "—"} · {p.proposed_by}</p>
                </div>
                <button data-testid={`validate-proposal-${p.id}`} onClick={() => decide(p.id, "validated")}
                  className="text-emerald-400 hover:text-emerald-300 p-1"><CheckCircle size={17} weight="fill" /></button>
                <button data-testid={`reject-proposal-${p.id}`} onClick={() => decide(p.id, "rejected")}
                  className="text-red-400 hover:text-red-300 p-1"><XCircle size={17} weight="fill" /></button>
              </div>
            ))}
            {pv.beta_awaiting_production.map((a) => (
              <div key={a.id} className="px-6 py-3 flex items-center gap-3 text-xs font-mono">
                <span className="text-amber-400 uppercase tracking-widest text-[9px]">Beta→Prod</span>
                <Link to={`/agents/${a.id}`} className="text-primary hover:underline">{a.id}</Link>
                <span className="text-muted-foreground truncate">{a.name}</span>
              </div>
            ))}
            {pv.human_interventions.map((m, i) => (
              <div key={i} className="px-6 py-3 text-xs font-mono text-amber-400">⚑ {m}</div>
            ))}
            {pv.knowledge_to_validate > 0 && (
              <Link to="/knowledge" className="block px-6 py-3 text-xs font-mono text-primary hover:underline">
                {pv.knowledge_to_validate} {t("knowledge_pending_link")}
              </Link>
            )}
            {pendingCount === 0 && <p className="px-6 py-6 text-xs font-mono text-muted-foreground">{t("nothing_to_validate")}</p>}
          </div>
        </div>

        <div className="space-y-4">
          <form onSubmit={propose} className="border border-border rounded-sm bg-card p-6 space-y-3">
            <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-primary">Improvement Loop — {t("new_proposal")}</p>
            <div className="grid grid-cols-2 gap-3">
              <select data-testid="proposal-type-select" className={field} value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                {["improve_agent", "create_agent", "modify_workflow", "optimize_procedure"].map((x) => <option key={x}>{x}</option>)}
              </select>
              <select className={field} value={form.target_agent_id} onChange={(e) => setForm({ ...form, target_agent_id: e.target.value })}>
                <option value="">Agent cible —</option>
                {agents.map((a) => <option key={a.id} value={a.id}>{a.id}</option>)}
              </select>
            </div>
            <input data-testid="proposal-title-input" required minLength={5} placeholder={t("title")} className={`${field} w-full`}
              value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            <textarea data-testid="proposal-description-input" required minLength={10} placeholder="Description" className={`${field} w-full h-16 resize-none`}
              value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            <button data-testid="proposal-submit-btn" type="submit"
              className="bg-primary text-primary-foreground px-4 py-2 text-xs font-semibold rounded-sm hover:opacity-90 transition-opacity duration-150">
              {t("propose")}
            </button>
          </form>

          <div className="border border-border rounded-sm bg-card p-6">
            <p className={label}>{t("last_closing")}</p>
            {ov.last_closing ? (
              <div className="text-xs font-mono space-y-1.5">
                <p className="text-primary">{ov.last_closing.date} · {t("confidence")} {ov.last_closing.average_confidence ?? "—"}%</p>
                <p className="text-muted-foreground leading-relaxed">{ov.last_closing.executive_report?.headline}</p>
              </div>
            ) : <p className="text-xs font-mono text-muted-foreground">{t("no_results")}</p>}
            <p className={`${label} mt-4`}>Finance</p>
            <p className="text-xs font-mono text-muted-foreground">
              <span className="text-red-400">-{fmt(ov.finance.total_cost)}</span> · <span className="text-emerald-400">+{fmt(ov.finance.total_revenue)}</span> · {ov.security.denied_authorizations_total} {t("denied")} (audit)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
