"""Grow (grow.business) payment gateway.

Everything Grow-specific lives here. The rest of the app only talks to `GrowGateway`.

- `MockGrowGateway` simulates Grow so the whole site works today.
- `LiveGrowGateway` is the real integration. Its three methods are the only
  missing logic. Fill them in once Grow approves API + token access.

Docs: https://developers.grow.business  (token flows: /reference/work-with-token)
"""

import io
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

from ..config import settings
from ..models import Client


class ChargeFailed(Exception):
    """Grow declined the charge. The message is shown to the user as-is (Hebrew)."""


@dataclass
class CustomerInfo:
    name: str
    phone: str
    email: str | None
    invoice_name: str | None
    tax_id: str | None

    @classmethod
    def of(cls, client: Client) -> "CustomerInfo":
        return cls(
            name=client.name,
            phone=client.phone,
            email=client.email,
            invoice_name=client.invoice_name,
            tax_id=client.tax_id,
        )


@dataclass
class ChargeRequest:
    card_token: str
    amount: Decimal
    description: str
    customer: CustomerInfo


@dataclass
class ChargeResult:
    transaction_id: str
    raw: dict  # stored as JSON on the charge, passed back to fetch_invoice_pdf


@dataclass
class CardSaveStart:
    token: str | None = None  # set when the token is available immediately
    url: str | None = None  # set when the client must fill in a Grow page


class GrowGateway(ABC):
    @abstractmethod
    def charge_with_token(self, req: ChargeRequest) -> ChargeResult:
        """Charge a saved card. Raise ChargeFailed with a Hebrew message on decline."""

    @abstractmethod
    def fetch_invoice_pdf(self, transaction_id: str, raw: dict) -> bytes:
        """Return the PDF bytes of the invoice Grow issued for this transaction."""

    @abstractmethod
    def start_card_save(self, customer: CustomerInfo) -> CardSaveStart:
        """Begin saving a customer's card as a Grow token."""


class LiveGrowGateway(GrowGateway):
    def charge_with_token(self, req: ChargeRequest) -> ChargeResult:
        # TODO(grow): POST createTransactionWithToken with userId, pageCode, the
        # card token, sum and customer details (fullName, phone, invoiceName...).
        # Server-side only. Map a decline to ChargeFailed(<message from Grow>).
        raise NotImplementedError

    def fetch_invoice_pdf(self, transaction_id: str, raw: dict) -> bytes:
        # TODO(grow): ask Grow how to get the invoice document for a transaction
        # (a link in the transaction response / notify callback, or a separate
        # endpoint), then download and return the PDF bytes.
        raise NotImplementedError

    def start_card_save(self, customer: CustomerInfo) -> CardSaveStart:
        # TODO(grow): createPaymentProcess with chargeType=3 and saveCardToken=1,
        # return CardSaveStart(url=<payment page url>). The token itself arrives
        # later through the notify webhook (see routers/grow_webhook.py).
        raise NotImplementedError


class MockGrowGateway(GrowGateway):
    """Pretends to be Grow: every charge with a token succeeds, and a sample
    invoice PDF is produced so the screenshot flow can be tried end to end."""

    def charge_with_token(self, req: ChargeRequest) -> ChargeResult:
        time.sleep(0.6)
        transaction_id = f"MOCK-{uuid.uuid4().hex[:10].upper()}"
        raw = {
            "transaction_id": transaction_id,
            "invoice_number": str(40000 + int(time.time()) % 10000),
            "customer": asdict(req.customer),
            "amount": str(req.amount),
            "description": req.description,
            "date": date.today().strftime("%d/%m/%Y"),
        }
        return ChargeResult(transaction_id=transaction_id, raw=raw)

    def fetch_invoice_pdf(self, transaction_id: str, raw: dict) -> bytes:
        from .mock_invoice import render_mock_invoice

        image = render_mock_invoice(raw)
        buf = io.BytesIO()
        image.save(buf, "PDF", resolution=150)
        return buf.getvalue()

    def start_card_save(self, customer: CustomerInfo) -> CardSaveStart:
        return CardSaveStart(token=f"mock-token-{uuid.uuid4().hex[:12]}")


def get_gateway() -> GrowGateway:
    return MockGrowGateway() if settings.grow_mode == "mock" else LiveGrowGateway()


def dump_raw(raw: dict) -> str:
    return json.dumps(raw, ensure_ascii=False)
