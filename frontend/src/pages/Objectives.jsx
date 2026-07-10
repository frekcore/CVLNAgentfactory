import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../lib/i18n";
import { Compass } from "@phosphor-icons/react";

const STATUS_STYLE = {
  active: "text-emerald-400 border-emerald-900", paused: "text-zinc-400 border-zinc-700",
  waiting_validation: "text-amber-400 border-amber-900", done: "text-sky-400 border-sky-900",
  archived: "text-zinc-500 border-zinc-800",
};
const PRIO_STYLE = { P0: "text-red-400", P1: "text-amber-400", P2: "text-sky-400" };

export default function Objectives() {
  const { t } = useLang();
  const { user } = useAuth();
  const [objectives, setObjectives] = useState([]);
  const [pursue, setPursue] = useState(null);
  const [form, setForm] = useState({ title: "", priority: "P1", owner: "", next_action: "", requires_human_validation: false });

  const load = () => {
    api.get("/objectives").then((r) => setObjectives(r.data)).catch(() => {});
    api.get("/objectives/pursue").then((r) => setPursue(r.data)).catch(() => {});
  };
  useEffect(load, []);

  const create = async () => {
    try {
      await api.post("/objectives", form);
      toast.success("Objectif créé");
      setForm({ title: "", priority: "P1", owner: "", next_action: "", requires_human_validation: false });
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const setStatus = async (id, status) => {
    try { await api.patch(`/objectives/${id}`, { status }); toast.success(`Statut : ${status}`); load(); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  return (
    <div data-testid="objectives-page" className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3"><Compass size={28} className="text-primary" /> {t("objectives_nav")}</h1>
        <p className="text-xs font-mono text-muted-foreground mt-1">Objective Registry — ce que CVLN poursuit même quand Laurent n'est pas connecté</p>
      </div>

      {pursue && (
        <div data-testid="pursue-banner" className="border border-primary/30 rounded-sm bg-primary/5 p-4">
          <p className="text-sm font-semibold">{pursue.answer}</p>
        </div>
      )}

      {user?.role !== "reader" && (
        <div className="border border-border rounded-sm bg-card p-4 flex flex-wrap gap-2 items-end">
          <input data-testid="obj-title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="Titre de l'objectif" className="bg-background border border-input rounded-sm px-3 py-1.5 text-xs font-mono flex-1 min-w-48" />
          <input data-testid="obj-owner" value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })}
            placeholder="Propriétaire (AGT-011)" className="bg-background border border-input rounded-sm px-3 py-1.5 text-xs font-mono w-40" />
          <input data-testid="obj-next-action" value={form.next_action} onChange={(e) => setForm({ ...form, next_action: e.target.value })}
            placeholder="Prochaine action" className="bg-background border border-input rounded-sm px-3 py-1.5 text-xs font-mono flex-1 min-w-48" />
          <select data-testid="obj-priority" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}
            className="bg-background border border-input rounded-sm px-2 py-1.5 text-xs font-mono">
            {["P0", "P1", "P2"].map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <label className="flex items-center gap-2 text-[10px] font-mono text-muted-foreground">
            <input data-testid="obj-requires-validation" type="checkbox" checked={form.requires_human_validation}
              onChange={(e) => setForm({ ...form, requires_human_validation: e.target.checked })} />
            Validation Laurent requise
          </label>
          <button data-testid="obj-create-btn" onClick={create}
            className="bg-primary text-primary-foreground px-4 py-1.5 text-xs font-semibold rounded-sm">Créer</button>
        </div>
      )}

      <div className="border border-border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-xs font-mono">
          <thead><tr className="border-b border-border text-left">
            {["Code", "Titre", "Prio", "Propriétaire", "Statut", "Prochaine action", "Dernière activité", ""].map((h, i) => (
              <th key={i} className="px-4 py-3 text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground font-sans">{h}</th>
            ))}
          </tr></thead>
          <tbody className="divide-y divide-border">
            {objectives.map((o) => (
              <tr key={o.id} data-testid={`objective-row-${o.code}`} className="hover:bg-secondary/40 transition-colors duration-100">
                <td className="px-4 py-2.5 text-primary">{o.code}</td>
                <td className="px-4 py-2.5 max-w-xs truncate">{o.title}
                  {o.requires_human_validation && <span className="text-[8px] text-amber-400 ml-2 uppercase">👤 validation</span>}</td>
                <td className={`px-4 py-2.5 font-bold ${PRIO_STYLE[o.priority]}`}>{o.priority}</td>
                <td className="px-4 py-2.5 text-muted-foreground">{o.owner}</td>
                <td className="px-4 py-2.5"><span className={`text-[9px] uppercase tracking-widest px-1.5 py-0.5 border rounded-sm ${STATUS_STYLE[o.status]}`}>{o.status}</span></td>
                <td className="px-4 py-2.5 text-muted-foreground max-w-xs truncate">{o.next_action}</td>
                <td className="px-4 py-2.5 text-muted-foreground/60">{o.last_activity?.slice(0, 16).replace("T", " ")}</td>
                <td className="px-4 py-2.5">
                  {user?.role !== "reader" && o.status === "active" && (
                    <button data-testid={`obj-done-${o.code}`} onClick={() => setStatus(o.id, "done")} className="text-sky-400 text-[10px] border border-sky-900 px-2 py-0.5 rounded-sm">Terminer</button>
                  )}
                  {user?.role === "admin" && o.status === "waiting_validation" && (
                    <button data-testid={`obj-activate-${o.code}`} onClick={() => setStatus(o.id, "active")} className="text-emerald-400 text-[10px] border border-emerald-900 px-2 py-0.5 rounded-sm">Activer</button>
                  )}
                </td>
              </tr>
            ))}
            {objectives.length === 0 && <tr><td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">Aucun objectif — créez le premier objectif permanent</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
