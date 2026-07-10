import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../lib/i18n";

const TYPE_STYLE = {
  observation: "text-sky-400 border-sky-900", analyse: "text-cyan-400 border-cyan-900",
  proposition: "text-violet-400 border-violet-900", decision_humaine: "text-amber-400 border-amber-900",
  action_executee: "text-emerald-400 border-emerald-900", action_bloquee: "text-red-400 border-red-900",
  erreur: "text-red-500 border-red-800", cloture: "text-zinc-400 border-zinc-700",
};

export default function Governance() {
  const { t } = useLang();
  const { user } = useAuth();
  const [tab, setTab] = useState("journal");
  const [entries, setEntries] = useState([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [types, setTypes] = useState([]);
  const [rules, setRules] = useState([]);
  const [levels, setLevels] = useState(null);
  const [validations, setValidations] = useState([]);
  const [rule, setRule] = useState({ scope: "action_type", target_id: "", action_type: "execute", level: 5, note: "" });

  const load = () => {
    api.get(`/journal?limit=200${typeFilter ? `&type=${typeFilter}` : ""}`).then((r) => setEntries(r.data)).catch(() => {});
    api.get("/journal/types").then((r) => setTypes(r.data)).catch(() => {});
    api.get("/gate/rules").then((r) => setRules(r.data)).catch(() => {});
    api.get("/gate/levels").then((r) => setLevels(r.data)).catch(() => {});
    api.get("/gate/validation-requests").then((r) => setValidations(r.data)).catch(() => {});
  };
  useEffect(load, [typeFilter]);

  const createRule = async () => {
    try {
      await api.post("/gate/rules", { ...rule, target_id: rule.target_id || null, level: Number(rule.level) });
      toast.success("Règle créée");
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const decide = async (id, decision) => {
    try {
      await api.post(`/gate/validation-requests/${id}/decide?decision=${decision}`);
      toast.success(decision === "approved" ? "Validation approuvée" : "Validation rejetée");
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  return (
    <div data-testid="governance-page" className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{t("governance")}</h1>
        <p className="text-xs font-mono text-muted-foreground mt-1">Permission Gate v2 · Activity Journal v2 — CVLN-GOV-PHASE1-001</p>
      </div>
      <div className="flex gap-6 border-b border-border">
        {[["journal", "Journal v2"], ["refusals", `Refus`], ["rules", "Règles Gate"], ["validations", `Validations (${validations.filter((v) => v.status === "pending").length})`]].map(([k, l]) => (
          <button key={k} data-testid={`gov-tab-${k}`} onClick={() => setTab(k)}
            className={`pb-2 text-sm border-b-2 -mb-[1px] transition-colors duration-150 ${tab === k ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            {l}
          </button>
        ))}
      </div>

      {tab === "journal" && (
        <>
          <select data-testid="journal-type-filter" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}
            className="bg-card border border-input rounded-sm px-3 py-2 text-xs font-mono focus:outline-none focus:border-primary">
            <option value="">{t("all")}</option>
            {types.map((ty) => <option key={ty} value={ty}>{ty}</option>)}
          </select>
          <JournalTable entries={entries} emptyLabel={t("no_results")} />
        </>
      )}

      {tab === "refusals" && <JournalTable entries={entries.filter((e) => e.type === "action_bloquee")} emptyLabel="Aucun refus journalisé" />}

      {tab === "rules" && (
        <div className="space-y-4">
          {user?.role === "admin" && levels && (
            <div className="border border-border rounded-sm bg-card p-4 flex flex-wrap gap-2 items-end">
              <Field label="Portée">
                <select data-testid="rule-scope" value={rule.scope} onChange={(e) => setRule({ ...rule, scope: e.target.value })} className="bg-background border border-input rounded-sm px-2 py-1.5 text-xs font-mono">
                  {["action_type", "agent", "mission"].map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              {rule.scope !== "action_type" && (
                <Field label="Cible (ID)">
                  <input data-testid="rule-target" value={rule.target_id} onChange={(e) => setRule({ ...rule, target_id: e.target.value })} placeholder="AGT-011" className="bg-background border border-input rounded-sm px-2 py-1.5 text-xs font-mono w-32" />
                </Field>
              )}
              <Field label="Type d'action">
                <select data-testid="rule-action-type" value={rule.action_type} onChange={(e) => setRule({ ...rule, action_type: e.target.value })} className="bg-background border border-input rounded-sm px-2 py-1.5 text-xs font-mono">
                  {Object.keys(levels.default_action_levels).map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              </Field>
              <Field label="Niveau">
                <select data-testid="rule-level" value={rule.level} onChange={(e) => setRule({ ...rule, level: e.target.value })} className="bg-background border border-input rounded-sm px-2 py-1.5 text-xs font-mono">
                  {Object.entries(levels.levels).map(([n, v]) => <option key={n} value={n}>{n} — {v.fr}</option>)}
                </select>
              </Field>
              <button data-testid="rule-create-btn" onClick={createRule} className="bg-primary text-primary-foreground px-4 py-1.5 text-xs font-semibold rounded-sm">Créer la règle</button>
            </div>
          )}
          {levels && (
            <p className="text-[10px] font-mono text-amber-400">Actions critiques (validation Laurent non contournable) : {levels.critical_actions.join(" · ")}</p>
          )}
          <div className="border border-border rounded-sm overflow-hidden bg-card">
            <table className="w-full text-xs font-mono">
              <thead><tr className="border-b border-border text-left">
                {["Portée", "Cible", "Action", "Niveau", "Note", "Créée par"].map((h) => <th key={h} className="px-4 py-3 text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground font-sans">{h}</th>)}
              </tr></thead>
              <tbody className="divide-y divide-border">
                {rules.map((r) => (
                  <tr key={r.id} className="hover:bg-secondary/40">
                    <td className="px-4 py-2.5 text-primary">{r.scope}</td>
                    <td className="px-4 py-2.5">{r.target_id || "global"}</td>
                    <td className="px-4 py-2.5">{r.action_type}</td>
                    <td className="px-4 py-2.5 text-amber-400">{r.level}</td>
                    <td className="px-4 py-2.5 text-muted-foreground max-w-xs truncate">{r.note}</td>
                    <td className="px-4 py-2.5 text-muted-foreground/60">{r.created_by}</td>
                  </tr>
                ))}
                {rules.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">Aucune règle — niveaux par défaut appliqués</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "validations" && (
        <div className="border border-border rounded-sm bg-card divide-y divide-border">
          {validations.map((v) => (
            <div key={v.id} data-testid={`validation-row-${v.id}`} className="px-4 py-3 flex items-center gap-3">
              <span className={`text-[9px] uppercase tracking-widest px-1.5 py-0.5 border rounded-sm font-mono ${v.status === "pending" ? "text-amber-400 border-amber-900" : v.status === "approved" ? "text-emerald-400 border-emerald-900" : "text-red-400 border-red-900"}`}>{v.status}</span>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium truncate">{v.summary}</p>
                <p className="text-[9px] font-mono text-muted-foreground">{v.action_type} · {v.requested_by} · {v.created_at?.slice(0, 19).replace("T", " ")}{v.critical && <span className="text-red-400 ml-2">CRITIQUE</span>}</p>
              </div>
              {v.status === "pending" && user?.role === "admin" && (
                <>
                  <button data-testid={`validation-approve-${v.id}`} onClick={() => decide(v.id, "approved")} className="text-emerald-400 text-xs border border-emerald-900 px-2 py-1 rounded-sm">Approuver</button>
                  <button data-testid={`validation-reject-${v.id}`} onClick={() => decide(v.id, "rejected")} className="text-red-400 text-xs border border-red-900 px-2 py-1 rounded-sm">Rejeter</button>
                </>
              )}
            </div>
          ))}
          {validations.length === 0 && <p className="px-4 py-8 text-center text-xs font-mono text-muted-foreground">Aucune demande de validation</p>}
        </div>
      )}
    </div>
  );
}

const Field = ({ label, children }) => (
  <div className="space-y-1">
    <p className="text-[9px] tracking-[0.2em] uppercase text-muted-foreground font-semibold">{label}</p>
    {children}
  </div>
);

const JournalTable = ({ entries, emptyLabel }) => (
  <div data-testid="journal-table" className="border border-border rounded-sm overflow-hidden bg-card">
    <table className="w-full text-xs font-mono">
      <thead><tr className="border-b border-border text-left">
        {["Type", "Acteur", "Résumé", "Confiance", "Résultat", "Horodatage"].map((h) => (
          <th key={h} className="px-4 py-3 text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground font-sans">{h}</th>
        ))}
      </tr></thead>
      <tbody className="divide-y divide-border">
        {entries.map((e) => (
          <tr key={e.id} className="hover:bg-secondary/40 transition-colors duration-100">
            <td className="px-4 py-2.5"><span className={`text-[9px] uppercase tracking-widest px-1.5 py-0.5 border rounded-sm ${TYPE_STYLE[e.type] || "text-zinc-400 border-zinc-700"}`}>{e.type}</span></td>
            <td className="px-4 py-2.5 text-foreground">{e.actor_name || e.actor_id} <span className="text-muted-foreground/60">({e.actor_type})</span></td>
            <td className="px-4 py-2.5 text-muted-foreground max-w-md truncate">{e.summary}</td>
            <td className="px-4 py-2.5 text-muted-foreground">{e.confidence ?? "—"}</td>
            <td className="px-4 py-2.5 text-muted-foreground">{e.result || "—"}</td>
            <td className="px-4 py-2.5 text-muted-foreground/60">{e.timestamp?.slice(0, 19).replace("T", " ")}</td>
          </tr>
        ))}
        {entries.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">{emptyLabel}</td></tr>}
      </tbody>
    </table>
  </div>
);
