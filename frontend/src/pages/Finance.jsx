import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useLang } from "../lib/i18n";
import { CurrencyEur } from "@phosphor-icons/react";

const EMPTY = { type: "cost", category: "api", agent_id: "", entity: "", amount: "", description: "" };

export default function Finance() {
  const { t } = useLang();
  const [summary, setSummary] = useState(null);
  const [entries, setEntries] = useState([]);
  const [agents, setAgents] = useState([]);
  const [entities, setEntities] = useState([]);
  const [form, setForm] = useState(EMPTY);

  const load = () => {
    api.get("/finance/summary").then((r) => setSummary(r.data)).catch(() => {});
    api.get("/finance/entries?limit=100").then((r) => setEntries(r.data)).catch(() => {});
  };
  useEffect(() => {
    load();
    api.get("/registry/agents").then((r) => setAgents(r.data)).catch(() => {});
    api.get("/entities").then((r) => setEntities(r.data)).catch(() => {});
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/finance/entries", { ...form, amount: Number(form.amount),
        agent_id: form.agent_id || null, entity: form.entity || null });
      toast.success(`${form.type} ${form.amount}€`);
      setForm(EMPTY); load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const field = "bg-background border border-input rounded-sm px-3 py-2 text-xs font-mono focus:outline-none focus:border-primary";
  const label = "text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground block mb-1.5";
  const fmt = (n) => (n == null ? "—" : `${n.toLocaleString("fr-FR")} €`);

  return (
    <div data-testid="finance-page" className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3"><CurrencyEur size={28} className="text-primary" /> Financial Intelligence</h1>
        <p className="text-xs text-muted-foreground font-mono mt-1">Digital CFO · Cost Intelligence · Accounting · Valuation</p>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-[1px] bg-border border border-border rounded-sm overflow-hidden">
          {[[t("total_costs"), fmt(summary.total_cost), "text-red-400"],
            [t("total_revenue"), fmt(summary.total_revenue), "text-emerald-400"],
            ["Net", fmt(summary.net), summary.net >= 0 ? "text-emerald-400" : "text-red-400"],
            ["ROI", summary.roi_percent == null ? "—" : `${summary.roi_percent}%`, "text-primary"],
            [t("forecast_30d"), fmt(summary.forecast_net_30d), "text-amber-400"]].map(([l, v, c]) => (
            <div key={l} className="bg-card p-5">
              <p className={label}>{l}</p>
              <p className={`text-xl font-bold font-mono ${c}`} data-testid={`finance-${l}`}>{v}</p>
            </div>
          ))}
        </div>
      )}

      <form onSubmit={submit} className="border border-border rounded-sm bg-card p-6 flex flex-wrap items-end gap-3">
        <div><label className={label}>Type</label>
          <select data-testid="finance-type-select" className={field} value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            <option value="cost">cost</option><option value="revenue">revenue</option>
          </select></div>
        <div><label className={label}>{t("category")}</label>
          <select data-testid="finance-category-select" className={field} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            {["api", "infrastructure", "software", "service", "production", "data", "other"].map((c) => <option key={c}>{c}</option>)}
          </select></div>
        <div><label className={label}>Agent</label>
          <select data-testid="finance-agent-select" className={field} value={form.agent_id} onChange={(e) => setForm({ ...form, agent_id: e.target.value })}>
            <option value="">—</option>
            {agents.map((a) => <option key={a.id} value={a.id}>{a.id}</option>)}
          </select></div>
        <div><label className={label}>{t("entity")}</label>
          <select className={field} value={form.entity} onChange={(e) => setForm({ ...form, entity: e.target.value })}>
            <option value="">—</option>
            {entities.map((en) => <option key={en.id} value={en.name}>{en.name}</option>)}
          </select></div>
        <div><label className={label}>{t("amount")} (€)</label>
          <input data-testid="finance-amount-input" type="number" step="0.01" min="0.01" required className={`${field} w-28`}
            value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
        <div className="flex-1 min-w-40"><label className={label}>Description</label>
          <input data-testid="finance-description-input" className={`${field} w-full`} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
        <button data-testid="finance-submit-btn" type="submit"
          className="bg-primary text-primary-foreground px-5 py-2 text-xs font-semibold rounded-sm hover:opacity-90 transition-opacity duration-150">
          {t("record")}
        </button>
      </form>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="border border-border rounded-sm bg-card">
          <div className="px-6 py-4 border-b border-border"><p className={label} style={{ marginBottom: 0 }}>{t("value_by_agent")}</p></div>
          <table className="w-full text-xs font-mono">
            <tbody className="divide-y divide-border">
              {summary && Object.entries(summary.by_agent).map(([aid, b]) => (
                <tr key={aid} className="hover:bg-secondary/40">
                  <td className="px-6 py-2.5 text-primary">{aid}</td>
                  <td className="px-4 py-2.5 text-red-400">-{b.cost}€</td>
                  <td className="px-4 py-2.5 text-emerald-400">+{b.revenue}€</td>
                  <td className="px-4 py-2.5">{b.net}€</td>
                  <td className="px-4 py-2.5 text-muted-foreground">ROI {b.roi == null ? "—" : `${b.roi}%`}</td>
                </tr>
              ))}
              {summary && Object.keys(summary.by_agent).length === 0 && <tr><td className="px-6 py-6 text-muted-foreground">{t("no_results")}</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="border border-border rounded-sm bg-card">
          <div className="px-6 py-4 border-b border-border"><p className={label} style={{ marginBottom: 0 }}>{t("recent_entries")}</p></div>
          <div className="divide-y divide-border max-h-72 overflow-y-auto">
            {entries.map((e) => (
              <div key={e.id} className="px-6 py-2.5 flex items-center gap-3 text-xs font-mono">
                <span className={e.type === "cost" ? "text-red-400" : "text-emerald-400"}>{e.type === "cost" ? "-" : "+"}{e.amount}€</span>
                <span className="text-muted-foreground">{e.category}</span>
                <span className="text-primary">{e.agent_id || e.entity || ""}</span>
                <span className="text-muted-foreground/60 truncate flex-1">{e.description}</span>
                <span className="text-muted-foreground/50">{e.date}</span>
              </div>
            ))}
            {entries.length === 0 && <p className="px-6 py-6 text-xs font-mono text-muted-foreground">{t("no_results")}</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
