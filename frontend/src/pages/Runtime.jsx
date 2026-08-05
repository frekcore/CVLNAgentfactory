import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Circuitry, Play } from "@phosphor-icons/react";

const STEP_LABELS = ["observer", "lire_objectifs", "prioriser", "analyser", "preparer", "verifier_permissions", "executer", "journaliser", "closing"];

export default function Runtime() {
  const { user } = useAuth();
  const [mode, setMode] = useState(null);
  const [cycles, setCycles] = useState([]);
  const [status, setStatus] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [running, setRunning] = useState(false);

  const load = () => {
    api.get("/autonomous/mode").then((r) => setMode(r.data)).catch(() => {});
    api.get("/autonomous/cycles?limit=15").then((r) => setCycles(r.data)).catch(() => {});
    api.get("/runtime/status").then((r) => setStatus(r.data)).catch(() => {});
  };
  useEffect(load, []);

  const runCycle = async () => {
    setRunning(true);
    try {
      const { data } = await api.post("/autonomous/cycle");
      toast.success(data.summary);
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    setRunning(false);
  };

  const switchMode = async (m) => {
    try {
      await api.post("/autonomous/mode", { mode: m });
      toast.success(`Mode : ${m}`);
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  return (
    <div data-testid="runtime-page" className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3"><Circuitry size={28} className="text-primary" /> Runtime autonome</h1>
        <p className="text-xs font-mono text-muted-foreground mt-1">Pas une IA libre — un runtime gouverné, déterministe et traçable (cycle 9 étapes)</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Card label="Mode" value={mode?.mode || "…"} accent={mode?.mode === "dry_run" ? "text-amber-400" : "text-emerald-400"} testId="runtime-mode-card" />
        <Card label="Cycles dry run complets" value={mode?.completed_dry_runs ?? "…"} testId="runtime-dryruns-card" />
        <Card label="Agents actifs" value={status?.by_state?.actif ?? "…"} accent="text-emerald-400" testId="runtime-active-card" />
        <Card label="En sommeil" value={status?.by_state?.sommeil ?? "…"} accent="text-sky-400" testId="runtime-sleep-card" />
      </div>

      <div className="flex gap-3 items-center flex-wrap">
        {user?.role !== "reader" && (
          <button data-testid="run-cycle-btn" onClick={runCycle} disabled={running}
            className="bg-primary text-primary-foreground px-5 py-2 text-sm font-semibold rounded-sm flex items-center gap-2 disabled:opacity-50 hover:opacity-90 transition-opacity duration-150">
            <Play size={16} weight="fill" /> {running ? "Cycle en cours…" : "Lancer un cycle"}
          </button>
        )}
        {user?.role === "admin" && mode && (
          mode.mode === "dry_run" ? (
            <button data-testid="mode-live-btn" onClick={() => switchMode("live")} disabled={!mode.live_available}
              className="border border-emerald-900 text-emerald-400 px-4 py-2 text-xs font-mono rounded-sm disabled:opacity-40">
              Activer le mode LIVE {!mode.live_available && "(1 dry run requis)"}
            </button>
          ) : (
            <button data-testid="mode-dryrun-btn" onClick={() => switchMode("dry_run")}
              className="border border-amber-900 text-amber-400 px-4 py-2 text-xs font-mono rounded-sm">Repasser en DRY RUN</button>
          )
        )}
        <p className="text-[10px] font-mono text-muted-foreground">DRY RUN : aucune modification métier — simulation journalisée</p>
      </div>

      <div className="space-y-2">
        {cycles.map((c) => (
          <div key={c.id} data-testid={`cycle-row-${c.number}`} className="border border-border rounded-sm bg-card">
            <button onClick={() => setExpanded(expanded === c.id ? null : c.id)}
              className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-secondary/40 transition-colors duration-100">
              <span className="font-mono text-primary text-sm shrink-0">#{c.number}</span>
              <span className={`text-[9px] uppercase tracking-widest px-1.5 py-0.5 border rounded-sm font-mono shrink-0 ${
                c.mode === "dry_run" ? "text-amber-400 border-amber-900" : "text-emerald-400 border-emerald-900"}`}>{c.mode}</span>
              <span className={`text-[9px] uppercase tracking-widest px-1.5 py-0.5 border rounded-sm font-mono shrink-0 ${
                c.status === "completed" ? "text-emerald-400 border-emerald-900" :
                c.status === "error" ? "text-red-400 border-red-900" : "text-zinc-400 border-zinc-700"}`}>{c.status}</span>
              <span className="text-xs text-muted-foreground truncate flex-1">{c.summary || "—"}</span>
              <span className="text-[9px] font-mono text-muted-foreground/60 shrink-0">{c.started_at?.slice(0, 19).replace("T", " ")}</span>
            </button>
            {expanded === c.id && (
              <div className="px-4 pb-4 space-y-1 border-t border-border pt-3">
                {(c.steps || []).map((s) => (
                  <p key={s.step} className="text-[11px] font-mono">
                    <span className="text-primary">{s.step}. {s.name}</span>
                    <span className="text-muted-foreground ml-2">{s.detail}</span>
                  </p>
                ))}
                {(c.actions_blocked || []).length > 0 && (
                  <p className="text-[11px] font-mono text-amber-400 pt-1">
                    ⚠ {c.actions_blocked.length} action(s) bloquée(s)/escaladée(s) : {c.actions_blocked.map((a) => a.detail?.slice(0, 60)).join(" · ")}
                  </p>
                )}
              </div>
            )}
          </div>
        ))}
        {cycles.length === 0 && <p className="text-center text-xs font-mono text-muted-foreground py-8">Aucun cycle — lancez le premier DRY RUN</p>}
      </div>
    </div>
  );
}

const Card = ({ label, value, accent = "text-foreground", testId }) => (
  <div data-testid={testId} className="border border-border rounded-sm bg-card p-4">
    <p className="text-[9px] tracking-[0.2em] uppercase text-muted-foreground font-semibold">{label}</p>
    <p className={`text-2xl font-bold font-mono mt-1 ${accent}`}>{value}</p>
  </div>
);
