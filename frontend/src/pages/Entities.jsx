import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useAuth } from "../context/AuthContext";
import { Buildings, Plus, X } from "@phosphor-icons/react";

const EMPTY = { name: "", type: "other", description: "", activities: "", data_domains: "", apis: "", objectives: "" };
const toList = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function Entities() {
  const { t } = useLang();
  const { user } = useAuth();
  const [entities, setEntities] = useState([]);
  const [agents, setAgents] = useState([]);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [showForm, setShowForm] = useState(false);
  const [linkAgent, setLinkAgent] = useState("");

  const load = () => api.get("/entities").then((r) => setEntities(r.data)).catch(() => {});
  useEffect(() => { load(); api.get("/registry/agents").then((r) => setAgents(r.data)).catch(() => {}); }, []);

  const openDetail = async (id) => {
    const { data } = await api.get(`/entities/${id}`);
    setSelected(data);
  };

  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/entities", { name: form.name, type: form.type, description: form.description,
        activities: toList(form.activities), data_domains: toList(form.data_domains),
        apis: toList(form.apis), objectives: toList(form.objectives) });
      toast.success(form.name); setForm(EMPTY); setShowForm(false); load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const link = async () => {
    if (!linkAgent || !selected) return;
    try {
      await api.post(`/entities/${selected.id}/agents`, { agent_ids: [linkAgent] });
      toast.success(`${linkAgent} → ${selected.name}`); setLinkAgent("");
      openDetail(selected.id); load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const unlink = async (agentId) => {
    await api.delete(`/entities/${selected.id}/agents/${agentId}`);
    openDetail(selected.id); load();
  };

  const field = "bg-background border border-input rounded-sm px-3 py-2 text-xs font-mono focus:outline-none focus:border-primary";
  const label = "text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground block mb-1.5";
  const isAdmin = user?.role === "admin";

  return (
    <div data-testid="entities-page" className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3"><Buildings size={28} className="text-primary" /> Entity Registry</h1>
          <p className="text-xs text-muted-foreground font-mono mt-1">Business Reality Layer — entités, activités, agents associés</p>
        </div>
        {isAdmin && (
          <button data-testid="new-entity-btn" onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 text-xs font-semibold rounded-sm hover:opacity-90 transition-opacity duration-150">
            <Plus size={14} /> {t("new_entity")}
          </button>
        )}
      </div>

      {showForm && (
        <form onSubmit={create} className="border border-border rounded-sm bg-card p-6 grid grid-cols-2 lg:grid-cols-4 gap-3 items-end">
          <div><label className={label}>{t("name")}</label>
            <input data-testid="entity-name-input" required className={`${field} w-full`} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div><label className={label}>Type</label>
            <select data-testid="entity-type-select" className={`${field} w-full`} value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
              {["holding", "brain", "musique", "ia", "media", "education", "tech", "creative", "other"].map((x) => <option key={x}>{x}</option>)}
            </select></div>
          <div className="col-span-2"><label className={label}>Description</label>
            <input className={`${field} w-full`} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
          <div><label className={label}>{t("activities")} ({t("comma_hint")})</label>
            <input className={`${field} w-full`} value={form.activities} onChange={(e) => setForm({ ...form, activities: e.target.value })} /></div>
          <div><label className={label}>Data ({t("comma_hint")})</label>
            <input className={`${field} w-full`} value={form.data_domains} onChange={(e) => setForm({ ...form, data_domains: e.target.value })} /></div>
          <div><label className={label}>APIs ({t("comma_hint")})</label>
            <input className={`${field} w-full`} value={form.apis} onChange={(e) => setForm({ ...form, apis: e.target.value })} /></div>
          <button data-testid="create-entity-btn" type="submit"
            className="bg-primary text-primary-foreground px-4 py-2 text-xs font-semibold rounded-sm hover:opacity-90 transition-opacity duration-150">{t("confirm")}</button>
        </form>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-[1px] bg-border border border-border rounded-sm overflow-hidden">
        {entities.map((e) => (
          <button key={e.id} data-testid={`entity-card-${e.name}`} onClick={() => openDetail(e.id)}
            className={`bg-card p-5 text-left hover:bg-secondary/40 transition-colors duration-100 ${selected?.id === e.id ? "outline outline-1 outline-primary" : ""}`}>
            <p className="text-sm font-semibold">{e.name}</p>
            <p className="text-[10px] font-mono uppercase tracking-widest text-primary mt-1">{e.type}</p>
            <p className="text-[10px] font-mono text-muted-foreground mt-2">{e.agent_count} agent(s)</p>
          </button>
        ))}
      </div>

      {selected && (
        <div data-testid="entity-detail" className="border border-border rounded-sm bg-card p-6 space-y-4">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-lg font-bold">{selected.name} <span className="text-[10px] font-mono uppercase tracking-widest text-primary ml-2">{selected.type}</span></p>
              <p className="text-xs text-muted-foreground mt-1">{selected.description}</p>
            </div>
            <button onClick={() => setSelected(null)} className="text-muted-foreground hover:text-foreground"><X size={16} /></button>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
            <div><p className={label}>{t("activities")}</p>{(selected.activities || []).map((a, i) => <p key={i} className="text-muted-foreground">› {a}</p>)}</div>
            <div><p className={label}>Data</p>{(selected.data_domains || []).map((a, i) => <p key={i} className="text-muted-foreground">› {a}</p>)}</div>
            <div><p className={label}>APIs</p>{(selected.apis || []).map((a, i) => <p key={i} className="text-muted-foreground">› {a}</p>)}</div>
            <div><p className={label}>{t("objectives")}</p>{(selected.objectives || []).map((a, i) => <p key={i} className="text-muted-foreground">› {a}</p>)}</div>
          </div>
          <div>
            <p className={label}>{t("linked_agents")}</p>
            <div className="flex flex-wrap gap-2 mb-3">
              {(selected.agents || []).map((a) => (
                <span key={a.id} className="flex items-center gap-2 border border-border px-2 py-1 rounded-sm text-xs font-mono">
                  <span className="text-primary">{a.id}</span> {a.name}
                  {isAdmin && <button onClick={() => unlink(a.id)} className="text-muted-foreground hover:text-destructive"><X size={11} /></button>}
                </span>
              ))}
            </div>
            {isAdmin && (
              <div className="flex gap-2">
                <select data-testid="link-agent-select" className={field} value={linkAgent} onChange={(e) => setLinkAgent(e.target.value)}>
                  <option value="">—</option>
                  {agents.filter((a) => !(selected.agents || []).some((x) => x.id === a.id)).map((a) => <option key={a.id} value={a.id}>{a.id} — {a.name}</option>)}
                </select>
                <button data-testid="link-agent-btn" onClick={link}
                  className="border border-primary/40 text-primary px-3 py-1.5 text-xs font-mono rounded-sm hover:bg-primary/10 transition-colors duration-150">{t("link")}</button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
