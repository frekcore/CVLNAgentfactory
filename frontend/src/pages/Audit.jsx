import { useEffect, useState } from "react";
import api from "../lib/api";
import { useLang } from "../lib/i18n";

export default function Audit() {
  const { t } = useLang();
  const [logs, setLogs] = useState([]);
  const [filter, setFilter] = useState("");
  const [memLogs, setMemLogs] = useState([]);
  const [tab, setTab] = useState("authz");

  useEffect(() => {
    api.get(`/audit?limit=200${filter !== "" ? `&allowed=${filter}` : ""}`).then((r) => setLogs(r.data)).catch(() => {});
    api.get("/memory/logs?limit=100").then((r) => setMemLogs(r.data)).catch(() => {});
  }, [filter]);

  return (
    <div data-testid="audit-page" className="space-y-6">
      <h1 className="text-3xl font-bold tracking-tight">{t("audit")}</h1>
      <div className="flex gap-6 border-b border-border">
        {[["authz", t("audit")], ["memory", t("memory_logs")]].map(([k, l]) => (
          <button key={k} data-testid={`audit-tab-${k}`} onClick={() => setTab(k)}
            className={`pb-2 text-sm border-b-2 -mb-[1px] transition-colors duration-150 ${tab === k ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            {l}
          </button>
        ))}
      </div>

      {tab === "authz" && (
        <>
          <select data-testid="audit-allowed-filter" value={filter} onChange={(e) => setFilter(e.target.value)}
            className="bg-card border border-input rounded-sm px-3 py-2 text-xs font-mono focus:outline-none focus:border-primary">
            <option value="">{t("all")}</option>
            <option value="true">{t("allowed")}</option>
            <option value="false">{t("denied")}</option>
          </select>
          <div className="border border-border rounded-sm overflow-hidden bg-card">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-border text-left">
                  {["", t("actor"), t("action"), t("resource"), t("reason"), t("timestamp")].map((h, i) => (
                    <th key={i} className="px-4 py-3 text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground font-sans">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {logs.map((l) => (
                  <tr key={l.id} className="hover:bg-secondary/40 transition-colors duration-100">
                    <td className="px-4 py-2.5">
                      <span className={`text-[9px] uppercase tracking-widest px-1.5 py-0.5 border rounded-sm ${l.allowed ? "text-emerald-400 border-emerald-900" : "text-red-400 border-red-900"}`}>
                        {l.allowed ? "OK" : "DENY"}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-foreground">{l.actor_name || l.actor_id} <span className="text-muted-foreground/60">({l.actor_type})</span></td>
                    <td className="px-4 py-2.5 text-primary">{l.action}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{l.resource}</td>
                    <td className="px-4 py-2.5 text-muted-foreground max-w-xs truncate">{l.reason}</td>
                    <td className="px-4 py-2.5 text-muted-foreground/60">{l.timestamp?.slice(0, 19).replace("T", " ")}</td>
                  </tr>
                ))}
                {logs.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">{t("no_results")}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === "memory" && (
        <div className="border border-border rounded-sm overflow-hidden bg-card">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-border text-left">
                {[t("actor"), "Agent", "Operation", "Key", t("timestamp")].map((h) => (
                  <th key={h} className="px-4 py-3 text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground font-sans">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {memLogs.map((l) => (
                <tr key={l.id} className="hover:bg-secondary/40 transition-colors duration-100">
                  <td className="px-4 py-2.5 text-foreground">{l.actor_id} <span className="text-muted-foreground/60">({l.actor_type})</span></td>
                  <td className="px-4 py-2.5 text-primary">{l.agent_id}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">{l.operation}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">{l.key || "—"}</td>
                  <td className="px-4 py-2.5 text-muted-foreground/60">{l.timestamp?.slice(0, 19).replace("T", " ")}</td>
                </tr>
              ))}
              {memLogs.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">{t("no_results")}</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
