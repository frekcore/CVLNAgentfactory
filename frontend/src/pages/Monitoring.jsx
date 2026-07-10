import { useEffect, useState } from "react";
import api from "../lib/api";
import { useLang } from "../lib/i18n";
import { Pulse, Warning } from "@phosphor-icons/react";

export default function Monitoring() {
  const { t } = useLang();
  const [health, setHealth] = useState(null);
  const [dash, setDash] = useState(null);

  useEffect(() => {
    const load = () => {
      api.get("/monitoring/health").then((r) => setHealth(r.data)).catch(() => {});
      api.get("/monitoring/dashboard").then((r) => setDash(r.data)).catch(() => {});
    };
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  if (!health || !dash) return <p className="text-muted-foreground font-mono text-sm">{t("loading")}</p>;

  return (
    <div data-testid="monitoring-page" className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3"><Pulse size={28} className="text-primary" /> {t("monitoring")}</h1>
        <p className="text-xs text-muted-foreground font-mono mt-1">Lecture seule stricte — il alerte, il n'agit jamais</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-[1px] bg-border border border-border rounded-sm overflow-hidden">
        {health.services.map((s) => (
          <div key={s.name} data-testid={`service-health-${s.name}`} className="bg-card p-5">
            <div className="flex items-center gap-2 mb-2">
              <span className={`w-2 h-2 rounded-full ${s.status === "healthy" ? "bg-emerald-400" : "bg-red-500"} animate-pulse`} />
              <p className="text-sm font-semibold">{s.name}</p>
            </div>
            <p className="text-[10px] font-mono text-muted-foreground">{s.detail}</p>
            <p className={`text-[10px] font-mono uppercase tracking-widest mt-1 ${s.status === "healthy" ? "text-emerald-400" : "text-red-400"}`}>{s.status}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-[1px] bg-border border border-border rounded-sm overflow-hidden">
        {[[t("active_agents"), `${dash.active_agents} / ${dash.total_agents}`],
          [t("events_24h"), dash.events_24h],
          [t("denied_24h"), dash.denied_authz_24h],
          [t("alerts"), dash.alerts.length]].map(([l, v]) => (
          <div key={l} className="bg-card p-6">
            <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">{l}</p>
            <p className="text-3xl font-bold font-mono text-primary mt-2">{v}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="border border-border rounded-sm bg-card p-6">
          <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-4">{t("active_agents")} — {t("by_pole")}</p>
          <div className="space-y-2">
            {Object.entries(dash.active_by_pole).map(([p, n]) => (
              <div key={p} className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground text-xs">{p}</span>
                <span className="font-mono text-xs">{n}</span>
              </div>
            ))}
          </div>
          <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mt-6 mb-4">{t("by_entity")}</p>
          <div className="space-y-2">
            {Object.entries(dash.active_by_entity).map(([e, n]) => (
              <div key={e} className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground text-xs">{e}</span>
                <span className="font-mono text-xs">{n}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="border border-border rounded-sm bg-card">
          <div className="px-6 py-4 border-b border-border flex items-center gap-2">
            <Warning size={14} className="text-amber-400" />
            <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">{t("alerts")}</p>
          </div>
          <div className="divide-y divide-border max-h-64 overflow-y-auto">
            {dash.alerts.length === 0 && <p className="px-6 py-6 text-xs font-mono text-muted-foreground">{t("no_alerts")}</p>}
            {dash.alerts.map((a) => (
              <div key={a.id} className="px-6 py-3 text-xs font-mono">
                <span className="text-amber-400">{JSON.stringify(a.payload)}</span>
                <span className="text-muted-foreground/60 ml-2">{a.timestamp?.slice(0, 19).replace("T", " ")}</span>
              </div>
            ))}
          </div>
          <div className="px-6 py-4 border-t border-border">
            <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-3">{t("recent_events")}</p>
            <div className="space-y-1.5">
              {dash.recent_events.slice(0, 6).map((e) => (
                <div key={e.id} className="flex gap-3 text-[11px] font-mono">
                  <span className="text-primary w-36 truncate shrink-0">{e.topic}</span>
                  <span className="text-muted-foreground/60 truncate">{e.source}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
