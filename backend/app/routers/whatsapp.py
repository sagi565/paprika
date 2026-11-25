"""Linking the business's WhatsApp (wacli) and its status. Sending is in charges.py."""

import segno
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..db import get_db
from ..schemas import WhatsAppLinkIn, WhatsAppStatus
from ..services import whatsapp

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"], dependencies=[Depends(require_auth)])


def _status(db: Session) -> WhatsAppStatus:
    out = WhatsAppStatus(**whatsapp.status(db))
    if out.pairing and out.pairing.qr and not out.pairing.done:
        out.pairing.qr_svg = segno.make(out.pairing.qr, error="l").svg_data_uri(scale=6, border=2, dark="#111")
    return out


@router.get("", response_model=WhatsAppStatus)
def get_status(db: Session = Depends(get_db)):
    return _status(db)


@router.post("/link", response_model=WhatsAppStatus)
async def link(body: WhatsAppLinkIn, db: Session = Depends(get_db)):
    if body.method == "code" and not body.phone:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "צריך את מספר הנייד שהוואטסאפ רשום עליו")
    try:
        await run_in_threadpool(whatsapp.start_pairing, body.method, body.phone)
    except whatsapp.WhatsAppError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return _status(db)


@router.post("/link/cancel", response_model=WhatsAppStatus)
def cancel(db: Session = Depends(get_db)):
    whatsapp.cancel_pairing()
    return _status(db)


@router.post("/logout", response_model=WhatsAppStatus)
def logout(db: Session = Depends(get_db)):
    whatsapp.logout()
    db.expire_all()
    return _status(db)
