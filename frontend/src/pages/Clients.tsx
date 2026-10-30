import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Client, type ClientInput, type ImportResult } from "../api";
import { WhatsAppIcon } from "../components/icons";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/toast";
import { formatPhone, whatsappNumber } from "../format";

const EMPTY: ClientInput = {
  name: "",
  contact_name: null,
  phone: "",
  email: null,
  invoice_name: null,
  tax_id: null,
  address: null,
  notes: null,
  active: true,
};

const CSV_TEMPLATE = "﻿שם הגן,שם הגננת,טלפון,מייל,שם לחשבונית,ח.פ,כתובת,הערות\nגן לדוגמה,רונית,050-1234567,,,,,\n";

function downloadTemplate() {
  const url = URL.createObjectURL(new Blob([CSV_TEMPLATE], { type: "text/csv;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: "gans-template.csv" });
  a.click();
  URL.revokeObjectURL(url);
}

export function Clients() {
  const [query, setQuery] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [list, setList] = useState<Client[] | null>(null);
  const [editing, setEditing] = useState<Client | "new" | null>(null);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api.clients(query, showInactive).then(setList, toastError);
  }, [query, showInactive]);

  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);

  const importFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      const result = await api.importClients(file);
      setImportResult(result);
      load();
    } catch (err) {
      toastError(err);
    } finally {
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  return (
    <div className="stack-lg">
      <div className="page-head">
        <div>
          <p className="eyebrow">לקוחות</p>
          <h1>גנים</h1>
        </div>
        <div className="head-actions">
          <button className="btn" onClick={() => fileInput.current?.click()}>
            ייבוא מקובץ
          </button>
          <button className="btn btn-primary" onClick={() => setEditing("new")}>
            הוספת גן
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".csv,text/csv"
            hidden
            onChange={(e) => importFile(e.target.files?.[0])}
          />
        </div>
      </div>

      <section className="card">
        <div className="toolbar">
          <input
            className="search"
            type="search"
            placeholder="חיפוש גן, גננת או טלפון"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <label className="check">
            <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
            הצגת גנים לא פעילים
          </label>
        </div>

        {!list ? (
          <p className="empty">טוען…</p>
        ) : list.length === 0 ? (
          <p className="empty">{query ? "אין תוצאות" : "עוד אין גנים. אפשר להוסיף אחד אחד או לייבא מקובץ."}</p>
        ) : (
          <div className="grid clients-grid">
            <div className="grid-row grid-head">
              <span className="c-name">גן</span>
              <span className="c-contact">גננת</span>
              <span className="c-phone">טלפון</span>
              <span className="c-card">כרטיס</span>
            </div>
            {list.map((c) => (
              <button key={c.id} className={c.active ? "grid-row row-btn" : "grid-row row-btn row-inactive"} onClick={() => setEditing(c)}>
                <span className="c-name">
                  <span className="name">{c.name}</span>
                  {!c.active && <span className="sub">לא פעיל</span>}
                </span>
                <span className="c-contact">{c.contact_name ?? "—"}</span>
                <span className="c-phone mono">{formatPhone(c.phone)}</span>
                <span className="c-card">
                  <span className={c.has_card_token ? "badge badge-charged" : "badge badge-pending"}>
                    {c.has_card_token ? "שמור" : "חסר"}
                  </span>
                </span>
              </button>
            ))}
          </div>
        )}
      </section>

      {editing && (
        <ClientModal
          client={editing === "new" ? null : editing}
          onClose={() => {
            setEditing(null);
            load(); // the card may have changed even without saving the form
          }}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}

      {importResult && (
        <Modal
          title="תוצאות הייבוא"
          onClose={() => setImportResult(null)}
          footer={
            <button className="btn btn-primary" onClick={() => setImportResult(null)}>
              סגירה
            </button>
          }
        >
          <p className="lead">
            נוספו {importResult.created} גנים
            {importResult.skipped > 0 && `, ${importResult.skipped} דולגו כי כבר קיימים`}.
          </p>
          {importResult.errors.length > 0 && (
            <ul className="error-list">
              {importResult.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
        </Modal>
      )}

      <p className="footnote">
        ייבוא מקובץ CSV (אפשר לשמור מאקסל כ-CSV).{" "}
        <button className="link-btn" onClick={downloadTemplate}>
          הורדת קובץ לדוגמה
        </button>
      </p>
    </div>
  );
}

function ClientModal({ client, onClose, onSaved }: { client: Client | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<ClientInput>(() => (client ? { ...EMPTY, ...pickInput(client) } : EMPTY));
  const [hasCard, setHasCard] = useState(client?.has_card_token ?? false);
  const [cardUrl, setCardUrl] = useState<string | null>(null);
  const [cardBusy, setCardBusy] = useState(false);
  const [saving, setSaving] = useState(false);

  const set = <K extends keyof ClientInput>(key: K, value: ClientInput[K]) => setForm((f) => ({ ...f, [key]: value }));
  const text = (key: keyof ClientInput) => ({
    value: (form[key] as string | null) ?? "",
    onChange: (e: { target: { value: string } }) => set(key, (e.target.value || null) as never),
  });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (client) await api.updateClient(client.id, form);
      else await api.createClient(form);
      toast(client ? "הגן עודכן" : "הגן נוסף");
      onSaved();
    } catch (err) {
      toastError(err);
    } finally {
      setSaving(false);
    }
  };

  const saveCard = async () => {
    if (!client) return;
    setCardBusy(true);
    try {
      const res = await api.saveCard(client.id);
      setHasCard(res.has_card_token);
      setCardUrl(res.url);
      if (res.has_card_token) toast("הכרטיס נשמר");
    } catch (err) {
      toastError(err);
    } finally {
      setCardBusy(false);
    }
  };

  const copyCardUrl = async () => {
    if (!cardUrl) return;
    try {
      await navigator.clipboard.writeText(cardUrl);
      toast("הקישור הועתק");
    } catch {
      window.prompt("העתיקו את הקישור:", cardUrl);
    }
  };

  const checkCard = async () => {
    if (!client) return;
    try {
      const fresh = await api.client(client.id);
      setHasCard(fresh.has_card_token);
      toast(fresh.has_card_token ? "הכרטיס נשמר" : "עוד לא נשמר כרטיס", fresh.has_card_token ? "ok" : "error");
    } catch (err) {
      toastError(err);
    }
  };

  const removeCard = async () => {
    if (!client || !window.confirm("להסיר את הכרטיס השמור?")) return;
    try {
      await api.removeCard(client.id);
      setHasCard(false);
    } catch (err) {
      toastError(err);
    }
  };

  const remove = async () => {
    if (!client || !window.confirm(`למחוק את ${client.name}?`)) return;
    try {
      await api.deleteClient(client.id);
      toast("הגן נמחק");
      onSaved();
    } catch (err) {
      toastError(err);
    }
  };

  return (
    <Modal
      title={client ? client.name : "גן חדש"}
      onClose={onClose}
      footer={
        <>
          {client && (
            <button type="button" className="link-btn danger" onClick={remove}>
              מחיקה
            </button>
          )}
          <span className="spacer" />
          <button type="button" className="btn" onClick={onClose}>
            ביטול
          </button>
          <button type="submit" form="client-form" className="btn btn-primary" disabled={saving}>
            {saving ? "שומר…" : "שמירה"}
          </button>
        </>
      }
    >
      <form id="client-form" className="form-grid" onSubmit={submit}>
        <label className="field">
          <span>שם הגן *</span>
          <input required {...text("name")} />
        </label>
        <label className="field">
          <span>שם הגננת</span>
          <input {...text("contact_name")} />
        </label>
        <label className={client ? "field" : "field span-2"}>
          <span>טלפון *</span>
          <input required inputMode="tel" dir="ltr" {...text("phone")} />
        </label>
        {client && (
          <>
            <label className="field">
              <span>מייל</span>
              <input type="email" dir="ltr" {...text("email")} />
            </label>
            <label className="field">
              <span>שם לחשבונית</span>
              <input {...text("invoice_name")} placeholder="אם שונה משם הגן" />
            </label>
            <label className="field">
              <span>ח.פ / ע.מ</span>
              <input inputMode="numeric" {...text("tax_id")} />
            </label>
            <label className="field span-2">
              <span>כתובת</span>
              <input {...text("address")} />
            </label>
            <label className="field span-2">
              <span>הערות</span>
              <textarea rows={2} {...text("notes")} />
            </label>
          </>
        )}
        {client && (
          <label className="check span-2">
            <input type="checkbox" checked={form.active} onChange={(e) => set("active", e.target.checked)} />
            גן פעיל (מופיע בחיובים החודשיים)
          </label>
        )}
      </form>

      {client && (
        <div className="card-box-wrap">
          <div className="card-box">
            <div>
              <strong>כרטיס אשראי ב-Grow</strong>
              <p className="sub">
                {hasCard ? "שמור. אפשר לחייב בלי להקליד פרטים." : "לא שמור. אי אפשר לחייב אוטומטית."}
              </p>
            </div>
            {hasCard ? (
              <button type="button" className="btn btn-sm" onClick={removeCard}>
                הסרה
              </button>
            ) : (
              <button type="button" className="btn btn-sm" onClick={saveCard} disabled={cardBusy}>
                {cardBusy ? "יוצר קישור…" : cardUrl ? "קישור חדש" : "שמירת כרטיס"}
              </button>
            )}
          </div>
          {cardUrl && !hasCard && (
            <div className="card-link">
              <p className="sub">
                שלחו לגננת את הקישור. אחרי שהיא תזין כרטיס בדף המאובטח של Grow, הוא יישמר כאן אוטומטית.
              </p>
              <div className="card-link-actions">
                <a
                  className="btn btn-sm btn-whatsapp"
                  href={`https://wa.me/${whatsappNumber(client.phone)}?text=${encodeURIComponent(cardLinkMessage(client, cardUrl))}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <WhatsAppIcon /> שליחה לגננת
                </a>
                <button type="button" className="btn btn-sm" onClick={copyCardUrl}>
                  העתקת קישור
                </button>
                <button type="button" className="link-btn" onClick={checkCard}>
                  בדיקה אם נשמר
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

function cardLinkMessage(c: Client, url: string): string {
  const hello = c.contact_name ? `שלום ${c.contact_name},` : "שלום,";
  return (
    `${hello} כדי שנוכל לחייב את החשבון החודשי של ${c.name} אוטומטית, ` +
    `אפשר לשמור כרטיס אשראי בדף המאובטח של Grow: ${url}\nתודה, פפריקה פירות וירקות`
  );
}

function pickInput(c: Client): ClientInput {
  const { name, contact_name, phone, email, invoice_name, tax_id, address, notes, active } = c;
  return { name, contact_name, phone, email, invoice_name, tax_id, address, notes, active };
}
