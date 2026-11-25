"""Monthly billing flow: create rows, claim them, charge through Grow, attach the invoice image."""

import json
import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..db import SessionLocal
from ..models import Charge, ChargeStatus, Client, GrowInvoiceNotice
from . import invoices
from .grow import (
    DUPLICATE_UNIQUE_ID,
    MAX_UNIQUE_ID,
    ChargeFailed,
    ChargeRequest,
    ChargeResult,
    CustomerInfo,
    InvoiceNotReady,
    dump_raw,
    get_gateway,
)

log = logging.getLogger(__name__)

DONE = (ChargeStatus.CHARGED, ChargeStatus.SENT)
INVOICE_WAITING = "ממתינים לחשבונית מ-Grow. בודקים שוב לבד כל כמה דקות."
INVOICE_FAILED = "לא הצלחנו להפוך את החשבונית מ-Grow לתמונה. אפשר להעלות אותה ידנית."
# How long the background check keeps asking Grow for a missing invoice.
INVOICE_RETRY_DAYS = 14
NOTICE_MATCH_DAYS = 60

# The row keeps its transactionUniqueIdentifier, so charging again is safe: if the first
# attempt went through, Grow refuses the second and we look the first one up instead.
UNKNOWN_OUTCOME = "החיבור ל-Grow נקטע ולא ידוע אם החיוב עבר. אפשר לחייב שוב: אם הוא כבר עבר, Grow לא יחייבו פעמיים."
NOT_FOUND_AFTER_DUPLICATE = "הניסיון הקודם לא עבר ב-Grow. אפשר לחייב שוב."
HEBREW_MONTHS = [
    "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
    "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר",
]


def month_label(month: str) -> str:
    year, mon = month.split("-")
    return f"{HEBREW_MONTHS[int(mon) - 1]} {year}"


def shift_month(month: str, delta: int) -> str:
    year, mon = map(int, month.split("-"))
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_month_rows(db: Session, month: str) -> None:
    """Every active client gets a (pending, no amount) row for the month."""
    have = set(db.scalars(select(Charge.client_id).where(Charge.month == month)))
    stmt = select(Client.id).where(Client.active.is_(True))
    if have:
        stmt = stmt.where(Client.id.not_in(have))
    missing = list(db.scalars(stmt))
    for client_id in missing:
        db.add(Charge(client_id=client_id, month=month, status=ChargeStatus.PENDING))
    if missing:
        try:
            db.commit()
        except IntegrityError:  # a concurrent request created them first
            db.rollback()


def _claim(db: Session, *conditions) -> list[int]:
    """Atomically move chargeable rows to PROCESSING so nothing is charged twice."""
    stmt = (
        update(Charge)
        .where(Charge.status.in_(ChargeStatus.CHARGEABLE), Charge.amount > 0, *conditions)
        .values(status=ChargeStatus.PROCESSING, error=None, updated_at=_now())
        .returning(Charge.id)
        .execution_options(synchronize_session=False)
    )
    ids = list(db.scalars(stmt))
    db.commit()
    return ids


def claim_one(db: Session, charge_id: int) -> bool:
    return bool(_claim(db, Charge.id == charge_id))


def claim_month(db: Session, month: str) -> list[int]:
    return _claim(db, Charge.month == month)


def process_many(charge_ids: list[int]) -> None:
    for charge_id in charge_ids:
        process_charge(charge_id)


def process_charge(charge_id: int) -> None:
    """Charge one claimed row. Uses its own session (runs in background tasks)."""
    with SessionLocal() as db:
        ch = db.get(Charge, charge_id, options=[joinedload(Charge.client)])
        if ch is None or ch.status != ChargeStatus.PROCESSING:
            return
        gateway = get_gateway()
        card_token = ch.client.grow_card_token
        if not card_token:
            ch.status, ch.error = ChargeStatus.FAILED, "אין כרטיס שמור לגן הזה"
            db.commit()
            return
        if ch.grow_unique_id is None:
            # Saved before calling Grow, so a crash mid-request leaves it for the retry.
            _assign_unique_id(db, ch)
        try:
            result = gateway.charge_with_token(
                ChargeRequest(
                    charge_id=ch.id,
                    unique_id=ch.grow_unique_id,
                    card_token=card_token,
                    amount=ch.amount,
                    description=f"פירות וירקות, {month_label(ch.month)}",
                    customer=CustomerInfo.of(ch.client),
                )
            )
        except ChargeFailed as exc:
            if exc.code == DUPLICATE_UNIQUE_ID:
                _resolve_duplicate(db, ch, card_token)
                return
            # A clear decline: the next attempt is a new request with a new identifier.
            ch.status, ch.error, ch.grow_unique_id = ChargeStatus.FAILED, str(exc), None
            db.commit()
            return
        except Exception:
            log.exception("Grow charge failed unexpectedly (charge %s)", charge_id)
            ch.status, ch.error = ChargeStatus.FAILED, UNKNOWN_OUTCOME
            db.commit()
            return

        _mark_charged(db, ch, result)


def _assign_unique_id(db: Session, ch: Charge) -> None:
    """A transactionUniqueIdentifier never used before, even by a row that later cleared it
    (Grow refuses any value it has seen, whatever happened to that request)."""
    value = db.scalar(text("SELECT nextval('grow_unique_id_seq')"))
    if value > MAX_UNIQUE_ID:
        raise RuntimeError("Grow unique identifiers ran past 32 bits")
    ch.grow_unique_id = value
    db.commit()


def _resolve_duplicate(db: Session, ch: Charge, card_token: str) -> None:
    """Grow already saw this row's identifier: an earlier attempt reached it. Ask Grow how it ended."""
    try:
        found = get_gateway().find_token_charge(card_token, ch.grow_unique_id)
    except Exception:
        log.exception("Looking up an earlier Grow attempt failed (charge %s)", ch.id)
        ch.status, ch.error = ChargeStatus.FAILED, UNKNOWN_OUTCOME
        db.commit()
        return
    if found is None:
        log.info("Earlier Grow attempt for charge %s did not complete", ch.id)
        ch.status, ch.error, ch.grow_unique_id = ChargeStatus.FAILED, NOT_FOUND_AFTER_DUPLICATE, None
        db.commit()
        return
    log.info("Charge %s was already charged in Grow (transaction %s)", ch.id, found.transaction_id)
    _mark_charged(db, ch, found)


def _mark_charged(db: Session, ch: Charge, result: ChargeResult) -> None:
    ch.status, ch.error = ChargeStatus.CHARGED, None
    ch.grow_transaction_id = result.transaction_id
    ch.grow_payload = dump_raw(result.raw)
    ch.charged_at = _now()
    db.commit()
    attach_invoice(db, ch)


# ---------- invoices ----------


def _refs(values) -> set[str]:
    return {str(v).strip() for v in values if v not in (None, "") and str(v).strip()}


def charge_refs(ch: Charge, raw: dict) -> set[str]:
    """Identifiers Grow may use for this charge in an invoice notification."""
    return _refs(
        [ch.grow_transaction_id, raw.get("transactionId"), raw.get("transactionCode"), raw.get("asmachta")]
    )


def notice_refs(item: dict) -> set[str]:
    return _refs([item.get("transactionId"), item.get("transactionCode"), item.get("asmachta")])


def match_charge(db: Session, refs: set[str]) -> Charge | None:
    """The charge an invoice notification belongs to."""
    if not refs:
        return None
    ch = db.scalar(select(Charge).where(Charge.grow_transaction_id.in_(refs)))
    if ch is not None:
        return ch
    recent = db.scalars(
        select(Charge).where(
            Charge.status.in_(DONE), Charge.charged_at > _now() - timedelta(days=NOTICE_MATCH_DAYS)
        )
    )
    for candidate in recent:
        if charge_refs(candidate, json.loads(candidate.grow_payload or "{}")) & refs:
            return candidate
    return None


def _apply_notice(db: Session, ch: Charge, raw: dict) -> None:
    """An invoice notification that came before the charge was saved (Grow can be that fast)."""
    refs = charge_refs(ch, raw)
    notices = db.scalars(
        select(GrowInvoiceNotice)
        .where(
            or_(GrowInvoiceNotice.charge_id == ch.id, GrowInvoiceNotice.charge_id.is_(None)),
            GrowInvoiceNotice.received_at > _now() - timedelta(days=NOTICE_MATCH_DAYS),
        )
        .order_by(GrowInvoiceNotice.id.desc())
    )
    for notice in notices:
        if notice.charge_id == ch.id or refs & set(notice.refs.split()):
            notice.charge_id = ch.id
            raw["invoice_url"] = notice.invoice_url
            if notice.invoice_number:
                raw["invoice_number"] = notice.invoice_number
            return


def attach_invoice(db: Session, ch: Charge) -> None:
    """Get the invoice from Grow and store it as a PNG. Never fails the charge."""
    ch.invoice_checked_at = _now()
    try:
        raw = json.loads(ch.grow_payload or "{}")
        _apply_notice(db, ch, raw)
        source = get_gateway().find_invoice(ch.grow_transaction_id or "", raw)
        ch.grow_payload = dump_raw(raw)  # keeps the invoice link Grow gave us
        invoices.store_invoice(db, ch, invoices.source_to_png(source))
        ch.invoice_error = None
    except InvoiceNotReady:
        ch.grow_payload = dump_raw(raw)
        ch.invoice_error = INVOICE_WAITING
    except Exception:
        log.exception("Fetching invoice failed (charge %s)", ch.id)
        db.rollback()
        ch.invoice_checked_at = _now()
        # A parallel attempt (Grow's notification) may have stored it meanwhile.
        ch.invoice_error = None if ch.invoice_image else INVOICE_FAILED
    db.commit()


def attach_invoice_by_id(charge_id: int) -> None:
    """For background tasks (e.g. Grow's invoice notification)."""
    with SessionLocal() as db:
        ch = db.get(Charge, charge_id)
        if ch is not None and not ch.invoice_image:
            attach_invoice(db, ch)


def retry_missing_invoices() -> None:
    """Ask Grow again for invoices that haven't come: every few minutes in the first hour
    after the charge, then every half hour, for two weeks."""
    now = _now()
    with SessionLocal() as db:
        rows = db.scalars(
            select(Charge).where(
                Charge.status.in_(DONE),
                Charge.invoice_image.is_(None),
                Charge.charged_at > now - timedelta(days=INVOICE_RETRY_DAYS),
            )
        ).all()
        for ch in rows:
            gap = timedelta(minutes=3) if now - ch.charged_at < timedelta(hours=1) else timedelta(minutes=30)
            if ch.invoice_checked_at is None or now - ch.invoice_checked_at >= gap:
                attach_invoice(db, ch)


def start_invoice_watcher(interval: float = 60) -> threading.Event:
    """Background thread for retry_missing_invoices. Set the returned event to stop it."""
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(interval):
            try:
                retry_missing_invoices()
            except Exception:
                log.exception("Invoice retry round failed")

    threading.Thread(target=loop, name="invoice-watcher", daemon=True).start()
    return stop


def recover_interrupted(db: Session) -> None:
    """Rows left PROCESSING by a crash/restart: we can't know if Grow charged them."""
    db.execute(
        update(Charge)
        .where(Charge.status == ChargeStatus.PROCESSING)
        .values(status=ChargeStatus.FAILED, error=UNKNOWN_OUTCOME)
    )
    db.commit()
