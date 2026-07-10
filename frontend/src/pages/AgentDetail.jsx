import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useAuth } from "../context/AuthContext";
import { StatusBadge } from "../components/StatusBadge";
import { ArrowLeft, DownloadSimple } from "@phosphor-icons/react";

const Section = ({ title, children }) => (
  <div className="border border-border rounded-sm bg-card p-5">
    <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-3">{title}</p>
    {children}
  </div>
);

export default function AgentDetail() {
  const { agentId } = useParams();
  const navigate = useNavigate();
  const { t } = useLang();
  const { user } = useAuth();
  const [agent, setAgent] = useState(null);
  const [versions, setVersions] = useState([]);
  const [tab, setTab] = useState("overview");
  const [diffFrom, setDiffFrom] = useState("");
  const [diffTo, setDiffTo] = useState("");
  const [diff, setDiff] = useState(null);

  const load = () => {
    api.get(`/registry/agents/${agentId}`).then((r) => setAgent(r.data)).catch(() => {});
    api.get(`/registry/agents/${agentId}/versions`).then((r) => setVersions(r.data)).catch(() => {});
  };
  useEffect(() => { load(); }, [agentId]);

  if (!agent) return <p className="text-muted-foreground font-mono text-sm">{t("loading")}</p>;

  const transition = async (target) => {
    const note = window.prompt(`${agent.status} → ${target} — ${t("note")} :`) || "";
    try {
      await api.post(`/registry/agents/${agentId}/lifecycle`, { target_status: target, note });
      toast.success(`${agent.status} → ${target}`);
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const exportYaml = async () => {
    const { data } = await api.get(`/registry/agents/${agentId}/export`);
    const blob = new Blob([data.adl_yaml], { type: "text/yaml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${agentId}.adl.yaml`;
    a.click();
  };

  const runDiff = async () => {
    if (!diffFrom || !diffTo) return;
    try {
      const { data } = await api.get(`/registry/agents/${agentId}/diff?from_version=${diffFrom}&to_version=${diffTo}`);
      setDiff(data.diff);
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const versionList = [...new Set(versions.filter((v) => v.type === "version").map((v) => v.version))];
  const tabs = ["overview", "adl", "timeline", "diff"];
  const canWrite = user?.role === "admin";

  return (
    <div data-testid="agent-detail-page" className="space-y-6">
      <button data-testid="back-btn" onClick={() => navigate("/agents")} className="flex items-center gap-2 text-xs text-muted-foreground hover:text-primary font-mono transition-colors duration-150">
        <ArrowLeft size={14} /> {t("agents")}
      </button>
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <p className="font-mono text-primary text-sm">{agent.id} · v{agent.version}</p>
          <h1 className="text-3xl font-bold tracking-tight mt-1">{agent.name}</h1>
          <p className="text-xs text-muted-foreground font-mono mt-1">{agent.pole} — {agent.entity}</p>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={agent.status} />
          <button data-testid="export-yaml-btn" onClick={exportYaml}
            className="flex items-center gap-2 border border-border px-3 py-1.5 text-xs font-mono rounded-sm hover:border-primary hover:text-primary transition-colors duration-150">
            <DownloadSimple size={14} /> {t("export_yaml")}
          </button>
        </div>
      </div>

      {canWrite && agent.allowed_transitions?.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] tracking-[0.2em] uppercase text-muted-foreground font-semibold">{t("lifecycle_transition")} :</span>
          {agent.allowed_transitions.map((s) => (
            <button key={s} data-testid={`transition-${s}-btn`} onClick={() => transition(s)}
              className="border border-border px-3 py-1 text-xs font-mono rounded-sm hover:border-primary hover:text-primary transition-colors duration-150">
              → {s}
            </button>
          ))}
        </div>
      )}

      <div className="flex gap-6 border-b border-border">
        {tabs.map((tb) => (
          <button key={tb} data-testid={`tab-${tb}`} onClick={() => setTab(tb)}
            className={`pb-2 text-sm border-b-2 -mb-[1px] transition-colors duration-150 ${tab === tb ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            {t(tb === "adl" ? "adl_editor" : tb).replace("Éditeur ADL", "ADL").replace("ADL Editor", "ADL")}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Section title={t("mission")}><p className="text-sm leading-relaxed">{agent.mission}</p></Section>
          <Section title={t("vision")}><p className="text-sm leading-relaxed text-muted-foreground">{agent.vision || "—"}</p></Section>
          <Section title={t("objectives")}>
            <ul className="space-y-1.5">{(agent.objectives || []).map((o, i) => <li key={i} className="text-sm flex gap-2"><span className="text-primary font-mono">›</span>{o}</li>)}</ul>
          </Section>
          <Section title={t("kpis")}>
            <ul className="space-y-1.5">{(agent.kpis || []).map((k, i) => <li key={i} className="text-sm flex gap-2 font-mono text-xs"><span className="text-primary">▸</span>{k}</li>)}</ul>
          </Section>
          <Section title={t("permissions")}>
            <pre className="text-xs font-mono text-muted-foreground whitespace-pre-wrap">{JSON.stringify(agent.adl?.permissions, null, 2)}</pre>
          </Section>
          <Section title={`${t("tools")} / ${t("knowledge")}`}>
            <div className="space-y-1.5 text-xs font-mono">
              {(agent.adl?.tools || []).map((tl, i) => <p key={i} className="text-foreground">⚙ {tl.name} <span className="text-muted-foreground">({tl.type})</span></p>)}
              {(agent.adl?.knowledge || []).map((k, i) => <p key={i} className="text-muted-foreground">◆ {k.source} ({k.type})</p>)}
            </div>
          </Section>
        </div>
      )}

      {tab === "adl" && (
        <pre data-testid="adl-yaml-view" className="border border-border rounded-sm bg-card p-5 text-xs font-mono leading-relaxed overflow-x-auto whitespace-pre-wrap text-emerald-300/90">
          {agent.adl_yaml}
        </pre>
      )}

      {tab === "timeline" && (
        <div className="border-l border-border ml-2 space-y-0">
          {versions.map((v) => (
            <div key={v.id} className="relative pl-6 pb-6">
              <span className={`absolute -left-[5px] top-1 w-2.5 h-2.5 rounded-full ${v.type === "lifecycle" ? "bg-primary" : "bg-amber-400"}`} />
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">{v.type}</span>
                <StatusBadge status={v.status} />
                <span className="text-xs font-mono">v{v.version}</span>
                <span className="text-[10px] font-mono text-muted-foreground/60">{v.timestamp?.slice(0, 19).replace("T", " ")}</span>
              </div>
              <p className="text-xs text-muted-foreground mt-1">{v.note} <span className="font-mono text-muted-foreground/60">— {v.actor}</span></p>
            </div>
          ))}
        </div>
      )}

      {tab === "diff" && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <select data-testid="diff-from-select" value={diffFrom} onChange={(e) => setDiffFrom(e.target.value)}
              className="bg-card border border-input rounded-sm px-3 py-2 text-xs font-mono">
              <option value="">from…</option>
              {versionList.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
            <span className="text-muted-foreground">→</span>
            <select data-testid="diff-to-select" value={diffTo} onChange={(e) => setDiffTo(e.target.value)}
              className="bg-card border border-input rounded-sm px-3 py-2 text-xs font-mono">
              <option value="">to…</option>
              {versionList.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
            <button data-testid="run-diff-btn" onClick={runDiff}
              className="bg-primary text-primary-foreground px-4 py-2 text-xs font-semibold rounded-sm hover:opacity-90 transition-opacity duration-150">{t("diff")}</button>
          </div>
          {diff && (
            <pre data-testid="diff-output" className="border border-border rounded-sm bg-card p-5 text-xs font-mono leading-relaxed overflow-x-auto">
              {diff.length === 0 ? <span className="text-muted-foreground">No differences</span> :
                diff.map((l, i) => (
                  <div key={i} className={l.startsWith("+") ? "text-emerald-400" : l.startsWith("-") ? "text-red-400" : "text-muted-foreground"}>{l}</div>
                ))}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
