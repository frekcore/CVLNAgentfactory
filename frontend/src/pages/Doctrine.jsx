import { useEffect, useState } from "react";
import api from "../lib/api";
import { useLang } from "../lib/i18n";
import { Scroll, PlugsConnected } from "@phosphor-icons/react";

export default function Doctrine() {
  const { lang, t } = useLang();
  const [doctrine, setDoctrine] = useState(null);
  const [external, setExternal] = useState(null);

  useEffect(() => {
    api.get("/doctrine").then((r) => setDoctrine(r.data)).catch(() => {});
    api.get("/external").then((r) => setExternal(r.data)).catch(() => {});
  }, []);

  if (!doctrine) return <p className="text-muted-foreground font-mono text-sm">{t("loading")}</p>;

  return (
    <div data-testid="doctrine-page" className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3"><Scroll size={28} className="text-primary" /> {t("doctrine_title")}</h1>
        <p className="text-xs text-muted-foreground font-mono mt-1">v{doctrine.version} — héritée automatiquement par chaque agent généré</p>
      </div>

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
