"""Monthly billing flow: create rows, claim them, charge through Grow, attach the invoice image."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..db import SessionLocal
from ..models import Charge, ChargeStatus, Client
from . import invoices
from .grow import ChargeFailed, ChargeRequest, CustomerInfo, InvoiceNotReady, dump_raw, get_gateway

log = logging.getLogger(__name__)

UNKNOWN_OUTCOME = "לא ידוע אם החיוב בוצע. בדקו ב-Grow לפני שמחייבים שוב."
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
        try:
            if not ch.client.grow_card_token:
                raise ChargeFailed("אין כרטיס שמור לגן הזה")
            result = gateway.charge_with_token(
                ChargeRequest(
                    charge_id=ch.id,
                    card_token=ch.client.grow_card_token,
                    amount=ch.amount,
                    description=f"פירות וירקות, {month_label(ch.month)}",
                    customer=CustomerInfo.of(ch.client),
                )
            )
        except ChargeFailed as exc:
            ch.status, ch.error = ChargeStatus.FAILED, str(exc)
            db.commit()
            return
        except Exception:
            log.exception("Grow charge failed unexpectedly (charge %s)", charge_id)
            ch.status, ch.error = ChargeStatus.FAILED, UNKNOWN_OUTCOME
            db.commit()
            return

        ch.status = ChargeStatus.CHARGED
        ch.grow_transaction_id = result.transaction_id
        ch.grow_payload = dump_raw(result.raw)
        ch.charged_at = _now()
        db.commit()
        attach_invoice(db, ch)


def attach_invoice(db: Session, ch: Charge) -> None:
    """Fetch the invoice from Grow and store it as a PNG. Never fails the charge."""
    try:
        raw = json.loads(ch.grow_payload or "{}")
        document = get_gateway().fetch_invoice(ch.grow_transaction_id or "", raw)
        invoices.store_invoice(db, ch, invoices.document_to_png(document))
        ch.invoice_error = None
    except InvoiceNotReady:
        ch.invoice_error = "ממתינים לחשבונית מ-Grow"
    except Exception:
        log.exception("Fetching invoice failed (charge %s)", ch.id)
        db.rollback()
        ch.invoice_error = "לא הצלחנו להביא את החשבונית מ-Grow"
    db.commit()


def attach_invoice_by_id(charge_id: int) -> None:
    """For background tasks (e.g. Grow's invoice notification)."""
    with SessionLocal() as db:
        ch = db.get(Charge, charge_id)
        if ch is not None:
            attach_invoice(db, ch)


def recover_interrupted(db: Session) -> None:
    """Rows left PROCESSING by a crash/restart: we can't know if Grow charged them."""
    db.execute(
        update(Charge)
        .where(Charge.status == ChargeStatus.PROCESSING)
        .values(status=ChargeStatus.FAILED, error=UNKNOWN_OUTCOME)
    )
    db.commit()
