import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useLang } from "../lib/i18n";
import { Trash } from "@phosphor-icons/react";

export default function Users() {
  const { t } = useLang();
  const [users, setUsers] = useState([]);
  const [identities, setIdentities] = useState([]);
  const [form, setForm] = useState({ email: "", name: "", password: "", role: "reader" });

  const load = () => {
    api.get("/users").then((r) => setUsers(r.data)).catch(() => {});
    api.get("/identity/service-identities").then((r) => setIdentities(r.data)).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  const createUser = async (e) => {
    e.preventDefault();
    try {
      await api.post("/users", form);
      toast.success(`${form.email} — ${form.role}`);
      setForm({ email: "", name: "", password: "", role: "reader" });
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const changeRole = async (id, role) => {
    try { await api.patch(`/users/${id}`, { role }); toast.success(role); load(); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const removeUser = async (id) => {
    try { await api.delete(`/users/${id}`); load(); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const field = "bg-background border border-input rounded-sm px-3 py-2 text-xs font-mono focus:outline-none focus:border-primary";

  return (
    <div data-testid="users-page" className="space-y-8">
      <h1 className="text-3xl font-bold tracking-tight">{t("users")}</h1>

      <form onSubmit={createUser} className="border border-border rounded-sm bg-card p-6 flex flex-wrap items-end gap-3">
        <div><label className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground block mb-1.5">{t("email")}</label>
          <input data-testid="user-email-input" type="email" required className={field} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
        <div><label className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground block mb-1.5">{t("name")}</label>
          <input data-testid="user-name-input" required className={field} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
        <div><label className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground block mb-1.5">{t("password")}</label>
          <input data-testid="user-password-input" type="password" required className={field} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
        <div><label className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground block mb-1.5">{t("role")}</label>
          <select data-testid="user-role-select" className={field} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            <option value="admin">{t("admin")}</option>
            <option value="operator">{t("operator")}</option>
            <option value="reader">{t("reader")}</option>
          </select></div>
        <button data-testid="create-user-btn" type="submit"
          className="bg-primary text-primary-foreground px-5 py-2 text-xs font-semibold rounded-sm hover:opacity-90 transition-opacity duration-150">
          {t("create_user")}
        </button>
      </form>

      <div className="border border-border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              {[t("email"), t("name"), t("role"), t("created_at"), ""].map((h, i) => (
                <th key={i} className="px-4 py-3 text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {users.map((u) => (
              <tr key={u.id} data-testid={`user-row-${u.email}`} className="hover:bg-secondary/40 transition-colors duration-100">
                <td className="px-4 py-3 font-mono text-xs">{u.email}</td>
                <td className="px-4 py-3">{u.name}</td>
                <td className="px-4 py-3">
                  <select value={u.role} onChange={(e) => changeRole(u.id, e.target.value)}
                    className="bg-background border border-input rounded-sm px-2 py-1 text-xs font-mono">
                    <option value="admin">admin</option>
                    <option value="operator">operator</option>
                    <option value="reader">reader</option>
                  </select>
                </td>
                <td className="px-4 py-3 font-mono text-[10px] text-muted-foreground">{u.created_at?.slice(0, 10)}</td>
                <td className="px-4 py-3">
                  <button data-testid={`delete-user-${u.email}`} onClick={() => removeUser(u.id)}
                    className="text-muted-foreground hover:text-destructive transition-colors duration-150"><Trash size={15} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="border border-border rounded-sm bg-card">
        <div className="px-6 py-4 border-b border-border">
          <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">{t("service_identities")}</p>
        </div>
        <div className="divide-y divide-border">
          {identities.map((i) => (
            <div key={i.id} className="px-6 py-3 flex items-center gap-4 text-xs font-mono">
              <span className="text-primary w-24">{i.agent_id}</span>
              <span className="text-foreground">{i.name}</span>
              <span className="text-muted-foreground ml-auto">{(i.scopes || []).join(" · ")}</span>
              <span className={`text-[9px] uppercase tracking-widest px-1.5 py-0.5 border rounded-sm ${i.active ? "text-emerald-400 border-emerald-900" : "text-zinc-500 border-zinc-800"}`}>
                {i.active ? "active" : "inactive"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
