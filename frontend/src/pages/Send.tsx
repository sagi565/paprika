import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type ChargeDetail } from "../api";
import { Brand } from "../components/Brand";
import { CheckIcon, WhatsAppIcon } from "../components/icons";
import { StatusBadge } from "../components/StatusBadge";
import { toast, toastError } from "../components/toast";
import { formatMoney, formatPhone, formatShortDateTime, monthLabel, whatsappNumber } from "../format";

function shareMessage(row: ChargeDetail): string {
  const hello = row.client.contact_name ? `שלום ${row.client.contact_name},` : "שלום,";
  return `${hello} מצורפת החשבונית של פפריקה לחודש ${monthLabel(row.month)}. תודה!`;
}

export function Send() {
  const chargeId = Number(useParams().id);
  const navigate = useNavigate();
  const [row, setRow] = useState<ChargeDetail | null>(null);
  const [file, setFile] = useState<File | null>(null);

  useEffect(() => {
    setRow(null);
    setFile(null);
    api
      .charge(chargeId)
      .then((r) => {
        setRow(r);
        if (!r.has_invoice) return;
        // Load the image up front: share() must run straight from the tap, with no await before it.
        return fetch(api.invoiceUrl(chargeId), { credentials: "same-origin" })
          .then((res) => (res.ok ? res.blob() : Promise.reject(new Error("לא הצלחנו לטעון את החשבונית"))))
          .then((blob) => setFile(new File([blob], `invoice-${r.month}-${r.id}.png`, { type: "image/png" })));
      })
      .catch(toastError);
  }, [chargeId]);

  if (!row) return <div className="boot" />;

  const sent = row.status === "sent";
  const canShareFile = !!file && typeof navigator.canShare === "function" && navigator.canShare({ files: [file] });
  const chatUrl = `https://wa.me/${whatsappNumber(row.client.phone)}?text=${encodeURIComponent(shareMessage(row))}`;
  const backTo = `/billing?m=${row.month}`;

  const markSent = async () => {
    try {
      const updated = await api.markSent(row.id, true);
      setRow({ ...row, ...updated });
      toast("סומן כנשלח");
    } catch (err) {
      toastError(err);
    }
  };

  const confirmMarkSent = () => {
    if (window.confirm("לסמן שהחשבונית נשלחה? אחרי הסימון לא יהיה אפשר לשלוח אותה שוב.")) markSent();
  };

  const share = async () => {
    if (!file) return;
    try {
      await navigator.share({ files: [file], text: shareMessage(row) });
      await markSent();
    } catch (err) {
      if ((err as DOMException).name !== "AbortError") toastError(err);
    }
  };

  return (
    <div className="send">
      <header className="send-top">
        <Link to={backTo} className="link-btn">
          → חזרה לחיובים
        </Link>
        <Brand />
      </header>

      <div className="send-head">
        <p className="eyebrow">{monthLabel(row.month)}</p>
        <h1>{row.client.name}</h1>
        <p className="send-meta">
          {row.client.contact_name && <span>{row.client.contact_name}</span>}
          <span className="mono">{formatPhone(row.client.phone)}</span>
          {row.amount != null && <span>{formatMoney(row.amount)}</span>}
          <StatusBadge status={row.status} />
        </p>
      </div>

      {row.has_invoice ? (
        <a className="invoice-frame" href={api.invoiceUrl(row.id)} target="_blank" rel="noreferrer">
          <img src={api.invoiceUrl(row.id)} alt={`חשבונית ${row.client.name}`} />
        </a>
      ) : (
        <p className="empty card">{row.invoice_error ?? "אין עדיין תמונת חשבונית"}</p>
      )}

      {row.has_invoice && (
        <div className="send-actions">
          {sent ? (
            <div className="sent-banner">
              <CheckIcon size={20} />
              <div>
                <strong>תמונת החשבונית נשלחה</strong>
                {row.sent_at && <span className="sub mono">{formatShortDateTime(row.sent_at)}</span>}
              </div>
            </div>
          ) : canShareFile ? (
            <>
              <button className="btn btn-whatsapp btn-block btn-lg" onClick={share}>
                <WhatsAppIcon size={22} /> שליחה בוואטסאפ
              </button>
              <p className="hint">
                בחלון שנפתח בוחרים וואטסאפ ואז את {row.client.contact_name ?? row.client.name}.
              </p>
            </>
          ) : (
            <>
              <div className="split">
                <a className="btn btn-block" href={api.invoiceUrl(row.id)} download={`invoice-${row.month}-${row.id}.png`}>
                  הורדת התמונה
                </a>
                <a className="btn btn-whatsapp btn-block" href={chatUrl} target="_blank" rel="noreferrer">
                  <WhatsAppIcon /> פתיחת הצ׳אט
                </a>
              </div>
              <p className="hint">מורידים את התמונה, פותחים את הצ׳אט עם הגננת ומצרפים אותה.</p>
            </>
          )}

          <div className="send-foot">
            {!sent ? (
              <button className="link-btn" onClick={confirmMarkSent}>
                כבר שלחתי · סימון כנשלח
              </button>
            ) : (
              <span />
            )}
            {row.next_unsent_id && (
              <button className="btn" onClick={() => navigate(`/send/${row.next_unsent_id}`)}>
                לגן הבא ←
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
