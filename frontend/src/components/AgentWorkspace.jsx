import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useAuth } from "../context/AuthContext";

const STATUS_COLORS = { open: "text-sky-400 border-sky-900", in_progress: "text-amber-400 border-amber-900",
  done: "text-emerald-400 border-emerald-900", blocked: "text-red-400 border-red-900" };

export const AgentWorkspace = ({ agentId }) => {
  const { t } = useLang();
  const { user } = useAuth();
  const [ws, setWs] = useState(null);
  const [taskForm, setTaskForm] = useState({ title: "", priority: "P1" });

  const load = () => api.get(`/workforce/workspace/${agentId}`).then((r) => setWs(r.data)).catch(() => {});
  useEffect(() => { load(); }, [agentId]);

  if (!ws) return <p className="text-muted-foreground font-mono text-sm">{t("loading")}</p>;

  const addTask = async (e) => {
    e.preventDefault();
    try {
      await api.post("/workforce/tasks", { agent_id: agentId, title: taskForm.title, priority: taskForm.priority, entity: ws.agent.entity });
      toast.success(taskForm.title); setTaskForm({ title: "", priority: "P1" }); load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const setTaskStatus = async (id, status) => {
    try { await api.patch(`/workforce/tasks/${id}`, { status }); load(); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const setAutonomy = async (level) => {
    try {
      await api.post(`/workforce/agents/${agentId}/autonomy`, { level: Number(level), note: "console" });
      toast.success(`${t("autonomy")} → L${level}`); load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const field = "bg-background border border-input rounded-sm px-3 py-2 text-xs font-mono focus:outline-none focus:border-primary";
  const label = "text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-3";

  return (
    <div data-testid="agent-workspace" className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="border border-primary/30 rounded-sm bg-primary/5 p-5 lg:col-span-2">
        <p className={`${label} text-primary block`}>Briefing — {ws.briefing.date}</p>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className={label + " block"}>{t("objectives")}</p>
            {ws.briefing.objectives.map((o, i) => <p key={i} className="text-xs text-muted-foreground">› {o}</p>)}
          </div>
          <div>
            <p className={label + " block"}>{t("memory_context")}</p>
            {ws.briefing.memory_context.length ? ws.briefing.memory_context.map((m, i) => <p key={i} className="text-xs text-muted-foreground font-mono">▸ {m}</p>)
              : <p className="text-xs font-mono text-muted-foreground/50">—</p>}
            {ws.briefing.last_confidence != null && <p className="text-xs font-mono text-emerald-400 mt-2">{t("confidence")} : {ws.briefing.last_confidence}%</p>}
          </div>
        </div>
      </div>

      <div className="border border-border rounded-sm bg-card p-5">
        <p className={label + " block"}>{t("autonomy")}</p>
        <p className="text-sm font-mono text-primary">L{ws.agent.autonomy.level} — {ws.agent.autonomy.label}</p>
        <p className="text-xs text-muted-foreground mt-1">{ws.agent.autonomy.fr}</p>
        {user?.role === "admin" && (
          <select data-testid="autonomy-select" className={`${field} w-full mt-3`} value={ws.agent.autonomy.level}
            onChange={(e) => setAutonomy(e.target.value)}>
            <option value={1}>L1 — observation</option>
            <option value={2}>L2 — recommendation</option>
            <option value={3}>L3 — controlled-execution</option>
            <option value={4}>L4 — operational-autonomy</option>
          </select>
        )}
        <p className={label + " block mt-4"}>{t("memory")}</p>
        <p className="text-xs font-mono text-muted-foreground">
          {Object.entries(ws.memory.entries_by_scope).map(([s, n]) => `${s}:${n}`).join(" · ") || "—"} · snapshots:{ws.memory.snapshots}
        </p>
        <p className={label + " block mt-4"}>{t("entities")}</p>
        <p className="text-xs font-mono text-muted-foreground">{ws.entities.map((e) => e.name).join(" · ") || "—"}</p>
      </div>

      <div className="border border-border rounded-sm bg-card lg:col-span-2">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between">
          <p className={label} style={{ marginBottom: 0 }}>{t("tasks")} ({ws.tasks.filter((x) => x.status !== "done").length} {t("open_short")})</p>
        </div>
        {user?.role !== "reader" && (
          <form onSubmit={addTask} className="px-5 py-3 border-b border-border flex gap-2">
            <input data-testid="task-title-input" required minLength={3} placeholder={t("new_task")} className={`${field} flex-1`}
              value={taskForm.title} onChange={(e) => setTaskForm({ ...taskForm, title: e.target.value })} />
            <select data-testid="task-priority-select" className={field} value={taskForm.priority} onChange={(e) => setTaskForm({ ...taskForm, priority: e.target.value })}>
              <option>P0</option><option>P1</option><option>P2</option>
            </select>
            <button data-testid="add-task-btn" type="submit"
              className="bg-primary text-primary-foreground px-4 text-xs font-semibold rounded-sm hover:opacity-90 transition-opacity duration-150">+</button>
          </form>
        )}
        <div className="divide-y divide-border max-h-64 overflow-y-auto">
          {ws.tasks.map((tk) => (
            <div key={tk.id} data-testid={`task-row-${tk.id}`} className="px-5 py-2.5 flex items-center gap-3 text-xs">
              <span className={`font-mono ${tk.priority === "P0" ? "text-red-400" : tk.priority === "P1" ? "text-amber-400" : "text-muted-foreground"}`}>{tk.priority}</span>
              <span className={`flex-1 truncate ${tk.status === "done" ? "line-through text-muted-foreground" : ""}`}>{tk.title}</span>
              <select value={tk.status} onChange={(e) => setTaskStatus(tk.id, e.target.value)}
                className={`bg-background border rounded-sm px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-widest ${STATUS_COLORS[tk.status]}`}>
                {["open", "in_progress", "done", "blocked"].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          ))}
          {ws.tasks.length === 0 && <p className="px-5 py-6 text-xs font-mono text-muted-foreground">{t("no_results")}</p>}
        </div>
      </div>

      <div className="border border-border rounded-sm bg-card p-5">
        <p className={label + " block"}>{t("daily_reports_short")}</p>
        <div className="space-y-2">
          {ws.daily_reports.map((r) => (
            <div key={r.id} className="text-xs font-mono flex gap-3">
              <span className="text-primary">{r.date}</span>
              <span className="text-muted-foreground truncate flex-1">{r.tasks_done?.[0] || r.mission || "—"}</span>
              <span className="text-emerald-400">{r.confidence}%</span>
            </div>
          ))}
          {ws.daily_reports.length === 0 && <p className="text-xs font-mono text-muted-foreground/50">—</p>}
        </div>
        <p className={label + " block mt-4"}>{t("knowledge")}</p>
        <div className="space-y-1">
          {ws.knowledge.map((k) => <p key={k.id} className="text-xs font-mono text-muted-foreground truncate">◆ {k.title} <span className="text-primary">({k.category})</span></p>)}
          {ws.knowledge.length === 0 && <p className="text-xs font-mono text-muted-foreground/50">—</p>}
        </div>
      </div>
    </div>
  );
};
