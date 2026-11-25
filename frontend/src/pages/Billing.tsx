import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type Charge, type MonthData } from "../api";
import { Chevron } from "../components/Chevron";
import { AlertIcon, CheckIcon, SearchIcon, WhatsAppIcon } from "../components/icons";
import { Modal } from "../components/Modal";
import { MonthBoard, type StripCell } from "../components/MonthBoard";
import { StatusBadge } from "../components/StatusBadge";
import { toast, toastError } from "../components/toast";
import {
  currentMonth,
  formatMoney,
  formatMoneyWhole,
  formatPhone,
  formatShortDateTime,
  monthLabel,
  shiftMonth,
} from "../format";

type Filter = "all" | "pending" | "failed" | "charged" | "sent";

// The WhatsApp run's filters come first.
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "הכל" },
  { key: "charged", label: "לשליחה" },
  { key: "failed", label: "נכשלו" },
  { key: "pending", label: "ממתינים" },
  { key: "sent", label: "נשלחו" },
];

const MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;

function matchesFilter(row: Charge, filter: Filter): boolean {
  if (filter === "all") return true;
  if (filter === "pending") return row.status === "pending" || row.status === "processing";
  return row.status === filter;
}

function matchesQuery(row: Charge, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const digits = q.replace(/\D/g, "");
  return (
    row.client.name.toLowerCase().includes(q) ||
    (row.client.contact_name ?? "").toLowerCase().includes(q) ||
    (digits !== "" && row.client.phone.includes(digits))
  );
}

const isChargeable = (r: Charge) => (r.status === "pending" || r.status === "failed") && (r.amount ?? 0) > 0;

export function Billing() {
  const [params, setParams] = useSearchParams();
  const paramMonth = params.get("m");
  const month = paramMonth && MONTH_RE.test(paramMonth) ? paramMonth : currentMonth();
  const [data, setData] = useState<MonthData | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [confirming, setConfirming] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api.month(month));
    } catch (err) {
      toastError(err);
    }
  }, [month]);

  useEffect(() => {
    setData(null);
    load();
  }, [load]);

  // Keep refreshing while a bulk charge runs in the background.
  useEffect(() => {
    if (!data?.summary.processing_count) return;
    const t = setTimeout(load, 1500);
    return () => clearTimeout(t);
  }, [data, load]);

  const setMonth = (m: string) => setParams(m === currentMonth() ? {} : { m });

  const rows = useMemo(
    () => (data?.rows ?? []).filter((r) => matchesFilter(r, filter) && matchesQuery(r, query)),
    [data, filter, query],
  );
  const chargeable = useMemo(() => (data?.rows ?? []).filter(isChargeable), [data]);

  const startChargeAll = async () => {
    setConfirming(false);
    try {
      const { started } = await api.chargeAll(month);
      toast(started ? `מחייבים ${started} גנים…` : "אין גנים לחיוב");
      load();
    } catch (err) {
      toastError(err);
    }
  };

  const s = data?.summary;
  const cells: StripCell[] = (data?.rows ?? []).map((r) => ({ key: r.id, status: r.status, name: r.client.name }));

  return (
    <div className="stack">
      <div className="page-head">
        <div className="month-switch">
          {/* RTL: the previous month is on the right, the next on the left. */}
          <button className="icon-btn icon-btn-ring" onClick={() => setMonth(shiftMonth(month, -1))} aria-label="חודש קודם">
            <Chevron direction="right" />
          </button>
          <h1>{monthLabel(month)}</h1>
          <button className="icon-btn icon-btn-ring" onClick={() => setMonth(shiftMonth(month, 1))} aria-label="חודש הבא">
            <Chevron direction="left" />
          </button>
          {month !== currentMonth() && (
            <button className="btn btn-ghost btn-sm" onClick={() => setMonth(currentMonth())}>
              לחודש הנוכחי
            </button>
          )}
        </div>
        <button
          className="btn btn-primary btn-charge"
          disabled={!chargeable.length || !!s?.processing_count}
          onClick={() => setConfirming(true)}
        >
          {s?.processing_count ? (
            <>
              <span className="spinner" aria-hidden /> מחייב…
            </>
          ) : (
            <>
              חיוב כל הגנים <span className="btn-count">{chargeable.length}</span>
            </>
          )}
        </button>
      </div>

      {!s ? (
        <div className="sk sk-board" />
      ) : (
        <MonthBoard
          collected={formatMoneyWhole(s.charged_amount)}
          total={formatMoneyWhole(s.total_amount)}
          figures={[
            { label: "נשלחו", value: `${s.sent_count} מתוך ${s.charged_count}` },
            { label: "נכשלו", value: String(s.failed_count), tone: s.failed_count ? "bad" : undefined },
            { label: "גנים", value: String(s.clients) },
          ]}
          cells={cells}
          empty={
            <>
              עוד אין גנים לחיוב. <Link to="/clients">הוספת גנים</Link>
            </>
          }
        />
      )}

      <section className="panel table-panel">
        <div className="toolbar">
          <label className="search">
            <SearchIcon />
            <input
              type="search"
              placeholder="חיפוש גן, גננת או טלפון"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="חיפוש"
            />
          </label>
          <div className="chips" role="tablist" aria-label="סינון לפי סטטוס">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                role="tab"
                aria-selected={filter === f.key}
                className={filter === f.key ? "chip chip-on" : "chip"}
                onClick={() => setFilter(f.key)}
              >
                {f.key !== "all" && <span className={`dot st-${f.key}`} aria-hidden />}
                {f.label}
                <span className="chip-count">{(data?.rows ?? []).filter((r) => matchesFilter(r, f.key)).length}</span>
              </button>
            ))}
          </div>
        </div>

        {!data ? (
          <RowsSkeleton />
        ) : data.rows.length === 0 ? (
          <div className="empty">
            <p>עוד אין גנים בחודש הזה. כל גן פעיל נכנס לכאן אוטומטית.</p>
            <Link to="/clients" className="btn">
              הוספת גנים
            </Link>
          </div>
        ) : rows.length === 0 ? (
          <div className="empty">
            <p>אין גנים שמתאימים לחיפוש או לסינון.</p>
            <button
              className="btn"
              onClick={() => {
                setQuery("");
                setFilter("all");
              }}
            >
              ניקוי החיפוש
            </button>
          </div>
        ) : (
          <div className="grid billing-grid">
            <div className="grid-row grid-head">
              <span className="c-name">גן</span>
              <span className="c-phone">טלפון</span>
              <span className="c-amount">סכום</span>
              <span className="c-status">סטטוס</span>
              <span className="c-date">תאריך ושעה</span>
              <span className="c-actions">חשבונית</span>
            </div>
            {rows.map((row) => (
              <ChargeRow key={row.id} row={row} onChanged={load} />
            ))}
          </div>
        )}
      </section>

      {confirming && data && (
        <ConfirmChargeAll data={data} chargeable={chargeable} onCancel={() => setConfirming(false)} onConfirm={startChargeAll} />
      )}
    </div>
  );
}

function RowsSkeleton() {
  return (
    <div className="sk-rows" aria-busy="true" aria-label="טוען">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="sk-row">
          <span className="sk sk-line" style={{ width: "22%" }} />
          <span className="sk sk-line" style={{ width: "12%" }} />
          <span className="sk sk-line" style={{ width: "10%" }} />
          <span className="sk sk-line" style={{ width: "14%" }} />
        </div>
      ))}
    </div>
  );
}

/** The moment that matters for the row's current status. */
function rowTime(row: Charge): string | null {
  switch (row.status) {
    case "sent":
      return row.sent_at;
    case "charged":
      return row.charged_at;
    case "failed":
    case "processing":
      return row.updated_at;
    default:
      return null;
  }
}

function ChargeRow({ row, onChanged }: { row: Charge; onChanged: () => void }) {
  const when = rowTime(row);
  return (
    <div className={`grid-row charge-row row-${row.status}`}>
      <div className="c-name">
        <span className="name">{row.client.name}</span>
        {row.client.contact_name && <span className="sub">{row.client.contact_name}</span>}
      </div>
      <span className="c-phone mono">{formatPhone(row.client.phone)}</span>
      <div className="c-amount">
        <AmountCell row={row} onSaved={onChanged} />
      </div>
      <div className="c-status">
        <StatusBadge status={row.status} />
        {row.status === "failed" && row.error && <span className="note note-bad">{row.error}</span>}
        {(row.status === "charged" || row.status === "sent") && row.invoice_error && (
          <span className="note note-warn">{row.invoice_error}</span>
        )}
        {row.status === "pending" && !row.client.has_card_token && (
          <span className="note note-warn">
            <AlertIcon size={14} /> אין כרטיס שמור
          </span>
        )}
      </div>
      <span className="c-date mono">{when ? formatShortDateTime(when) : "—"}</span>
      <div className="c-actions">
        <RowActions row={row} onChanged={onChanged} />
      </div>
    </div>
  );
}

function AmountCell({ row, onSaved }: { row: Charge; onSaved: () => void }) {
  const editable = row.status === "pending" || row.status === "failed";
  const [value, setValue] = useState(row.amount?.toString() ?? "");

  useEffect(() => setValue(row.amount?.toString() ?? ""), [row.amount]);

  if (!editable) return <span className="amount">{row.amount != null ? formatMoney(row.amount) : "—"}</span>;

  const save = async () => {
    const trimmed = value.trim().replace(/[,₪\s]/g, "");
    const next = trimmed === "" ? null : Number(trimmed);
    if (next !== null && (Number.isNaN(next) || next < 0)) {
      toast("סכום לא תקין", "error");
      setValue(row.amount?.toString() ?? "");
      return;
    }
    if (next === row.amount) return;
    try {
      await api.updateAmount(row.id, next);
      onSaved();
    } catch (err) {
      toastError(err);
      setValue(row.amount?.toString() ?? "");
    }
  };

  return (
    <label className="amount-input">
      <span aria-hidden>₪</span>
      <input
        inputMode="decimal"
        placeholder="0"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
        aria-label={`סכום עבור ${row.client.name}`}
      />
    </label>
  );
}

function RowActions({ row, onChanged }: { row: Charge; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
    } catch (err) {
      toastError(err);
    } finally {
      setBusy(false);
      onChanged();
    }
  };

  const chargeOne = () =>
    run(async () => {
      if (row.status === "failed" && row.error?.includes("לא ידוע")) {
        if (!window.confirm("ייתכן שהחיוב הקודם עבר. בדקתם ב-Grow שהגן לא חויב?")) return;
      }
      const result = await api.chargeOne(row.id);
      if (result.status === "charged") toast(`${row.client.name} חויב`);
      else toast(result.error ?? "החיוב נכשל", "error");
    });

  switch (row.status) {
    case "pending":
    case "failed":
      return (
        <button className="btn btn-sm" disabled={busy || !row.amount} onClick={chargeOne}>
          {busy ? "מחייב…" : row.status === "failed" ? "חיוב חוזר" : "חיוב"}
        </button>
      );
    case "processing":
      return null;
    default:
      if (!row.has_invoice) {
        return (
          <button className="btn btn-sm" disabled={busy} onClick={() => run(async () => void (await api.refreshInvoice(row.id)))}>
            הבאת חשבונית
          </button>
        );
      }
      return (
        <div className="invoice-actions">
          <InvoiceThumb row={row} />
          {row.status === "sent" ? <SentLabel /> : <WhatsAppLink id={row.id} />}
        </div>
      );
  }
}

function SentLabel() {
  return (
    <span className="sent-label">
      <CheckIcon /> תמונת החשבונית נשלחה
    </span>
  );
}

function WhatsAppLink({ id }: { id: number }) {
  return (
    <Link className="btn btn-sm btn-whatsapp" to={`/send/${id}`}>
      <WhatsAppIcon /> שליחה בוואטסאפ
    </Link>
  );
}

function InvoiceThumb({ row }: { row: Charge }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="thumb" onClick={() => setOpen(true)} aria-label={`הצגת החשבונית של ${row.client.name}`}>
        <img src={api.invoiceThumbUrl(row.id, row.invoice_key)} alt="" loading="lazy" />
      </button>
      {open && (
        <Modal
          title={`חשבונית · ${row.client.name}`}
          onClose={() => setOpen(false)}
          wide
          footer={row.status === "sent" ? <SentLabel /> : <WhatsAppLink id={row.id} />}
        >
          <img className="lightbox-img" src={api.invoiceUrl(row.id, row.invoice_key)} alt={`חשבונית ${row.client.name}`} />
        </Modal>
      )}
    </>
  );
}

function ConfirmChargeAll({
  data,
  chargeable,
  onCancel,
  onConfirm,
}: {
  data: MonthData;
  chargeable: Charge[];
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const total = chargeable.reduce((sum, r) => sum + (r.amount ?? 0), 0);
  const noAmount = data.rows.filter((r) => r.status === "pending" && !r.amount);
  const noCard = chargeable.filter((r) => !r.client.has_card_token);
  return (
    <Modal
      title="חיוב כל הגנים"
      onClose={onCancel}
      footer={
        <>
          <button className="btn" onClick={onCancel}>
            ביטול
          </button>
          <button className="btn btn-primary" onClick={onConfirm}>
            חיוב {formatMoney(total)}
          </button>
        </>
      }
    >
      <p className="lead">
        {chargeable.length} גנים יחויבו עכשיו לחודש {monthLabel(data.month)}, בסך הכל <strong>{formatMoney(total)}</strong>.
      </p>
      {noAmount.length > 0 && (
        <p className="note note-warn block">
          ל-{noAmount.length} גנים אין סכום, ולכן הם לא יחויבו: {noAmount.map((r) => r.client.name).join(", ")}
        </p>
      )}
      {noCard.length > 0 && (
        <p className="note note-bad block">
          אין כרטיס שמור, והחיוב ייכשל: {noCard.map((r) => r.client.name).join(", ")}
        </p>
      )}
    </Modal>
  );
}
