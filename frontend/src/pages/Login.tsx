import { useState, type FormEvent } from "react";
import { api, type Me } from "../api";
import { Brand } from "../components/Brand";

export function Login({ onLogin }: { onLogin: (me: Me) => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogin(await api.login(password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "ההתחברות נכשלה");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <form className="login-card" onSubmit={submit}>
        <Brand large />
        <p className="login-lead">ניהול חיובים חודשיים</p>
        <label className="field">
          <span>סיסמה</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
            required
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button className="btn btn-primary btn-block" disabled={busy || !password}>
          {busy ? "מתחבר…" : "כניסה"}
        </button>
      </form>
    </div>
  );
}
