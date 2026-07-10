import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useAuth } from "../context/AuthContext";
import { Target, Lightning, CheckCircle, XCircle } from "@phosphor-icons/react";

const STAGE_LABELS = ["specification", "design", "development", "testing", "security_review", "deployment", "monitoring"];
const STATUS_STYLE = { assigned: "text-sky-400 border-sky-900", in_progress: "text-amber-400 border-amber-900",
  delivered: "text-primary border-cyan-900", validated: "text-emerald-400 border-emerald-900", rejected: "text-red-400 border-red-900" };

export default function Missions() {
  const { t } = useLang();
  const { user } = useAuth();
  const [request, setRequest] = useState("");
  const [orch, setOrch] = useState(null);
  const [missions, setMissions] = useState([]);
  const [deliverFor, setDeliverFor] = useState(null);
  const [delivery, setDelivery] = useState({ summary: "", deliverables: "", recommendations: "" });

  const load = () => api.get("/missions").then((r) => setMissions(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const orchestrate = async () => {
    if (request.length < 5) return;
    try {
      const { data } = await api.post("/missions/orchestrate", { request_text: request });
      setOrch(data);
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const createMission = async () => {
    try {
      await api.post("/missions", { ...orch.draft_mission, origin_request: request });
      toast.success("Mission créée et assignée");
      setOrch(null); setRequest(""); load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const advance = async (id) => {
    try { await api.post(`/missions/${id}/advance`); load(); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const deliver = async () => {
    try {
      await api.post(`/missions/${deliverFor}/deliver`, {
        summary: delivery.summary,
        deliverables: delivery.deliverables.split("\n").filter(Boolean),
        recommendations: delivery.recommendations.split("\n").filter(Boolean) });
      toast.success("Mission livrée — notification envoyée au fondateur");
      setDeliverFor(null); setDelivery({ summary: "", deliverables: "", recommendations: "" }); load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const validate = async (id, decision) => {
    try { await api.post(`/missions/${id}/validate?decision=${decision}`); toast.success(decision); load(); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const field = "bg-background border border-input rounded-sm px-3 py-2 text-xs font-mono focus:outline-none focus:border-primary";

  return (
    <div data-testid="missions-page" className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3"><Target size={28} className="text-primary" /> Mission Assignment Engine</h1>
        <p className="text-xs text-muted-foreground font-mono mt-1">Intention → Orchestrator → agents compétents → mission → livraison → validation humaine</p>
      </div>

      <div className="border border-primary/30 rounded-sm bg-primary/5 p-6 space-y-4">
        <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-primary">Agent Orchestrator — écris ton intention</p>
        <div className="flex gap-3">
          <input data-testid="orchestrate-input" className={`${field} flex-1`}
            placeholder='Ex : "Analyse la stratégie digitale Factory Maker pour les 30 prochains jours"'
            value={request} onChange={(e) => setRequest(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && orchestrate()} />
          <button data-testid="orchestrate-btn" onClick={orchestrate}
            className="flex items-center gap-2 bg-primary text-primary-foreground px-5 py-2 text-xs font-semibold rounded-sm hover:opacity-90 transition-opacity duration-150">
            <Lightning size={14} weight="fill" /> Orchestrer
          </button>
        </div>
        {orch && (
          <div data-testid="orchestration-result" className="space-y-3">
            <p className="text-xs font-mono text-muted-foreground">
              Type détecté : <span className="text-primary">{orch.intent.mission_type}</span> · mots-clés : {orch.intent.keywords.slice(0, 8).join(", ")}
            </p>
            <div className="flex flex-wrap gap-2">
              {orch.recommended_agents.map((a) => (
                <span key={a.agent_id} className={`border px-2 py-1 rounded-sm text-xs font-mono ${orch.draft_mission.agent_ids.includes(a.agent_id) ? "border-primary text-primary" : "border-border text-muted-foreground"}`}>
                  {a.agent_id} {a.name} <span className="text-amber-400">({a.score})</span>
                </span>
              ))}
              {orch.recommended_agents.length === 0 && <p className="text-xs font-mono text-muted-foreground">Aucun agent compétent trouvé</p>}
            </div>
            {orch.recommended_agents.length > 0 && user?.role === "admin" && (
              <button data-testid="create-mission-btn" onClick={createMission}
                className="border border-primary/40 text-primary px-4 py-2 text-xs font-mono rounded-sm hover:bg-primary/10 transition-colors duration-150">
                Créer la mission → {orch.draft_mission.agent_ids.join(" + ")} ({orch.draft_mission.entity})
              </button>
            )}
          </div>
        )}
      </div>

      <div className="border border-border rounded-sm bg-card divide-y divide-border">
        {missions.map((m) => (
          <div key={m.id} data-testid={`mission-row-${m.id}`} className="px-6 py-4">
            <div className="flex items-center gap-3 flex-wrap">
              <span className={`text-[9px] uppercase tracking-widest px-1.5 py-0.5 border rounded-sm font-mono ${STATUS_STYLE[m.status]}`}>{m.status}</span>
              <p className="text-sm font-medium">{m.title}</p>
              <span className="text-xs font-mono text-primary">{m.agent_ids.join(", ")}</span>
              <span className="text-xs font-mono text-muted-foreground">{m.entity} · L{m.autonomy_level} · {m.mission_type}</span>
              <div className="ml-auto flex items-center gap-2">
                {["assigned", "in_progress"].includes(m.status) && user?.role !== "reader" && (
                  <>
                    <button data-testid={`advance-${m.id}`} onClick={() => advance(m.id)}
                      className="border border-border px-2 py-1 text-[10px] font-mono rounded-sm hover:border-primary hover:text-primary transition-colors duration-150">étape →</button>
                    <button data-testid={`deliver-${m.id}`} onClick={() => setDeliverFor(m.id)}
                      className="border border-primary/40 text-primary px-2 py-1 text-[10px] font-mono rounded-sm hover:bg-primary/10 transition-colors duration-150">Livrer</button>
                  </>
                )}
                {m.status === "delivered" && user?.role === "admin" && (
                  <>
                    <button data-testid={`validate-mission-${m.id}`} onClick={() => validate(m.id, "validated")} className="text-emerald-400 p-1"><CheckCircle size={17} weight="fill" /></button>
                    <button onClick={() => validate(m.id, "rejected")} className="text-red-400 p-1"><XCircle size={17} weight="fill" /></button>
                  </>
                )}
              </div>
            </div>
            <div className="flex items-center gap-1 mt-3">
              {STAGE_LABELS.map((s, i) => {
                const reached = STAGE_LABELS.indexOf(m.workflow_stage) >= i;
                return <div key={s} title={s} className={`h-1 flex-1 rounded-sm ${reached ? "bg-primary" : "bg-secondary"}`} />;
              })}
              <span className="text-[9px] font-mono text-muted-foreground ml-2">{m.workflow_stage}</span>
            </div>
            {m.delivery && (
              <p className="text-xs text-muted-foreground mt-2 font-mono">📦 {m.delivery.summary}</p>
            )}
          </div>
        ))}
        {missions.length === 0 && <p className="px-6 py-8 text-center text-xs font-mono text-muted-foreground">{t("no_results")}</p>}
      </div>

      {deliverFor && (
        <div className="border border-primary/40 rounded-sm bg-card p-6 space-y-3">
          <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-primary">Livraison de mission</p>
          <textarea data-testid="delivery-summary-input" required placeholder="Résumé du travail réalisé..." className={`${field} w-full h-16 resize-none`}
            value={delivery.summary} onChange={(e) => setDelivery({ ...delivery, summary: e.target.value })} />
          <div className="grid grid-cols-2 gap-3">
            <textarea placeholder="Livrables (1 par ligne)" className={`${field} h-16 resize-none`}
              value={delivery.deliverables} onChange={(e) => setDelivery({ ...delivery, deliverables: e.target.value })} />
            <textarea placeholder="Recommandations (1 par ligne)" className={`${field} h-16 resize-none`}
              value={delivery.recommendations} onChange={(e) => setDelivery({ ...delivery, recommendations: e.target.value })} />
          </div>
          <div className="flex gap-2">
            <button data-testid="delivery-submit-btn" onClick={deliver} disabled={delivery.summary.length < 10}
              className="bg-primary text-primary-foreground px-4 py-2 text-xs font-semibold rounded-sm disabled:opacity-40">Livrer + notifier le fondateur</button>
            <button onClick={() => setDeliverFor(null)} className="border border-border px-4 py-2 text-xs font-mono rounded-sm">{t("cancel")}</button>
          </div>
        </div>
      )}
    </div>
  );
}
