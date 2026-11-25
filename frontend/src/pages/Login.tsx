import { useState, type FormEvent, type ReactNode } from "react";
import { api, type Me } from "../api";
import { Brand, Mark } from "../components/Brand";
import { FingerprintIcon } from "../components/icons";
import { toast } from "../components/toast";
import {
  addThisDevice,
  declineOffer,
  loginWithPasskey,
  passkeyErrorMessage,
  passkeysSupported,
  shouldOfferPasskey,
  thisDevicePasskey,
} from "../passkey";

export function Login({ onLogin }: { onLogin: (me: Me) => void }) {
  const supported = passkeysSupported();
  // A device that logs in with its fingerprint starts there; the password is one tap away.
  const [showPassword, setShowPassword] = useState(() => !(supported && thisDevicePasskey()));
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"password" | "fingerprint" | null>(null);
  // Logged in with the password on a device that could use its fingerprint next time.
  const [offerFor, setOfferFor] = useState<Me | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy("password");
    setError(null);
    try {
      const me = await api.login(password);
      if (await shouldOfferPasskey()) setOfferFor(me);
      else onLogin(me);
    } catch (err) {
      setError(err instanceof Error ? err.message : "ההתחברות נכשלה");
    } finally {
      setBusy(null);
    }
  };

  const fingerprintLogin = async () => {
    setBusy("fingerprint");
    setError(null);
    try {
      onLogin(await loginWithPasskey());
    } catch (err) {
      setError(passkeyErrorMessage(err));
      if (!thisDevicePasskey()) setShowPassword(true);
    } finally {
      setBusy(null);
    }
  };

  if (offerFor) return <PasskeyOffer me={offerFor} onDone={onLogin} />;

  const fingerprintButton = (primary: boolean) => (
    <button
      type="button"
      className={primary ? "btn btn-primary btn-block btn-lg" : "btn btn-block"}
      onClick={fingerprintLogin}
      disabled={busy !== null}
    >
      <FingerprintIcon size={primary ? 24 : 20} />
      {busy === "fingerprint" ? "מחכה לטביעת האצבע…" : "כניסה עם טביעת אצבע"}
    </button>
  );

  return (
    <AuthShell>
      <h1 className="auth-title">כניסה</h1>
      <p className="auth-lead">החיובים החודשיים של הגנים, במקום אחד.</p>
      {showPassword ? (
          <form className="auth-form" onSubmit={submit}>
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
            <button className="btn btn-primary btn-block" disabled={busy !== null || !password}>
              {busy === "password" ? "מתחבר…" : "כניסה"}
            </button>
            {supported && (
              <>
                <p className="auth-or">או</p>
                {fingerprintButton(false)}
              </>
            )}
          </form>
        ) : (
          <>
            {fingerprintButton(true)}
            {error && <p className="form-error">{error}</p>}
            <button
              type="button"
              className="link-btn auth-switch"
              onClick={() => {
                setShowPassword(true);
                setError(null);
              }}
            >
              כניסה עם סיסמה
            </button>
          </>
        )}
    </AuthShell>
  );
}

/** Brand panel (paprika red) beside the form; on phones it sits on top. */
function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="auth">
      <div className="auth-brand">
        <Mark className="auth-watermark" />
        <Brand tone="reversed" size="lg" tagline />
      </div>
      <div className="auth-main">
        <div className="auth-card">{children}</div>
      </div>
    </div>
  );
}

/** Shown once after a password login on a phone (or computer) that has a fingerprint or face check. */
function PasskeyOffer({ me, onDone }: { me: Me; onDone: (me: Me) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enable = async () => {
    setBusy(true);
    setError(null);
    try {
      await addThisDevice();
      toast("מעכשיו אפשר להיכנס מהמכשיר הזה עם טביעת אצבע");
      onDone(me);
    } catch (err) {
      setError(passkeyErrorMessage(err, true));
      setBusy(false);
    }
  };

  const skip = () => {
    declineOffer();
    onDone(me);
  };

  return (
    <AuthShell>
      <span className="auth-icon">
        <FingerprintIcon size={30} />
      </span>
      <h1 className="auth-title">כניסה עם טביעת אצבע?</h1>
      <p className="auth-lead">בפעם הבאה אפשר להיכנס מהמכשיר הזה עם טביעת אצבע או זיהוי פנים, בלי להקליד סיסמה.</p>
      {error && <p className="form-error">{error}</p>}
      <button className="btn btn-primary btn-block btn-lg" onClick={enable} disabled={busy}>
        {busy ? "מפעיל…" : "הפעלה"}
      </button>
      <button className="btn btn-block" onClick={skip} disabled={busy}>
        לא עכשיו
      </button>
      <p className="hint">אפשר להפעיל גם אחר כך, מ״טביעת אצבע״ בראש האתר.</p>
    </AuthShell>
  );
}
