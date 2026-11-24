import { useCallback, useEffect, useState } from "react";
import { api, type Passkey } from "../api";
import { addThisDevice, forgetThisDevice, hasBuiltInCheck, passkeyErrorMessage, thisDevicePasskey } from "../passkey";
import { FingerprintIcon } from "./icons";
import { Modal } from "./Modal";
import { toast, toastError } from "./toast";

const formatDate = (iso: string) => new Date(iso).toLocaleDateString("he-IL");

/** The devices that log in with their fingerprint: add this one, or remove a lost one. */
export function PasskeysModal({ onClose }: { onClose: () => void }) {
  const [items, setItems] = useState<Passkey[] | null>(null);
  const [canAdd, setCanAdd] = useState(false);
  const [busy, setBusy] = useState(false);
  const mine = thisDevicePasskey();

  const load = useCallback(() => api.passkeys().then(setItems, toastError), []);
  useEffect(() => {
    load();
    hasBuiltInCheck().then(setCanAdd);
  }, [load]);

  const add = async () => {
    setBusy(true);
    try {
      await addThisDevice();
      toast("מעכשיו אפשר להיכנס מהמכשיר הזה עם טביעת אצבע");
      await load();
    } catch (err) {
      const message = passkeyErrorMessage(err, true);
      if (message) toast(message, "error");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (passkey: Passkey) => {
    if (!window.confirm(`להסיר את הכניסה עם טביעת אצבע מ${passkey.name}?`)) return;
    try {
      await api.deletePasskey(passkey.id);
      if (passkey.credential_id === thisDevicePasskey()) forgetThisDevice();
      setItems((list) => list?.filter((p) => p.id !== passkey.id) ?? null);
      toast("הוסר");
    } catch (err) {
      toastError(err);
    }
  };

  const thisDeviceListed = items?.some((p) => p.credential_id === mine) ?? false;

  return (
    <Modal
      title="כניסה עם טביעת אצבע"
      onClose={onClose}
      footer={
        canAdd && items && !thisDeviceListed ? (
          <button className="btn btn-primary" onClick={add} disabled={busy}>
            <FingerprintIcon />
            {busy ? "מפעיל…" : "הפעלה במכשיר הזה"}
          </button>
        ) : undefined
      }
    >
      <p className="note">
        מהמכשירים האלה אפשר להיכנס עם טביעת אצבע או זיהוי פנים, בלי סיסמה. הסיסמה ממשיכה לעבוד מכל מכשיר.
      </p>
      {items === null ? (
        <p className="empty">טוען…</p>
      ) : items.length === 0 ? (
        <p className="empty">עוד לא הופעלה כניסה עם טביעת אצבע.</p>
      ) : (
        <ul className="passkey-list">
          {items.map((p) => (
            <li key={p.id}>
              <div>
                <strong>
                  {p.name}
                  {p.credential_id === mine && <span className="passkey-mine">המכשיר הזה</span>}
                </strong>
                <span className="note">
                  נוסף ב-{formatDate(p.created_at)}
                  {" · "}
                  {p.last_used_at ? `כניסה אחרונה ${formatDate(p.last_used_at)}` : "עוד לא נכנסו איתו"}
                </span>
              </div>
              <button className="link-btn danger" onClick={() => remove(p)}>
                הסרה
              </button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
