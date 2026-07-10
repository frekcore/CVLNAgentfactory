import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { useLang } from "../lib/i18n";
import { StatusBadge } from "../components/StatusBadge";

export default function Agents() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [agents, setAgents] = useState([]);
  const [search, setSearch] = useState("");
  const [pole, setPole] = useState("");
  const [entity, setEntity] = useState("");
  const [status, setStatus] = useState("");

  const load = () => {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (pole) params.set("pole", pole);
    if (entity) params.set("entity", entity);
    if (status) params.set("status", status);
    api.get(`/registry/agents?${params}`).then((r) => setAgents(r.data)).catch(() => {});
  };

  useEffect(() => { const id = setTimeout(load, 300); return () => clearTimeout(id); }, [search, pole, entity, status]);

  const [allAgents, setAllAgents] = useState([]);
  useEffect(() => { api.get("/registry/agents").then((r) => setAllAgents(r.data)).catch(() => {}); }, []);
  const poles = useMemo(() => [...new Set(allAgents.map((a) => a.pole))], [allAgents]);
  const entities = useMemo(() => [...new Set(allAgents.map((a) => a.entity))], [allAgents]);
  const statuses = ["Draft", "Prototype", "Alpha", "Beta", "Production", "Maintenance", "Archive"];

  const sel = "bg-card border border-input rounded-sm px-3 py-2 text-xs font-mono focus:outline-none focus:border-primary";

  return (
    <div data-testid="agents-page" className="space-y-6">
      <h1 className="text-3xl font-bold tracking-tight">{t("agents")}</h1>
      <div className="flex flex-wrap gap-3">
        <input data-testid="agents-search-input" value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder={t("search")} className={`${sel} w-64`} />
        <select data-testid="agents-pole-filter" value={pole} onChange={(e) => setPole(e.target.value)} className={sel}>
          <option value="">{t("all_poles")}</option>
          {poles.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select data-testid="agents-entity-filter" value={entity} onChange={(e) => setEntity(e.target.value)} className={sel}>
          <option value="">{t("all_entities")}</option>
          {entities.map((e) => <option key={e} value={e}>{e}</option>)}
        </select>
        <select data-testid="agents-status-filter" value={status} onChange={(e) => setStatus(e.target.value)} className={sel}>
          <option value="">{t("all_statuses")}</option>
          {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div className="border border-border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              {["ID", t("name"), t("pole"), t("entity"), t("version"), t("status")].map((h) => (
                <th key={h} className="px-4 py-3 text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {agents.map((a) => (
              <tr key={a.id} data-testid={`agent-row-${a.id}`} onClick={() => navigate(`/agents/${a.id}`)}
                className="cursor-pointer hover:bg-secondary/40 transition-colors duration-100">
                <td className="px-4 py-3 font-mono text-primary text-xs">{a.id}</td>
                <td className="px-4 py-3 font-medium">{a.name}{a.generated && <span className="ml-2 text-[9px] font-mono uppercase text-amber-400 border border-amber-900 px-1 rounded-sm">{t("generated")}</span>}</td>
                <td className="px-4 py-3 text-muted-foreground text-xs">{a.pole}</td>
                <td className="px-4 py-3 text-muted-foreground text-xs">{a.entity}</td>
                <td className="px-4 py-3 font-mono text-xs">{a.version}</td>
                <td className="px-4 py-3"><StatusBadge status={a.status} /></td>
              </tr>
            ))}
            {agents.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground text-xs font-mono">{t("no_results")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
