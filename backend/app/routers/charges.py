from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager, joinedload

from ..auth import require_auth
from ..db import get_db
from ..models import Charge, ChargeStatus, Client, InvoiceImage
from ..schemas import (
    MONTH_PATTERN,
    ChargeDetail,
    ChargeOut,
    ChargeUpdate,
    MonthOut,
    MonthSummary,
    SentUpdate,
    StartedOut,
)
from ..services import billing

router = APIRouter(tags=["charges"], dependencies=[Depends(require_auth)])

Month = Annotated[str, Path(pattern=MONTH_PATTERN)]
DONE = (ChargeStatus.CHARGED, ChargeStatus.SENT)


def _load(db: Session, charge_id: int) -> Charge:
    ch = db.get(Charge, charge_id, options=[joinedload(Charge.client)], populate_existing=True)
    if ch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "החיוב לא נמצא")
    return ch


def _summary(rows: list[ChargeOut]) -> MonthSummary:
    def count(*statuses: str) -> int:
        return sum(1 for r in rows if r.status in statuses)

    return MonthSummary(
        clients=len(rows),
        total_amount=sum(r.amount or 0 for r in rows),
        pending_count=count(ChargeStatus.PENDING),
        processing_count=count(ChargeStatus.PROCESSING),
        charged_count=count(*DONE),
        charged_amount=sum(r.amount or 0 for r in rows if r.status in DONE),
        failed_count=count(ChargeStatus.FAILED),
        sent_count=count(ChargeStatus.SENT),
    )


@router.get("/months/{month}/charges", response_model=MonthOut)
def get_month(month: Month, db: Session = Depends(get_db)):
    billing.ensure_month_rows(db, month)
    rows = db.scalars(
        select(Charge)
        .join(Charge.client)
        .options(contains_eager(Charge.client))
        .where(Charge.month == month)
        .order_by(Client.name)
    ).all()
    out = [ChargeOut.of(r) for r in rows]
    return MonthOut(month=month, rows=out, summary=_summary(out))


@router.post("/months/{month}/charge-all", response_model=StartedOut)
def charge_all(month: Month, background: BackgroundTasks, db: Session = Depends(get_db)):
    ids = billing.claim_month(db, month)
    background.add_task(billing.process_many, ids)
    return StartedOut(started=len(ids))


@router.get("/charges/{charge_id}", response_model=ChargeDetail)
def get_charge(charge_id: int, db: Session = Depends(get_db)):
    ch = _load(db, charge_id)
    # Next row in the same month that is charged but not yet sent, for "send next".
    unsent = db.execute(
        select(Charge.id, Client.name)
        .join(Charge.client)
        .where(Charge.month == ch.month, Charge.status == ChargeStatus.CHARGED, Charge.id != ch.id)
        .order_by(Client.name)
    ).all()
    after = [cid for cid, name in unsent if name > ch.client.name]
    next_id = after[0] if after else (unsent[0][0] if unsent else None)
    return ChargeDetail(**ChargeOut.of(ch).model_dump(), next_unsent_id=next_id)


@router.patch("/charges/{charge_id}", response_model=ChargeOut)
def update_charge(charge_id: int, body: ChargeUpdate, db: Session = Depends(get_db)):
    ch = _load(db, charge_id)
    if ch.status not in ChargeStatus.EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, "אי אפשר לשנות סכום אחרי חיוב")
    ch.amount = Decimal(str(round(body.amount, 2))) if body.amount is not None else None
    db.commit()
    return ChargeOut.of(ch)


@router.post("/charges/{charge_id}/charge", response_model=ChargeOut)
def charge_one(charge_id: int, db: Session = Depends(get_db)):
    ch = _load(db, charge_id)
    if not ch.amount:
        raise HTTPException(status.HTTP_409_CONFLICT, "צריך להזין סכום לפני החיוב")
    if not billing.claim_one(db, charge_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "אי אפשר לחייב את השורה הזו כרגע")
    billing.process_charge(charge_id)
    return ChargeOut.of(_load(db, charge_id))


@router.post("/charges/{charge_id}/invoice/refresh", response_model=ChargeOut)
def refresh_invoice(charge_id: int, db: Session = Depends(get_db)):
    ch = _load(db, charge_id)
    if ch.status not in DONE:
        raise HTTPException(status.HTTP_409_CONFLICT, "אין חשבונית לפני חיוב")
    billing.attach_invoice(db, ch)
    return ChargeOut.of(ch)


def _invoice(db: Session, charge_id: int) -> InvoiceImage:
    img = db.get(InvoiceImage, charge_id)
    if img is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "אין תמונת חשבונית")
    return img


# URLs carry ?v=<key>, so a replaced invoice gets a new URL and caching is safe.
IMAGE_CACHE = {"Cache-Control": "private, max-age=86400"}


@router.get("/charges/{charge_id}/invoice.png")
def invoice_image(charge_id: int, db: Session = Depends(get_db)):
    return Response(_invoice(db, charge_id).image, media_type="image/png", headers=IMAGE_CACHE)


@router.get("/charges/{charge_id}/invoice-thumb.png")
def invoice_thumbnail(charge_id: int, db: Session = Depends(get_db)):
    return Response(_invoice(db, charge_id).thumb, media_type="image/png", headers=IMAGE_CACHE)


@router.post("/charges/{charge_id}/sent", response_model=ChargeOut)
def mark_sent(charge_id: int, body: SentUpdate, db: Session = Depends(get_db)):
    ch = _load(db, charge_id)
    if ch.status not in DONE:
        raise HTTPException(status.HTTP_409_CONFLICT, "אפשר לסמן כנשלח רק אחרי חיוב")
    if body.sent:
        ch.status, ch.sent_at = ChargeStatus.SENT, datetime.now(timezone.utc)
    else:
        ch.status, ch.sent_at = ChargeStatus.CHARGED, None
    db.commit()
    return ChargeOut.of(ch)
