import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useAuth } from "../context/AuthContext";
import { CalendarCheck, Sun, CheckCircle, WarningCircle, Lock } from "@phosphor-icons/react";

const EMPTY = { agent_id: "", mission: "", tasks_done: "", results: "", data_produced: "", decisions: "", difficulties: "", alerts: "", next_actions: "", confidence: 80, human_intervention_needed: false, human_intervention_reason: "" };
const toList = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);

const List = ({ items, empty }) => (
  <ul className="space-y-1">
    {items?.length ? items.map((x, i) => <li key={i} className="text-xs flex gap-2"><span className="text-primary font-mono shrink-0">›</span><span className="text-muted-foreground">{x}</span></li>)
      : <li className="text-xs font-mono text-muted-foreground/50">{empty || "—"}</li>}
  </ul>
);

const Box = ({ title, children, accent }) => (
  <div className="border border-border rounded-sm bg-card p-5">
    <p className={`text-[10px] tracking-[0.2em] uppercase font-semibold mb-3 ${accent || "text-muted-foreground"}`}>{title}</p>
    {children}
  </div>
);

export default function DailyClosing() {
  const { t } = useLang();
  const { user } = useAuth();
  const [briefing, setBriefing] = useState(null);
  const [agents, setAgents] = useState([]);
  const [reports, setReports] = useState([]);
  const [closings, setClosings] = useState([]);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [closing, setClosing] = useState(false);
  const [closeResult, setCloseResult] = useState(null);

  const load = () => {
    api.get("/daily/briefing").then((r) => setBriefing(r.data)).catch(() => {});
    api.get("/registry/agents").then((r) => setAgents(r.data)).catch(() => {});
    api.get("/daily/reports").then((r) => setReports(r.data)).catch(() => {});
    api.get("/daily/closings").then((r) => setClosings(r.data)).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  const submitReport = async (e) => {
    e.preventDefault();
    try {
      await api.post("/daily/reports", {
        agent_id: form.agent_id, mission: form.mission,
        tasks_done: toList(form.tasks_done), results: toList(form.results),
        data_produced: toList(form.data_produced), decisions: toList(form.decisions),
        difficulties: toList(form.difficulties), alerts: toList(form.alerts),
        next_actions: toList(form.next_actions), confidence: Number(form.confidence),
        human_intervention_needed: form.human_intervention_needed,
        human_intervention_reason: form.human_intervention_reason,
      });
      toast.success(`Rapport quotidien — ${form.agent_id}`);
      setForm(EMPTY); load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const closeDay = async () => {
    if (!window.confirm(t("close_confirm"))) return;
    setClosing(true);
    try {
      const { data } = await api.post("/daily/close", { note: "" });
      setCloseResult(data);
      toast.success(`${t("day_closed")} — ${data.date}`);
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setClosing(false); }
  };

  const viewClosing = async (date) => {
    const { data } = await api.get(`/daily/closings/${date}`);
    setSelected(data);
  };

  const field = "w-full bg-background border border-input rounded-sm px-3 py-2 text-xs font-mono focus:outline-none focus:border-primary";
  const label = "text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground block mb-1.5";
  const report = selected || closeResult;

  return (
    <div data-testid="daily-closing-page" className="space-y-8">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3"><CalendarCheck size={28} className="text-primary" /> Daily Closing Service</h1>
          <p className="text-xs text-muted-foreground font-mono mt-1">Agents exécutent · Core Services organisent · Agent 000 supervise · Laurent décide</p>
        </div>
        {user?.role === "admin" && (
          <button data-testid="close-day-btn" onClick={closeDay} disabled={closing}
            className="flex items-center gap-2 bg-primary text-primary-foreground px-5 py-2.5 text-xs font-semibold rounded-sm hover:opacity-90 transition-opacity duration-150 disabled:opacity-40">
            <Lock size={14} weight="fill" /> {closing ? "..." : t("close_day")}
          </button>
        )}
      </div>

      {briefing && (
        <div data-testid="morning-briefing" className="border border-primary/30 rounded-sm bg-primary/5 p-6">
          <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-primary mb-1 flex items-center gap-2">
            <Sun size={14} weight="fill" /> Morning Briefing CVLN — {briefing.date}
          </p>
          <p className="text-sm mb-4">{briefing.message}</p>
          {briefing.first_day ? (
            <p className="text-xs font-mono text-muted-foreground">{briefing.recommendations[0]}</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div><p className={label}>{t("priorities")}</p><List items={briefing.priorities} /></div>
              <div><p className={label}>{t("urgencies")}</p><List items={briefing.urgencies} /></div>
              <div><p className={label}>{t("opportunities")}</p><List items={briefing.opportunities} /></div>
              <div><p className={label}>{t("recommendations")}</p><List items={briefing.recommendations} /></div>
            </div>
          )}
          {briefing.last_closing && (
            <p className="text-[10px] font-mono text-muted-foreground mt-4">
              {t("last_closing")} : {briefing.last_closing.date} · {briefing.last_closing.reports_received}/{briefing.last_closing.total_agents} rapports · confiance {briefing.last_closing.average_confidence ?? "—"}%
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <form onSubmit={submitReport} className="border border-border rounded-sm bg-card p-6 space-y-3">
          <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-primary">{t("agent_daily_report")}</p>
          <div className="grid grid-cols-2 gap-3">
            <div><label className={label}>Agent</label>
              <select data-testid="report-agent-select" required className={field} value={form.agent_id} onChange={(e) => setForm({ ...form, agent_id: e.target.value })}>
                <option value="">—</option>
                {agents.map((a) => <option key={a.id} value={a.id}>{a.id} — {a.name}</option>)}
              </select></div>
            <div><label className={label}>{t("confidence")} (%)</label>
              <input data-testid="report-confidence-input" type="number" min="0" max="100" className={field} value={form.confidence} onChange={(e) => setForm({ ...form, confidence: e.target.value })} /></div>
          </div>
          <div><label className={label}>{t("mission")}</label>
            <input data-testid="report-mission-input" className={field} value={form.mission} onChange={(e) => setForm({ ...form, mission: e.target.value })} /></div>
          <div className="grid grid-cols-2 gap-3">
            {[["tasks_done", t("tasks_done")], ["results", t("results")], ["data_produced", t("data_produced")], ["decisions", t("decisions")],
              ["difficulties", t("difficulties")], ["alerts", t("alerts")], ["next_actions", t("next_actions")]].map(([k, l]) => (
              <div key={k}><label className={label}>{l} <span className="normal-case tracking-normal">({t("one_per_line")})</span></label>
                <textarea data-testid={`report-${k}-input`} className={`${field} h-14 resize-none`} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></div>
            ))}
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-xs cursor-pointer mt-5">
                <input data-testid="report-intervention-checkbox" type="checkbox" checked={form.human_intervention_needed}
                  onChange={(e) => setForm({ ...form, human_intervention_needed: e.target.checked })} className="accent-cyan-400" />
                {t("human_intervention")}
              </label>
              {form.human_intervention_needed && (
                <input data-testid="report-intervention-reason" className={field} placeholder={t("reason")}
                  value={form.human_intervention_reason} onChange={(e) => setForm({ ...form, human_intervention_reason: e.target.value })} />
              )}
            </div>
          </div>
          <button data-testid="submit-report-btn" type="submit"
            className="bg-primary text-primary-foreground px-5 py-2 text-xs font-semibold rounded-sm hover:opacity-90 transition-opacity duration-150">
            {t("submit_report")}
          </button>
        </form>

        <div className="space-y-4">
          <div className="border border-border rounded-sm bg-card">
            <div className="px-6 py-4 border-b border-border">
              <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">{t("today_reports")} ({reports.length})</p>
            </div>
            <div className="divide-y divide-border max-h-56 overflow-y-auto">
              {reports.map((r) => (
                <div key={r.id} data-testid={`daily-report-${r.agent_id}`} className="px-6 py-2.5 flex items-center gap-3 text-xs font-mono">
                  <span className="text-primary w-20 shrink-0">{r.agent_id}</span>
                  <span className="text-muted-foreground truncate flex-1">{r.tasks_done?.[0] || r.mission || "—"}</span>
                  {r.human_intervention_needed && <WarningCircle size={13} weight="fill" className="text-amber-400 shrink-0" />}
                  <span className={r.confidence < 50 ? "text-red-400" : "text-emerald-400"}>{r.confidence}%</span>
                </div>
              ))}
              {reports.length === 0 && <p className="px-6 py-6 text-xs font-mono text-muted-foreground">{t("no_results")}</p>}
            </div>
          </div>
          <div className="border border-border rounded-sm bg-card">
            <div className="px-6 py-4 border-b border-border">
              <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">{t("closings_history")}</p>
            </div>
            <div className="divide-y divide-border max-h-56 overflow-y-auto">
              {closings.map((c) => (
                <button key={c.id} data-testid={`closing-row-${c.date}`} onClick={() => viewClosing(c.date)}
                  className="w-full px-6 py-2.5 flex items-center gap-4 text-xs font-mono hover:bg-secondary/40 transition-colors duration-100 text-left">
                  <span className="text-primary">{c.date}</span>
                  <span className="text-muted-foreground">v{c.system_version}</span>
                  <span className="text-muted-foreground">{c.general_state?.reports_received}/{c.general_state?.total_agents} rapports</span>
                  <span className="ml-auto text-emerald-400">{c.average_confidence ?? "—"}%</span>
                </button>
              ))}
              {closings.length === 0 && <p className="px-6 py-6 text-xs font-mono text-muted-foreground">{t("no_results")}</p>}
            </div>
          </div>
        </div>
      </div>

      {report && (
        <div data-testid="daily-report-detail" className="space-y-4">
          <div className="border border-amber-900/60 rounded-sm bg-amber-950/10 p-6">
            <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-amber-400 mb-2">{report.executive_report?.title}</p>
            <p className="text-sm font-semibold mb-1">{report.executive_report?.headline}</p>
            <p className="text-[10px] font-mono text-muted-foreground mb-4">{report.executive_report?.prepared_by} → {report.executive_report?.for}</p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div><p className={label}>{t("decisions_validation")}</p><List items={report.executive_report?.decisions_requiring_validation} empty={t("none")} /></div>
              <div><p className={label}>{t("strategic_highlights")}</p><List items={report.executive_report?.strategic_highlights} empty={t("none")} /></div>
              <div><p className={label}>{t("tomorrow_priorities")}</p><List items={report.executive_report?.tomorrow_top_priorities} empty={t("none")} /></div>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Box title={`${t("general_state")} — ${report.date}`}>
              <div className="text-xs font-mono space-y-1.5">
                <p>{t("active_agents")} : <span className="text-primary">{report.general_state.active_agents}/{report.general_state.total_agents}</span></p>
                <p>Rapports : {report.general_state.reports_received}</p>
                <p className="text-red-400">{t("agents_in_error")} : {report.general_state.agents_in_error.join(", ") || "0"}</p>
                <p className="text-amber-400">{t("agents_waiting")} : {report.general_state.agents_waiting.length}</p>
              </div>
            </Box>
            <Box title={t("production_day")}>
              <List items={[...report.production.projects_advanced.slice(0, 4), ...report.production.deliverables.slice(0, 3)]} empty={t("none")} />
            </Box>
            <Box title={t("intelligence")}>
              <List items={[...report.intelligence.new_knowledge.slice(0, 4), ...report.intelligence.patterns_detected.slice(0, 3)]} empty={t("none")} />
            </Box>
            <Box title={t("risks")} accent="text-red-400">
              <div className="text-xs font-mono space-y-1.5">
                <p>{t("denied_24h")} : {report.risks.security.denied_authorizations}</p>
                <p>{t("alerts")} : {report.risks.security.alerts.length}</p>
                <p>{t("inconsistencies")} : {report.risks.inconsistencies.join(", ") || "0"}</p>
              </div>
            </Box>
          </div>
          {report.steps && (
            <Box title="Pipeline">
              <div className="space-y-1.5">
                {report.steps.map((s, i) => (
                  <div key={i} className="flex items-start gap-3 text-xs font-mono">
                    {s.status === "ok" ? <CheckCircle size={15} weight="fill" className="text-emerald-400 shrink-0 mt-0.5" />
                      : <WarningCircle size={15} weight="fill" className="text-amber-400 shrink-0 mt-0.5" />}
                    <span className="w-48 shrink-0">{s.step}</span>
                    <span className="text-muted-foreground">{s.detail}</span>
                  </div>
                ))}
              </div>
            </Box>
          )}
        </div>
      )}
    </div>
  );
}
