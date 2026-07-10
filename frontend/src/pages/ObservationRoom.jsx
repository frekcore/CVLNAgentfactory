import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { useLang } from "../lib/i18n";
import { Eye } from "@phosphor-icons/react";
import { StatusBadge } from "../components/StatusBadge";

export default function ObservationRoom() {
  const { t } = useLang();
  const [perf, setPerf] = useState([]);
  const [selected, setSelected] = useState(null);
  const [history, setHistory] = useState({ events: [], versions: [], reports: [] });

  useEffect(() => { api.get("/missions/performance").then((r) => setPerf(r.data)).catch(() => {}); }, []);

  const observe = async (agentId) => {
    setSelected(agentId);
    const [ev, vs, rp] = await Promise.all([
      api.get(`/events?source=${agentId}&limit=20`).catch(() => ({ data: [] })),
      api.get(`/registry/agents/${agentId}/versions`).catch(() => ({ data: [] })),
      api.get(`/daily/reports?agent_id=${agentId}`).catch(() => ({ data: [] })),
    ]);
    setHistory({ events: ev.data, versions: vs.data, reports: rp.data });
  };

  const scoreColor = (s) => (s >= 60 ? "text-emerald-400" : s >= 30 ? "text-amber-400" : "text-muted-foreground");

  return (
    <div data-testid="observation-page" className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3"><Eye size={28} className="text-primary" /> CVLN Observation Room</h1>
        <p className="text-xs text-muted-foreground font-mono mt-1">Agent Performance System — comportement, performance, évolution, apprentissage</p>
      </div>

      <div className="border border-border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-left">
              {["Agent", t("status"), "Score", t("tasks_done"), "Missions", t("confidence"), "Valeur nette"].map((h) => (
                <th key={h} className="px-4 py-3 text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border font-mono">
            {perf.map((p) => (
              <tr key={p.agent_id} data-testid={`perf-row-${p.agent_id}`} onClick={() => observe(p.agent_id)}
                className={`cursor-pointer hover:bg-secondary/40 transition-colors duration-100 ${selected === p.agent_id ? "bg-secondary/40" : ""}`}>
                <td className="px-4 py-2.5"><span className="text-primary">{p.agent_id}</span> <span className="font-sans">{p.name}</span></td>
                <td className="px-4 py-2.5"><StatusBadge status={p.status} /></td>
                <td className="px-4 py-2.5">
                  <span className={`text-sm font-bold ${scoreColor(p.performance_score)}`}>{p.performance_score}</span>
                  <span className="text-muted-foreground/50">/100</span>
                </td>
                <td className="px-4 py-2.5 text-muted-foreground">{p.tasks_done}</td>
                <td className="px-4 py-2.5 text-muted-foreground">{p.missions_validated}</td>
                <td className="px-4 py-2.5 text-muted-foreground">{p.avg_confidence != null ? `${p.avg_confidence}%` : "—"}</td>
                <td className={`px-4 py-2.5 ${p.net_value >= 0 ? "text-emerald-400" : "text-red-400"}`}>{p.net_value}€</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <div data-testid="observation-detail" className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="border border-border rounded-sm bg-card p-5">
            <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-3">
              Historique des actions — <Link to={`/agents/${selected}`} className="text-primary hover:underline">{selected}</Link>
            </p>
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {history.events.map((e) => (
                <p key={e.id} className="text-[10px] font-mono"><span className="text-primary">{e.topic}</span> <span className="text-muted-foreground/60">{e.timestamp?.slice(5, 16).replace("T", " ")}</span></p>
              ))}
              {history.events.length === 0 && <p className="text-xs font-mono text-muted-foreground/50">—</p>}
            </div>
          </div>
          <div className="border border-border rounded-sm bg-card p-5">
            <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-3">Replay des décisions (cycle de vie)</p>
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {history.versions.map((v) => (
                <p key={v.id} className="text-[10px] font-mono">
                  <span className="text-amber-400">{v.type}</span> v{v.version} → {v.status}
                  <span className="text-muted-foreground/60 block">{v.note}</span>
                </p>
              ))}
            </div>
          </div>
          <div className="border border-border rounded-sm bg-card p-5">
            <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-3">Apprentissage (rapports quotidiens)</p>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {history.reports.map((r) => (
                <div key={r.id} className="text-[10px] font-mono">
                  <span className="text-primary">{r.date}</span> · confiance <span className="text-emerald-400">{r.confidence}%</span>
                  {r.next_actions?.[0] && <span className="text-muted-foreground block">→ {r.next_actions[0]}</span>}
                </div>
              ))}
              {history.reports.length === 0 && <p className="text-xs font-mono text-muted-foreground/50">—</p>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
