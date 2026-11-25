import { useEffect, useRef, useState } from "react";
import { api, type WhatsAppStatus } from "../api";
import { localPhone, refreshWhatsApp, setWhatsApp, useWhatsApp } from "../whatsapp";
import { CheckIcon, WhatsAppIcon } from "./icons";
import { Modal } from "./Modal";
import { toast, toastError } from "./toast";

const formatDate = (iso: string) => new Date(iso).toLocaleDateString("he-IL");

/** "ABCD1234" -> "ABCD-1234", the way WhatsApp shows it. */
const splitCode = (code: string) => (code.length === 8 ? `${code.slice(0, 4)}-${code.slice(4)}` : code);

/** Link the business's WhatsApp to the site (once), so invoices go out from its number. */
export function WhatsAppModal({ onClose }: { onClose: () => void }) {
  const status = useWhatsApp();
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const wasLinked = useRef<boolean | null>(null);

  const pairing = status?.pairing ?? null;
  const pairingActive = !!pairing && !pairing.done;

  useEffect(() => {
    refreshWhatsApp().catch(toastError);
  }, []);

  // Follow the pairing while the owner approves it on the phone.
  useEffect(() => {
    if (!pairingActive) return;
    const t = setTimeout(() => refreshWhatsApp().catch(() => undefined), 2000);
    return () => clearTimeout(t);
  }, [status, pairingActive]);

  useEffect(() => {
    if (!status) return;
    if (wasLinked.current === false && status.linked) toast("וואטסאפ מחובר. מעכשיו החשבוניות נשלחות ממנו.");
    wasLinked.current = status.linked;
  }, [status]);

  const run = async (action: () => Promise<WhatsAppStatus>) => {
    setBusy(true);
    try {
      setWhatsApp(await action());
    } catch (err) {
      toastError(err);
    } finally {
      setBusy(false);
    }
  };

  const unlink = () => {
    if (!window.confirm("לנתק את הוואטסאפ מהאתר? אחר כך אפשר לחבר שוב בכל רגע.")) return;
    run(api.whatsappLogout);
  };

  let body;
  let footer;
  if (!status) {
    body = <p className="empty">טוען…</p>;
  } else if (status.linked) {
    body = (
      <div className="wa-linked">
        <span className="wa-linked-icon" aria-hidden>
          <CheckIcon size={20} />
        </span>
        <div>
          <strong>מחובר למספר <span className="mono">{localPhone(status.phone)}</span></strong>
          <span className="note">
            {status.linked_at ? `חובר ב-${formatDate(status.linked_at)}. ` : ""}
            החשבוניות נשלחות מהמספר הזה ישר לטלפון של כל גן.
          </span>
        </div>
      </div>
    );
    footer = (
      <button className="link-btn danger" onClick={unlink} disabled={busy}>
        ניתוק
      </button>
    );
  } else if (!status.available) {
    body = <p className="note note-bad block">התוכנה לשליחה בוואטסאפ (wacli) לא מותקנת בשרת.</p>;
  } else if (pairingActive && pairing) {
    body = <PairingSteps pairing={pairing} />;
    footer = (
      <button className="btn" onClick={() => run(api.whatsappCancel)} disabled={busy}>
        ביטול
      </button>
    );
  } else {
    body = (
      <>
        <p className="lead">
          מחברים פעם אחת את הוואטסאפ של העסק, ומאז החשבוניות נשלחות ממנו ישר לגננות, בלי לפתוח את הטלפון.
        </p>
        {pairing?.error && <p className="note note-bad block">{pairing.error}</p>}
        <form
          className="wa-form"
          onSubmit={(e) => {
            e.preventDefault();
            run(() => api.whatsappLink("code", phone));
          }}
        >
          <label className="field">
            <span>מספר הנייד שהוואטסאפ רשום עליו</span>
            <input
              type="tel"
              inputMode="tel"
              dir="ltr"
              placeholder="050-1234567"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
            />
          </label>
          <button className="btn btn-whatsapp" type="submit" disabled={busy || !phone.trim()}>
            <WhatsAppIcon /> קבלת קוד חיבור
          </button>
        </form>
        <p className="note">
          באתר פתוח במחשב?{" "}
          <button className="link-btn" onClick={() => run(() => api.whatsappLink("qr"))} disabled={busy}>
            חיבור בסריקת קוד QR
          </button>
        </p>
      </>
    );
  }

  return (
    <Modal title="וואטסאפ" onClose={onClose} footer={footer}>
      {body}
    </Modal>
  );
}

function PairingSteps({ pairing }: { pairing: NonNullable<WhatsAppStatus["pairing"]> }) {
  if (pairing.connected) {
    return (
      <div className="wa-wait">
        <span className="spinner" aria-hidden /> מתחבר… עוד כמה שניות.
      </div>
    );
  }
  if (pairing.method === "qr") {
    return (
      <div className="wa-pair">
        {pairing.qr_svg ? (
          <img className="wa-qr" src={pairing.qr_svg} alt="קוד QR לחיבור וואטסאפ" />
        ) : (
          <div className="wa-wait">
            <span className="spinner" aria-hidden /> מכין קוד…
          </div>
        )}
        <ol className="wa-steps">
          <li>בטלפון פותחים וואטסאפ ← הגדרות ← מכשירים מקושרים.</li>
          <li>לוחצים „קישור מכשיר" וסורקים את הקוד.</li>
        </ol>
      </div>
    );
  }
  return (
    <div className="wa-pair">
      {pairing.code ? (
        <p className="wa-code mono" dir="ltr">
          {splitCode(pairing.code)}
        </p>
      ) : (
        <div className="wa-wait">
          <span className="spinner" aria-hidden /> מבקש קוד מוואטסאפ…
        </div>
      )}
      <ol className="wa-steps">
        <li>בטלפון פותחים וואטסאפ ← הגדרות ← מכשירים מקושרים ← „קישור מכשיר".</li>
        <li>בוחרים „קישור באמצעות מספר טלפון" (למטה, במקום סריקה).</li>
        <li>מקלידים את הקוד שלמעלה. אם מופיעה התראה מוואטסאפ, אפשר ללחוץ עליה ולהקליד שם.</li>
      </ol>
    </div>
  );
}
