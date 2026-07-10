import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../lib/i18n";
import {
  SquaresFour, Robot, Code, Factory, Scroll, Broadcast, ShieldCheck,
  UsersThree, SignOut, Pulse, CalendarCheck, Crown, Buildings, BookOpen, CurrencyEur,
  Target, Eye, DeviceMobile, Brain, Gavel, Compass,
} from "@phosphor-icons/react";

const NAV = [
  { to: "/", key: "dashboard", icon: SquaresFour, end: true },
  { to: "/cognitive", key: "cognitive_nav", icon: Brain },
  { to: "/agents", key: "agents", icon: Robot },
  { to: "/missions", key: "missions_nav", icon: Target },
  { to: "/objectives", key: "objectives_nav", icon: Compass },
  { to: "/observation", key: "observation_nav", icon: Eye },
  { to: "/editor", key: "adl_editor", icon: Code },
  { to: "/generator", key: "generator", icon: Factory },
  { to: "/daily", key: "daily_closing", icon: CalendarCheck },
  { to: "/entities", key: "entities", icon: Buildings },
  { to: "/knowledge", key: "knowledge_nav", icon: BookOpen },
  { to: "/finance", key: "finance_nav", icon: CurrencyEur },
  { to: "/doctrine", key: "doctrine", icon: Scroll },
  { to: "/events", key: "events", icon: Broadcast },
  { to: "/audit", key: "audit", icon: ShieldCheck },
  { to: "/governance", key: "governance", icon: Gavel },
  { to: "/monitoring", key: "monitoring", icon: Pulse },
];

export const Layout = () => {
  const { user, logout } = useAuth();
  const { lang, setLang, t } = useLang();
  const navigate = useNavigate();

  const nav = user?.role === "admin"
    ? [NAV[0], { to: "/founder", key: "founder_center", icon: Crown },
       { to: "/command", key: "cvln_command", icon: DeviceMobile }, ...NAV.slice(1),
       { to: "/users", key: "users", icon: UsersThree }]
    : NAV;

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="w-60 shrink-0 border-r border-border flex flex-col fixed inset-y-0 bg-card z-20">
        <div className="px-5 py-6 border-b border-border">
          <p className="text-[10px] tracking-[0.3em] uppercase text-primary font-mono">CVLN</p>
          <h1 className="text-lg font-bold tracking-tight leading-tight mt-1">Agent Factory</h1>
          <p className="text-[10px] tracking-[0.15em] uppercase text-muted-foreground mt-1 font-mono">Agent OS Layer — V1</p>
        </div>
        <nav className="flex-1 py-4 overflow-y-auto">
          {nav.map(({ to, key, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} data-testid={`nav-${key}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-5 py-2.5 text-sm border-l-2 transition-colors duration-150 ${
                  isActive ? "border-primary text-primary bg-primary/5" : "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/50"}`}>
              <Icon size={17} weight="regular" />
              {t(key)}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-border p-4 space-y-3">
          <div className="flex items-center gap-1">
            {["fr", "en"].map((l) => (
              <button key={l} data-testid={`lang-${l}`} onClick={() => setLang(l)}
                className={`px-2 py-1 text-[11px] font-mono uppercase tracking-widest border rounded-sm transition-colors duration-150 ${
                  lang === l ? "border-primary text-primary" : "border-border text-muted-foreground hover:text-foreground"}`}>
                {l}
              </button>
            ))}
          </div>
          <div className="flex items-center justify-between">
            <div className="min-w-0">
              <p className="text-xs truncate">{user?.name || user?.email}</p>
              <p className="text-[10px] font-mono uppercase tracking-widest text-primary">{user?.role}</p>
            </div>
            <button data-testid="logout-btn" onClick={async () => { await logout(); navigate("/login"); }}
              className="text-muted-foreground hover:text-destructive transition-colors duration-150 p-1.5">
              <SignOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <main className="flex-1 ml-60 p-8">
        <Outlet />
      </main>
    </div>
  );
};
