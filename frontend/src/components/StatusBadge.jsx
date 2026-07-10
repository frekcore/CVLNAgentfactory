const COLORS = {
  Draft: "text-zinc-400 border-zinc-700 bg-zinc-900",
  Prototype: "text-sky-400 border-sky-900 bg-sky-950/40",
  Alpha: "text-indigo-400 border-indigo-900 bg-indigo-950/40",
  Beta: "text-amber-400 border-amber-900 bg-amber-950/40",
  Production: "text-emerald-400 border-emerald-900 bg-emerald-950/40",
  Maintenance: "text-yellow-400 border-yellow-900 bg-yellow-950/40",
  Archive: "text-zinc-500 border-zinc-800 bg-zinc-950",
};

export const StatusBadge = ({ status }) => (
  <span data-testid={`status-badge-${status}`}
    className={`inline-flex items-center px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest border rounded-sm ${COLORS[status] || COLORS.Draft}`}>
    {status}
  </span>
);
