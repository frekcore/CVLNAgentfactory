import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useLang } from "../lib/i18n";
import { Brain, PaperPlaneTilt, CheckCircle } from "@phosphor-icons/react";

const CLASS_STYLE = { rule: "text-red-400 border-red-900", decision: "text-amber-400 border-amber-900",
  instruction: "text-primary border-cyan-900", task: "text-sky-400 border-sky-900",
  idea: "text-emerald-400 border-emerald-900", hypothesis: "text-indigo-400 border-indigo-900",
  information: "text-zinc-400 border-zinc-800" };

export default function Cognitive() {
  const { t } = useLang();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [convId, setConvId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [temporal, setTemporal] = useState(null);
  const endRef = useRef(null);

  useEffect(() => { api.get("/cognitive/temporal?period=day").then((r) => setTemporal(r.data)).catch(() => {}); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const send = async () => {
    if (input.length < 2 || busy) return;
    const text = input;
    setInput(""); setBusy(true);
    setMessages((m) => [...m, { role: "user", content: text, id: "tmp" }]);
    try {
      const { data } = await api.post("/cognitive/chat", { message: text, conversation_id: convId });
      setConvId(data.conversation_id);
      setMessages((m) => [
        ...m.slice(0, -1),
        { role: "user", content: text, id: data.user_message_id, classification: data.classification,
          proposed_action: data.proposed_action, action_executed: false },
        { role: "assistant", content: data.reply, engine: data.engine, id: `a-${data.user_message_id}` },
      ]);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
      setMessages((m) => m.slice(0, -1));
    } finally { setBusy(false); }
  };

  const confirm = async (msgId) => {
    try {
      const { data } = await api.post(`/cognitive/confirm/${msgId}`);
      toast.success(`${data.type}${data.agent_id ? ` → ${data.agent_id}` : ""}`);
      setMessages((m) => m.map((x) => (x.id === msgId ? { ...x, action_executed: true } : x)));
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  return (
    <div data-testid="cognitive-page" className="flex flex-col h-[calc(100vh-64px)] max-w-4xl">
      <div className="mb-4">
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3"><Brain size={28} className="text-primary" /> Interface Cognitive</h1>
        <p className="text-xs text-muted-foreground font-mono mt-1">
          Conversation → Compréhension → Structuration → Mémoire → Action · moteur souverain + accélérateur LLM interchangeable
        </p>
        {temporal && (
          <p className="text-[10px] font-mono text-muted-foreground mt-2">
            Aujourd'hui : {temporal.events} événements · {temporal.tasks_done} tâches terminées · {temporal.missions_validated} missions validées · net {temporal.finance.net}€
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto border border-border rounded-sm bg-card p-5 space-y-4">
        {messages.length === 0 && (
          <div className="text-xs font-mono text-muted-foreground space-y-2">
            <p>Parle à ton organisation. Exemples :</p>
            <p className="text-primary">« Crée une analyse de la stratégie digitale Factory Maker »</p>
            <p className="text-primary">« Je décide de prioriser la génération des 283 agents ce trimestre »</p>
            <p className="text-primary">« Nouvelle règle : aucun agent ne passe en Production sans KPI mesuré »</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`max-w-[85%] ${m.role === "user" ? "ml-auto" : ""}`}>
            <div className={`rounded-sm border p-3 ${m.role === "user" ? "border-primary/40 bg-primary/5" : "border-border bg-background"}`}>
              <p className="text-sm whitespace-pre-wrap leading-relaxed">{m.content}</p>
            </div>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {m.classification && (
                <span className={`text-[9px] uppercase tracking-widest px-1.5 py-0.5 border rounded-sm font-mono ${CLASS_STYLE[m.classification]}`}>{m.classification}</span>
              )}
              {m.proposed_action && !m.action_executed && (
                <button data-testid={`confirm-action-${m.id}`} onClick={() => confirm(m.id)}
                  className="text-[10px] font-mono text-emerald-400 border border-emerald-900 px-2 py-0.5 rounded-sm hover:bg-emerald-950/40 transition-colors duration-150 flex items-center gap-1">
                  <CheckCircle size={11} weight="fill" /> {m.proposed_action}
                </button>
              )}
              {m.action_executed && <span className="text-[9px] font-mono text-emerald-400">✓ exécuté</span>}
              {m.engine && <span className="text-[9px] font-mono text-muted-foreground/50">{m.engine}</span>}
            </div>
          </div>
        ))}
        {busy && <p className="text-xs font-mono text-primary animate-pulse">CVLN analyse...</p>}
        <div ref={endRef} />
      </div>

      <div className="flex gap-3 mt-4">
        <input data-testid="cognitive-input" className="flex-1 bg-card border border-input rounded-sm px-4 py-3 text-sm focus:outline-none focus:border-primary"
          placeholder="Parle à ton organisation numérique..."
          value={input} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()} />
        <button data-testid="cognitive-send-btn" onClick={send} disabled={busy}
          className="bg-primary text-primary-foreground px-5 rounded-sm hover:opacity-90 transition-opacity duration-150 disabled:opacity-40">
          <PaperPlaneTilt size={18} weight="fill" />
        </button>
      </div>
    </div>
  );
}
