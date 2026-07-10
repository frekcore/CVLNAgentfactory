import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../lib/i18n";
import { formatApiError } from "../lib/api";

export default function Login() {
  const { login } = useAuth();
  const { t } = useLang();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || err.message);
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center relative overflow-hidden">
      <div className="absolute inset-0 opacity-[0.04]"
        style={{ backgroundImage: "linear-gradient(hsl(180 100% 50%) 1px, transparent 1px), linear-gradient(90deg, hsl(180 100% 50%) 1px, transparent 1px)", backgroundSize: "48px 48px" }} />
      <div className="w-full max-w-md relative z-10 px-6">
        <p className="text-[11px] tracking-[0.4em] uppercase text-primary font-mono mb-2">CVLN — Agent Operating System Layer</p>
        <h1 className="text-4xl font-bold tracking-tight mb-1">{t("login_title")}</h1>
        <p className="text-sm text-muted-foreground mb-10 font-mono">Registry · ADL · Identity · Event Bus · Monitoring</p>
        <form onSubmit={submit} className="space-y-5 border border-border bg-card p-8 rounded-sm">
          <div>
            <label className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground block mb-2">{t("email")}</label>
            <input data-testid="login-email-input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-background border border-input rounded-sm px-3 py-2.5 text-sm font-mono focus:outline-none focus:border-primary transition-colors duration-150"
              placeholder="laurent@cvln.fr" />
          </div>
          <div>
            <label className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground block mb-2">{t("password")}</label>
            <input data-testid="login-password-input" type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-background border border-input rounded-sm px-3 py-2.5 text-sm font-mono focus:outline-none focus:border-primary transition-colors duration-150" />
          </div>
          {error && <p data-testid="login-error" className="text-xs text-destructive font-mono">{error}</p>}
          <button data-testid="login-submit-btn" type="submit" disabled={loading}
            className="w-full bg-primary text-primary-foreground py-2.5 text-sm font-semibold tracking-wide rounded-sm hover:opacity-90 transition-opacity duration-150 disabled:opacity-50">
            {loading ? "..." : t("sign_in")}
          </button>
        </form>
      </div>
    </div>
  );
}
