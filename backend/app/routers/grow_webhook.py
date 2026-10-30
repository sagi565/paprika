"""Grow's server-to-server notifications. Not behind login: Grow calls them.

Each URL carries ?key=<GROW_WEBHOOK_KEY>; we only ever give these URLs to Grow.
Grow posts form fields like data[cardToken] / data[customFields][cField1] (the docs
show them as JSON, so JSON bodies are accepted too).
"""

import hmac
import json
import logging
import re
from collections.abc import Iterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Charge, Client
from ..services import billing
from ..services.grow import dump_raw, verify_card_signature

log = logging.getLogger(__name__)
router = APIRouter(prefix="/grow", tags=["grow"])

OK = {"ok": True}
SECRET_FIELDS = {"cardToken", "transactionToken", "processToken"}


def _check_key(key: str) -> None:
    if not settings.grow_webhook_key or not hmac.compare_digest(key, settings.grow_webhook_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")


def _nest(items: list[tuple[str, str]]) -> dict:
    """data[customFields][cField1]=x  ->  {"data": {"customFields": {"cField1": "x"}}}"""
    result: dict = {}
    for key, value in items:
        parts = re.findall(r"[^\[\]]+", key)
        node = result
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = node[part] = {}
            node = child
        if parts:
            node[parts[-1]] = value
    return result


async def _read_payload(request: Request) -> dict | list:
    if "json" in request.headers.get("content-type", ""):
        return await request.json()
    form = await request.form()
    payload = _nest([(k, v) for k, v in form.multi_items() if isinstance(v, str)])
    if isinstance(payload.get("data"), str):  # data sent as a JSON string
        try:
            payload["data"] = json.loads(payload["data"])
        except ValueError:
            pass
    return payload


def _find(node, key: str):
    """First value for `key`, searching this level before nested ones."""
    if isinstance(node, dict):
        if key in node:
            return node[key]
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        found = _find(child, key)
        if found is not None:
            return found
    return None


def _redact(node):
    if isinstance(node, dict):
        return {k: ("***" if k in SECRET_FIELDS else _redact(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [_redact(v) for v in node]
    return node


@router.post("/notify")
async def grow_notify(request: Request, key: str = "", db: Session = Depends(get_db)):
    """After a kindergarten fills in the card-save page: store the card token on the client."""
    _check_key(key)
    payload = await _read_payload(request)
    log.info("Grow notify: %s", _redact(payload))

    if str(_find(payload, "status")) != "1":
        return OK
    token = _find(payload, "cardToken")
    client_id = str(_find(payload, "cField1") or "")
    signature = str(_find(payload, "cField2") or "")
    if not (token and client_id.isdigit() and verify_card_signature(int(client_id), signature)):
        log.warning("Grow notify ignored: no token or bad client signature")
        return OK

    client = db.get(Client, int(client_id))
    if client is not None:
        client.grow_card_token = str(token)
        db.commit()
        log.info("Saved Grow card token for client %s", client_id)
    return OK


def _invoice_items(node) -> Iterator[dict]:
    if isinstance(node, dict):
        if "invoiceUrl" in node:
            yield node
            return
        node = list(node.values())
    if isinstance(node, list):
        for child in node:
            yield from _invoice_items(child)


@router.post("/invoice-notify")
async def grow_invoice_notify(
    request: Request, background: BackgroundTasks, key: str = "", db: Session = Depends(get_db)
):
    """Grow issued an invoice: remember its link and turn it into the invoice image.

    Serves both the API's invoiceNotifyUrl ({transactionId, invoiceUrl, ...}) and the
    dashboard's "invoice created" webhook ({transactionCode, invoiceNumber, invoiceUrl}).
    """
    _check_key(key)
    payload = await _read_payload(request)
    log.info("Grow invoice notify: %s", _redact(payload))

    for item in _invoice_items(payload):
        transaction_id = str(item.get("transactionId") or item.get("transactionCode") or "")
        if not transaction_id:
            continue
        ch = db.scalar(select(Charge).where(Charge.grow_transaction_id == transaction_id))
        if ch is None:
            log.warning("Invoice for unknown transaction %s", transaction_id)
            continue
        raw = json.loads(ch.grow_payload or "{}")
        raw.update(invoice_url=item.get("invoiceUrl"), invoice_number=item.get("invoiceNumber"))
        ch.grow_payload = dump_raw(raw)
        db.commit()
        background.add_task(billing.attach_invoice_by_id, ch.id)
    return OK
