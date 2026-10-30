import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Client, type ClientInput, type ImportResult } from "../api";
import { CheckIcon } from "../components/icons";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/toast";
import { formatPhone } from "../format";

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

/**
 * Creates Grow's card page and shows it in `tab` (opened by the caller during the click).
 * The card number and ID are typed only on Grow's page; they never pass through this site.
 */
async function startCardFill(c: Client, tab: Window | null): Promise<string | null> {
  const res = await api.saveCard(c.id);
  if (res.has_card_token || !res.url) {
    tab?.close(); // demo mode saves a token without a page
    toast(`הכרטיס של ${c.name} נשמר`);
    return null;
  }
  if (tab) {
    tab.opener = null;
    tab.location.href = res.url;
  } else {
    window.location.href = res.url; // popup blocked: continue in this tab
  }
  return res.url;
}

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
  const [onlyNoCard, setOnlyNoCard] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const noCardCount = list?.filter((c) => !c.has_card_token).length ?? 0;
  const shown = (list ?? []).filter((c) => !onlyNoCard || !c.has_card_token);

  const load = useCallback(() => {
    api.clients(query, showInactive).then(setList, toastError);
  }, [query, showInactive]);

  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);

  // Kindergartens whose Grow card page is open: refresh until the token arrives.
  const [waiting, setWaiting] = useState<Set<number>>(new Set());
  useEffect(() => {
    if (!waiting.size) return;
    const t = setInterval(load, 4000);
    const stop = setTimeout(() => setWaiting(new Set()), 15 * 60 * 1000);
    return () => {
      clearInterval(t);
      clearTimeout(stop);
    };
  }, [waiting.size, load]);
  useEffect(() => {
    if (!list || !waiting.size) return;
    const saved = list.filter((c) => waiting.has(c.id) && c.has_card_token);
    if (!saved.length) return;
    saved.forEach((c) => toast(`הכרטיס של ${c.name} נשמר`));
    setWaiting((w) => new Set([...w].filter((id) => !saved.some((c) => c.id === id))));
  }, [list, waiting]);

  const fillCard = async (c: Client) => {
    // Open the tab right away (inside the click) so the browser doesn't block it.
    const tab = window.open("", "_blank");
    try {
      const url = await startCardFill(c, tab);
      if (url) setWaiting((w) => new Set(w).add(c.id));
      else load();
    } catch (err) {
      tab?.close();
      toastError(err);
    }
  };

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
          <div className="chips">
            <button className={onlyNoCard ? "chip" : "chip chip-on"} onClick={() => setOnlyNoCard(false)}>
              כל הגנים <span className="chip-count">{list?.length ?? 0}</span>
            </button>
            <button className={onlyNoCard ? "chip chip-on" : "chip"} onClick={() => setOnlyNoCard(true)}>
              בלי כרטיס <span className="chip-count">{noCardCount}</span>
            </button>
          </div>
          <label className="check">
            <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
            הצגת גנים לא פעילים
          </label>
        </div>

        {!list ? (
          <p className="empty">טוען…</p>
        ) : shown.length === 0 ? (
          <p className="empty">
            {onlyNoCard ? "לכל הגנים יש כרטיס שמור" : query ? "אין תוצאות" : "עוד אין גנים. אפשר להוסיף אחד אחד או לייבא מקובץ."}
          </p>
        ) : (
          <div className="grid clients-grid">
            <div className="grid-row grid-head">
              <span className="c-name">גן</span>
              <span className="c-contact">גננת</span>
              <span className="c-phone">טלפון</span>
              <span className="c-card">כרטיס אשראי</span>
            </div>
            {shown.map((c) => (
              <div
                key={c.id}
                role="button"
                tabIndex={0}
                className={c.active ? "grid-row row-btn" : "grid-row row-btn row-inactive"}
                onClick={() => setEditing(c)}
                onKeyDown={(e) => e.key === "Enter" && e.target === e.currentTarget && setEditing(c)}
              >
                <span className="c-name">
                  <span className="name">{c.name}</span>
                  {!c.active && <span className="sub">לא פעיל</span>}
                </span>
                <span className="c-contact">{c.contact_name ?? "—"}</span>
                <span className="c-phone mono">{formatPhone(c.phone)}</span>
                <span className="c-card">
                  {c.has_card_token ? (
                    <span className="badge badge-sent">
                      <CheckIcon size={14} /> שמור
                    </span>
                  ) : waiting.has(c.id) ? (
                    <span className="badge badge-processing">
                      <span className="spinner" aria-hidden /> ממתין למילוי
                    </span>
                  ) : (
                    <button
                      className="btn btn-sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        fillCard(c);
                      }}
                    >
                      מילוי כרטיס
                    </button>
                  )}
                </span>
              </div>
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

  const fillCard = async () => {
    if (!client) return;
    const tab = window.open("", "_blank"); // inside the click, so it isn't blocked
    setCardBusy(true);
    try {
      const url = await startCardFill(client, tab);
      if (url) setCardUrl(url);
      else setHasCard(true);
    } catch (err) {
      tab?.close();
      toastError(err);
    } finally {
      setCardBusy(false);
    }
  };

  // While Grow's page is open in another tab, notice when the card arrives.
  useEffect(() => {
    if (!client || !cardUrl || hasCard) return;
    const t = setInterval(async () => {
      const fresh = await api.client(client.id).catch(() => null);
      if (fresh?.has_card_token) {
        setHasCard(true);
        toast(`הכרטיס של ${client.name} נשמר`);
      }
    }, 4000);
    return () => clearInterval(t);
  }, [client, cardUrl, hasCard]);

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
              <button type="button" className="btn btn-sm btn-primary" onClick={fillCard} disabled={cardBusy}>
                {cardBusy ? "פותח את Grow…" : cardUrl ? "פתיחה מחדש" : "מילוי כרטיס"}
              </button>
            )}
          </div>
          {cardUrl && !hasCard && (
            <div className="card-link">
              <p className="sub">
                <span className="spinner" aria-hidden /> הדף המאובטח של Grow נפתח בלשונית חדשה. ממלאים שם את מספר
                הכרטיס, התוקף ות.ז של בעל הכרטיס. כשהכרטיס יישמר, הסטטוס כאן יתעדכן לבד.
              </p>
              <div className="card-link-actions">
                <button type="button" className="link-btn" onClick={checkCard}>
                  בדיקה אם נשמר
                </button>
              </div>
            </div>
          )}
          <p className="footnote">
            מספר הכרטיס ות.ז מוקלדים רק בדף של Grow, ולא עוברים דרך האתר הזה ולא נשמרים בו.
          </p>
        </div>
      )}
    </Modal>
  );
}

function pickInput(c: Client): ClientInput {
  const { name, contact_name, phone, email, invoice_name, tax_id, address, notes, active } = c;
  return { name, contact_name, phone, email, invoice_name, tax_id, address, notes, active };
}
