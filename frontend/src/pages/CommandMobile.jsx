import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Crown, BellRinging, CheckCircle, XCircle, PaperPlaneTilt, Plugs, ArrowSquareOut } from "@phosphor-icons/react";

const LEVEL_STYLE = { 1: "border-red-900 text-red-400", 2: "border-amber-900 text-amber-400",
  3: "border-sky-900 text-sky-400", 4: "border-zinc-800 text-zinc-400" };

export default function CommandMobile() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [ov, setOv] = useState(null);
  const [notifs, setNotifs] = useState([]);
  const [settings, setSettings] = useState(null);
  const [missions, setMissions] = useState([]);

  const load = () => {
    api.get("/founder/overview").then((r) => setOv(r.data)).catch(() => {});
    api.get("/notifications?limit=30").then((r) => setNotifs(r.data)).catch(() => {});
    api.get("/notifications/settings").then((r) => setSettings(r.data)).catch(() => {});
    api.get("/missions?status=delivered").then((r) => setMissions(r.data)).catch(() => {});
  };
  useEffect(() => { load(); const id = setInterval(load, 30000); return () => clearInterval(id); }, []);

  const connectTelegram = async () => {
    try {
      const { data } = await api.post("/notifications/discover-chat");
      toast.success(`Telegram connecté — ${data.name} (chat ${data.chat_id})`);
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const testNotif = async () => {
    try {
      const { data } = await api.post("/notifications/test", {});
      if (data.pushed) {
        toast.success("Notification envoyée sur ton téléphone 📲");
      } else {
        toast.error(`Push Telegram indisponible — ${formatApiError(data.push_error) || "envoie /start au bot puis « Connecter Telegram »"}`);
      }
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const decideProposal = async (id, decision) => {
    try { await api.post(`/evolution/proposals/${id}/decide`, { decision, note: "mobile" }); toast.success(decision); load(); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const validateMission = async (id, decision) => {
    try { await api.post(`/missions/${id}/validate?decision=${decision}`); toast.success(decision); load(); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  if (!ov) return <div className="min-h-screen bg-background flex items-center justify-center"><p className="text-primary font-mono text-xs animate-pulse tracking-[0.3em] uppercase">CVLN Command</p></div>;

  const pv = ov.pending_validations;
  const decisions = pv.evolution_proposals.length + missions.length + pv.beta_awaiting_production.length;

  return (
    <div data-testid="command-mobile-page" className="min-h-screen bg-background text-foreground max-w-lg mx-auto pb-24">
      <header className="sticky top-0 z-20 bg-background/95 backdrop-blur border-b border-border px-5 py-4 flex items-center justify-between">
        <div>
          <p className="text-[9px] tracking-[0.35em] uppercase text-primary font-mono">CVLN Command</p>
          <p className="text-lg font-bold leading-tight">Founder OS</p>
        </div>
        <button data-testid="command-desktop-link" onClick={() => navigate("/")} className="text-muted-foreground p-2"><ArrowSquareOut size={18} /></button>
      </header>

      <div className="px-5 py-4 space-y-4">
        <div className="border border-primary/30 rounded-sm bg-primary/5 p-4">
          <p className="text-sm font-semibold">Votre organisation numérique a travaillé pendant votre absence.</p>
          <p className="text-[10px] font-mono text-muted-foreground mt-1">{ov.governance_model}</p>
        </div>

        <div className="grid grid-cols-3 gap-[1px] bg-border border border-border rounded-sm overflow-hidden">
          {[["Agents", `${ov.ecosystem.total_agents}/${ov.ecosystem.target}`],
            ["Décisions", decisions],
            ["Net €", (ov.finance.net ?? 0).toLocaleString("fr-FR")]].map(([l, v]) => (
            <div key={l} className="bg-card p-3 text-center">
              <p className="text-[9px] tracking-[0.2em] uppercase text-muted-foreground font-semibold">{l}</p>
              <p className="text-lg font-bold font-mono text-primary">{v}</p>
            </div>
          ))}
        </div>

        <div className="flex gap-2">
          {settings && !settings.founder_chat_connected && (
            <button data-testid="connect-telegram-btn" onClick={connectTelegram}
              className="flex-1 flex items-center justify-center gap-2 border border-amber-700 text-amber-400 py-2.5 text-xs font-semibold rounded-sm">
              <Plugs size={15} /> Connecter Telegram
            </button>
          )}
          <button data-testid="test-notification-btn" onClick={testNotif}
            className="flex-1 flex items-center justify-center gap-2 bg-primary text-primary-foreground py-2.5 text-xs font-semibold rounded-sm">
            <PaperPlaneTilt size={15} weight="fill" /> Notification test
          </button>
        </div>
        {settings && (
          <p className="text-[10px] font-mono text-muted-foreground">
            Telegram : {settings.founder_chat_connected ? <span className="text-emerald-400">connecté ✓</span> : <span className="text-amber-400">envoie /start au bot puis « Connecter »</span>}
          </p>
        )}

        <div data-testid="mobile-decisions" className="border border-amber-900/60 rounded-sm bg-amber-950/10">
          <p className="px-4 py-3 text-[10px] tracking-[0.2em] uppercase font-semibold text-amber-400 border-b border-amber-900/40">
            Décisions attendues ({decisions})
          </p>
          <div className="divide-y divide-border">
            {pv.evolution_proposals.map((p) => (
              <div key={p.id} className="px-4 py-3 flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium truncate">{p.title}</p>
                  <p className="text-[9px] font-mono text-muted-foreground">{p.type}</p>
                </div>
                <button data-testid={`mobile-validate-${p.id}`} onClick={() => decideProposal(p.id, "validated")} className="text-emerald-400 p-1"><CheckCircle size={20} weight="fill" /></button>
                <button onClick={() => decideProposal(p.id, "rejected")} className="text-red-400 p-1"><XCircle size={20} weight="fill" /></button>
              </div>
            ))}
            {missions.map((m) => (
              <div key={m.id} className="px-4 py-3 flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium truncate">Mission livrée : {m.title}</p>
                  <p className="text-[9px] font-mono text-muted-foreground">{m.agent_ids.join(", ")}</p>
                </div>
                <button data-testid={`mobile-mission-validate-${m.id}`} onClick={() => validateMission(m.id, "validated")} className="text-emerald-400 p-1"><CheckCircle size={20} weight="fill" /></button>
                <button onClick={() => validateMission(m.id, "rejected")} className="text-red-400 p-1"><XCircle size={20} weight="fill" /></button>
              </div>
            ))}
            {pv.beta_awaiting_production.slice(0, 5).map((a) => (
              <div key={a.id} className="px-4 py-3 text-xs font-mono">
                <span className="text-amber-400 text-[9px] uppercase tracking-widest mr-2">Beta→Prod</span>
                <span className="text-primary">{a.id}</span> <span className="text-muted-foreground">{a.name}</span>
              </div>
            ))}
            {decisions === 0 && <p className="px-4 py-5 text-xs font-mono text-muted-foreground">Rien à valider — le groupe tourne.</p>}
          </div>
        </div>

        <div data-testid="mobile-notifications" className="border border-border rounded-sm bg-card">
          <p className="px-4 py-3 text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground border-b border-border flex items-center gap-2">
            <BellRinging size={13} className="text-primary" /> Notifications
          </p>
          <div className="divide-y divide-border max-h-96 overflow-y-auto">
            {notifs.map((n) => (
              <div key={n.id} className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className={`text-[8px] uppercase tracking-widest px-1.5 py-0.5 border rounded-sm font-mono ${LEVEL_STYLE[n.level]}`}>N{n.level} {n.level_key}</span>
                  {n.pushed && <span className="text-[8px] font-mono text-emerald-400">📲 push</span>}
                  <span className="text-[9px] font-mono text-muted-foreground/60 ml-auto">{n.timestamp?.slice(5, 16).replace("T", " ")}</span>
                </div>
                <p className="text-xs font-medium mt-1">{n.title}</p>
                <p className="text-[10px] text-muted-foreground leading-relaxed">{n.message}</p>
              </div>
            ))}
            {notifs.length === 0 && <p className="px-4 py-5 text-xs font-mono text-muted-foreground">Aucune notification</p>}
          </div>
        </div>

        <p className="text-[9px] font-mono text-muted-foreground/50 text-center pt-2">
          {user?.email} · <button onClick={async () => { await logout(); navigate("/login"); }} className="underline">déconnexion</button>
        </p>
      </div>
    </div>
  );
}
