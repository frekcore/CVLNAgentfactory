import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { useLang } from "../lib/i18n";
import { StatusBadge } from "../components/StatusBadge";

const Bar = ({ label, value, max }) => (
  <div className="flex items-center gap-3">
    <span className="text-xs text-muted-foreground w-44 truncate shrink-0">{label}</span>
    <div className="flex-1 h-1.5 bg-secondary rounded-sm overflow-hidden">
      <div className="h-full bg-primary" style={{ width: `${max ? (value / max) * 100 : 0}%` }} />
    </div>
    <span className="text-xs font-mono w-8 text-right">{value}</span>
  </div>
);

export default function Dashboard() {
  const { t } = useLang();
  const [stats, setStats] = useState(null);
  const [events, setEvents] = useState([]);

  useEffect(() => {
    api.get("/registry/stats").then((r) => setStats(r.data)).catch(() => {});
    api.get("/events?limit=8").then((r) => setEvents(r.data)).catch(() => {});
  }, []);

  if (!stats) return <p className="text-muted-foreground font-mono text-sm">{t("loading")}</p>;

  const maxPole = Math.max(...Object.values(stats.by_pole || { x: 1 }), 1);
  const maxEntity = Math.max(...Object.values(stats.by_entity || { x: 1 }), 1);

  return (
    <div data-testid="dashboard-page" className="space-y-8">
      <div>
        <p className="text-[10px] tracking-[0.3em] uppercase text-primary font-mono mb-1">{t("ecosystem_state")}</p>
        <h1 className="text-4xl font-bold tracking-tight">
          <span data-testid="agents-count" className="text-primary font-mono">{stats.total}</span>
          <span className="text-muted-foreground font-mono text-2xl"> / {stats.target}</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1">{t("agents_registered")}</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-[1px] bg-border border border-border rounded-sm overflow-hidden">
        <div className="lg:col-span-4 bg-card p-6">
          <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-4">{t("by_status")}</p>
          <div className="space-y-2.5">
            {Object.entries(stats.by_status).map(([s, n]) => (
              <div key={s} className="flex items-center justify-between">
                <StatusBadge status={s} />
                <span className="text-sm font-mono">{n}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="lg:col-span-4 bg-card p-6">
          <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-4">{t("by_pole")}</p>
          <div className="space-y-2.5">
            {Object.entries(stats.by_pole).map(([p, n]) => <Bar key={p} label={p} value={n} max={maxPole} />)}
          </div>
        </div>
        <div className="lg:col-span-4 bg-card p-6">
          <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-4">{t("by_entity")}</p>
          <div className="space-y-2.5">
            {Object.entries(stats.by_entity).map(([e, n]) => <Bar key={e} label={e} value={n} max={maxEntity} />)}
          </div>
        </div>
      </div>

      <div className="border border-border rounded-sm bg-card">
        <div className="px-6 py-4 border-b border-border flex items-center justify-between">
          <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">{t("recent_events")}</p>
          <Link to="/events" data-testid="dashboard-events-link" className="text-xs text-primary font-mono hover:underline">→ {t("events")}</Link>
        </div>
        <div className="divide-y divide-border">
          {events.map((e) => (
            <div key={e.id} className="px-6 py-2.5 flex items-center gap-4 text-xs font-mono">
              <span className="text-primary w-40 truncate">{e.topic}</span>
              <span className="text-muted-foreground w-24 truncate">{e.source}</span>
              <span className="text-muted-foreground/60 ml-auto">{e.timestamp?.slice(0, 19).replace("T", " ")}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
