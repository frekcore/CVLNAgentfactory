import { useEffect, useState } from "react";
import api from "../lib/api";
import { useLang } from "../lib/i18n";

export default function Events() {
  const { t } = useLang();
  const [events, setEvents] = useState([]);
  const [topic, setTopic] = useState("");
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    const id = setTimeout(() => {
      api.get(`/events?limit=200${topic ? `&topic=${topic}` : ""}`).then((r) => setEvents(r.data)).catch(() => {});
    }, 300);
    return () => clearTimeout(id);
  }, [topic]);

  return (
    <div data-testid="events-page" className="space-y-6">
      <h1 className="text-3xl font-bold tracking-tight">{t("events")}</h1>
      <input data-testid="events-topic-filter" value={topic} onChange={(e) => setTopic(e.target.value)}
        placeholder={`${t("topic")}… (agent.created, factory.compile…)`}
        className="w-96 bg-card border border-input rounded-sm px-3 py-2 text-xs font-mono focus:outline-none focus:border-primary" />
      <div className="border border-border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="border-b border-border text-left">
              {[t("topic"), t("source"), t("destination"), t("timestamp"), t("payload")].map((h) => (
                <th key={h} className="px-4 py-3 text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground font-sans">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {events.map((e) => (
              <tr key={e.id} data-testid={`event-row-${e.id}`} onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                className="cursor-pointer hover:bg-secondary/40 transition-colors duration-100 align-top">
                <td className="px-4 py-2.5 text-primary">{e.topic}</td>
                <td className="px-4 py-2.5 text-muted-foreground">{e.source}</td>
                <td className="px-4 py-2.5 text-muted-foreground">{e.destination}</td>
                <td className="px-4 py-2.5 text-muted-foreground/60">{e.timestamp?.slice(0, 19).replace("T", " ")}</td>
                <td className="px-4 py-2.5 text-muted-foreground max-w-xs">
                  <span className={expanded === e.id ? "whitespace-pre-wrap break-all" : "block truncate"}>{JSON.stringify(e.payload)}</span>
                </td>
              </tr>
            ))}
            {events.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">{t("no_results")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
