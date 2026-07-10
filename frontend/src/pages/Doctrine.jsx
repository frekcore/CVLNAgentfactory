import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../lib/i18n";
import { Scroll, PlugsConnected } from "@phosphor-icons/react";

export default function Doctrine() {
  const { lang, t } = useLang();
  const { user } = useAuth();
  const [doctrine, setDoctrine] = useState(null);
  const [external, setExternal] = useState(null);
  const [registry, setRegistry] = useState([]);
  const [tab, setTab] = useState("v1");
  const [prop, setProp] = useState({ title: "", principle: "", category: "governance" });

  const load = () => {
    api.get("/doctrine").then((r) => setDoctrine(r.data)).catch(() => {});
    api.get("/external").then((r) => setExternal(r.data)).catch(() => {});
    api.get("/doctrine/registry").then((r) => setRegistry(r.data)).catch(() => {});
  };
  useEffect(load, []);

  const propose = async () => {
    try {
      await api.post("/doctrine/registry", prop);
      toast.success("Doctrine proposée");
      setProp({ title: "", principle: "", category: "governance" });
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const changeStatus = async (id, status) => {
    try { await api.post(`/doctrine/registry/${id}/status?status=${status}`); toast.success(`Statut : ${status}`); load(); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  if (!doctrine) return <p className="text-muted-foreground font-mono text-sm">{t("loading")}</p>;

  return (
    <div data-testid="doctrine-page" className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3"><Scroll size={28} className="text-primary" /> {t("doctrine_title")}</h1>
        <p className="text-xs text-muted-foreground font-mono mt-1">v{doctrine.version} — héritée automatiquement par chaque agent généré</p>
      </div>

      <div className="flex gap-6 border-b border-border">
        {[["v1", "Fondamentaux v1"], ["v2", `Registre v2 (${registry.length})`]].map(([k, l]) => (
          <button key={k} data-testid={`doctrine-tab-${k}`} onClick={() => setTab(k)}
            className={`pb-2 text-sm border-b-2 -mb-[1px] transition-colors duration-150 ${tab === k ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            {l}
          </button>
        ))}
      </div>

      {tab === "v2" && (
        <div className="space-y-4">
          {user?.role !== "reader" && (
            <div className="border border-border rounded-sm bg-card p-4 flex flex-wrap gap-2 items-end">
              <input data-testid="doctrine-prop-title" value={prop.title} onChange={(e) => setProp({ ...prop, title: e.target.value })}
                placeholder="Titre de la doctrine" className="bg-background border border-input rounded-sm px-3 py-1.5 text-xs font-mono flex-1 min-w-48" />
              <input data-testid="doctrine-prop-principle" value={prop.principle} onChange={(e) => setProp({ ...prop, principle: e.target.value })}
                placeholder="Principe (règle permanente)" className="bg-background border border-input rounded-sm px-3 py-1.5 text-xs font-mono flex-1 min-w-64" />
              <button data-testid="doctrine-propose-btn" onClick={propose}
                className="bg-primary text-primary-foreground px-4 py-1.5 text-xs font-semibold rounded-sm">Proposer</button>
            </div>
          )}
          <div className="border border-border rounded-sm bg-card divide-y divide-border">
            {registry.map((d) => (
              <div key={d.id} data-testid={`doctrine-reg-${d.id}`} className="px-4 py-3 flex items-center gap-3">
                <code className="text-[10px] font-mono text-amber-400 shrink-0 w-20">{d.id}</code>
                <span className={`text-[9px] uppercase tracking-widest px-1.5 py-0.5 border rounded-sm font-mono shrink-0 ${
                  d.status === "active" ? "text-emerald-400 border-emerald-900" :
                  d.status === "validee" ? "text-sky-400 border-sky-900" :
                  d.status === "proposition" ? "text-amber-400 border-amber-900" : "text-zinc-500 border-zinc-800"}`}>{d.status}</span>
                <span className="text-[9px] font-mono text-muted-foreground/60 shrink-0">v{d.version}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium truncate">{d.title}</p>
                  <p className="text-[10px] text-muted-foreground truncate">{d.principle}</p>
                </div>
                {user?.role === "admin" && d.status === "proposition" && (
                  <button data-testid={`doctrine-validate-${d.id}`} onClick={() => changeStatus(d.id, "validee")}
                    className="text-sky-400 text-[10px] border border-sky-900 px-2 py-0.5 rounded-sm shrink-0">Valider</button>
                )}
                {user?.role === "admin" && d.status === "validee" && (
                  <button data-testid={`doctrine-activate-${d.id}`} onClick={() => changeStatus(d.id, "active")}
                    className="text-emerald-400 text-[10px] border border-emerald-900 px-2 py-0.5 rounded-sm shrink-0">Activer</button>
                )}
                {user?.role === "admin" && d.status !== "archivee" && (
                  <button data-testid={`doctrine-archive-${d.id}`} onClick={() => changeStatus(d.id, "archivee")}
                    className="text-zinc-500 text-[10px] border border-zinc-800 px-2 py-0.5 rounded-sm shrink-0">Archiver</button>
                )}
              </div>
            ))}
            {registry.length === 0 && <p className="px-4 py-8 text-center text-xs font-mono text-muted-foreground">Registre vide</p>}
          </div>
        </div>
      )}

      {tab === "v1" && (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {doctrine.sections.map((s) => (
          <div key={s.key} data-testid={`doctrine-section-${s.key}`} className="border border-border rounded-sm bg-card p-6">
            <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-primary mb-4">{lang === "en" ? s.title_en : s.title_fr}</p>
            <ul className="space-y-3">
              {s.rules.map((r) => (
                <li key={r.id} className="flex gap-3 text-sm">
                  <code className="text-[10px] font-mono text-amber-400 shrink-0 pt-0.5">{r.id}</code>
                  <span className="leading-relaxed text-muted-foreground">{lang === "en" ? r.en : r.fr}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      )}

      {external && (
        <div className="border border-border rounded-sm bg-card p-6">
          <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-1 flex items-center gap-2">
            <PlugsConnected size={14} className="text-primary" /> {t("external_systems")}
          </p>
          <p className="text-xs text-muted-foreground mb-4">{external.principle}</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-[1px] bg-border border border-border rounded-sm overflow-hidden">
            {external.systems.map((s) => (
              <div key={s.key} data-testid={`external-system-${s.key}`} className="bg-card p-4">
                <p className="text-sm font-semibold">{s.name}</p>
                <p className="text-[10px] font-mono text-primary mt-1">/api/external/{s.key}</p>
                <p className="text-[10px] font-mono text-amber-400 mt-1 uppercase tracking-widest">reserved · 501</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
