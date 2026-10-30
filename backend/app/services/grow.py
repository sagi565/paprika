"""Grow (grow.business) payment gateway.

Everything Grow-specific lives here. The rest of the app only talks to `GrowGateway`.

- `MockGrowGateway` simulates Grow so the whole site works without credentials.
- `LiveGrowGateway` calls Grow's "light server" API (sandbox or production, by GROW_BASE_URL).

Docs: https://developers.grow.business/reference  (token flows: "Work with Token")
"""

import hashlib
import hmac
import io
import json
import re
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

import httpx

from ..config import settings
from ..models import Client


class ChargeFailed(Exception):
    """Grow declined the request. The message is shown to the user as-is (Hebrew)."""


class InvoiceNotReady(Exception):
    """Grow has not sent the invoice for this transaction yet."""


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
    charge_id: int
    card_token: str
    amount: Decimal
    description: str
    customer: CustomerInfo


@dataclass
class ChargeResult:
    transaction_id: str
    raw: dict  # stored as JSON on the charge, passed back to fetch_invoice


@dataclass
class CardSaveStart:
    token: str | None = None  # set when the token is available immediately (mock)
    url: str | None = None  # Grow page the kindergarten fills in to save its card


class GrowGateway(ABC):
    @abstractmethod
    def charge_with_token(self, req: ChargeRequest) -> ChargeResult:
        """Charge a saved card. Raise ChargeFailed with a Hebrew message on decline."""

    @abstractmethod
    def fetch_invoice(self, transaction_id: str, raw: dict) -> bytes:
        """Return the invoice document (PDF or image bytes). Raise InvoiceNotReady if not issued yet."""

    @abstractmethod
    def start_card_save(self, client_id: int, customer: CustomerInfo) -> CardSaveStart:
        """Begin saving a customer's card as a Grow token."""


# ---------- helpers ----------

_QUOTES = re.compile(r"[\"'`״׳]")  # בע״מ -> בעמ
_UNSAFE = re.compile(r"[^\w\s\-.@]")  # Grow: "do not include special characters in any parameter"


def clean(text: str | None) -> str:
    text = _UNSAFE.sub(" ", _QUOTES.sub("", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def payer_name(customer: CustomerInfo) -> str:
    """Grow requires a full name of at least two words."""
    name = clean(customer.invoice_name or customer.name)
    return name if len(name.split()) >= 2 else f"גן {name}".strip()


def mobile_phone(customer: CustomerInfo) -> str:
    if not re.fullmatch(r"05\d{8}", customer.phone):
        raise ChargeFailed("ל-Grow צריך מספר נייד (05X) של הגן. עדכנו את הטלפון בעמוד הגנים.")
    return customer.phone


def card_signature(client_id: int) -> str:
    """Signs the client id we hand Grow, so a card-saved notification can't be forged."""
    msg = f"card-save:{client_id}".encode()
    return hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).hexdigest()[:32]


def verify_card_signature(client_id: int, signature: str) -> bool:
    return hmac.compare_digest(card_signature(client_id), signature or "")


def webhook_url(path: str) -> str:
    return f"{settings.public_url.rstrip('/')}/api/grow/{path}?key={settings.grow_webhook_key}"


def dump_raw(raw: dict) -> str:
    return json.dumps(raw, ensure_ascii=False)


# ---------- live ----------


class LiveGrowGateway(GrowGateway):
    TIMEOUT = httpx.Timeout(40.0, connect=10.0)

    def _check_config(self) -> None:
        required = {
            "GROW_BASE_URL": settings.grow_base_url,
            "GROW_USER_ID": settings.grow_user_id,
            "GROW_PAGE_CODE": settings.grow_page_code,
            "PUBLIC_URL": settings.public_url,
            "GROW_WEBHOOK_KEY": settings.grow_webhook_key,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ChargeFailed("חסרות הגדרות Grow בשרת: " + ", ".join(missing))

    def _post(self, method: str, fields: dict) -> dict:
        """POST multipart/form-data (as Grow requires) and return `data`, or raise ChargeFailed."""
        self._check_config()
        url = f"{settings.grow_base_url.rstrip('/')}/{method}"
        parts = [(k, (None, str(v))) for k, v in fields.items() if v not in (None, "")]
        res = httpx.post(url, files=parts, timeout=self.TIMEOUT)
        res.raise_for_status()  # 5xx/timeouts propagate: the outcome is unknown, not a decline
        body = res.json()
        if str(body.get("status")) != "1":
            err = body.get("err") if isinstance(body.get("err"), dict) else {}
            message = err.get("message") or "הבקשה נדחתה"
            code = f" (קוד {err['id']})" if err.get("id") else ""
            raise ChargeFailed(f"Grow: {message}{code}")
        return body.get("data") or {}

    def charge_with_token(self, req: ChargeRequest) -> ChargeResult:
        c = req.customer
        data = self._post(
            "createTransactionWithToken",
            {
                "userId": settings.grow_user_id,
                "cardToken": req.card_token,
                "sum": f"{req.amount:.2f}",
                "description": clean(req.description),
                "paymentType": 2,  # regular charge
                "paymentNum": 1,
                "pageField[fullName]": payer_name(c),
                "pageField[phone]": mobile_phone(c),
                "pageField[email]": c.email,
                "pageField[invoiceName]": clean(c.invoice_name or c.name),
                "pageField[invoiceLicenseNumber]": clean(c.tax_id),
                "cField1": req.charge_id,
                # Unique per request. TODO(grow): confirm in sandbox that a 13-digit value is accepted.
                "transactionUniqueIdentifier": int(time.time() * 1000),
                # Grow rejects the request if this group already has a successful payment,
                # so retrying a charge whose outcome was unknown can never charge twice.
                "transactionGroupIdentifier": req.charge_id,
                # Not in the token spec; asked Grow whether invoices for token charges use it.
                "invoiceNotifyUrl": webhook_url("invoice-notify"),
            },
        )
        raw = {k: v for k, v in data.items() if k not in ("cardToken", "processToken")}
        return ChargeResult(transaction_id=str(data.get("transactionId") or ""), raw=raw)

    def fetch_invoice(self, transaction_id: str, raw: dict) -> bytes:
        url = raw.get("invoice_url")
        if not url:
            raise InvoiceNotReady
        if not str(url).startswith("https://"):
            raise ValueError(f"unexpected invoice URL: {url}")
        res = httpx.get(url, follow_redirects=True, timeout=30)
        res.raise_for_status()
        return res.content

    def start_card_save(self, client_id: int, customer: CustomerInfo) -> CardSaveStart:
        public = settings.public_url.rstrip("/")
        data = self._post(
            "createPaymentProcess",
            {
                "userId": settings.grow_user_id,
                "pageCode": settings.grow_page_code,
                "chargeType": 3,  # token only, no charge
                "sum": 1,
                "saveCardToken": 1,
                "description": "שמירת כרטיס לחיוב חודשי",
                "successUrl": f"{public}/card-saved",
                "cancelUrl": f"{public}/card-saved?cancelled=1",
                "pageField[fullName]": payer_name(customer),
                "pageField[phone]": mobile_phone(customer),
                "pageField[email]": customer.email,
                "cField1": client_id,
                "cField2": card_signature(client_id),
                "notifyUrl": webhook_url("notify"),
            },
        )
        if not data.get("url"):
            raise ChargeFailed("Grow לא החזירו קישור לשמירת כרטיס")
        return CardSaveStart(url=data["url"])


# ---------- mock ----------


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

    def fetch_invoice(self, transaction_id: str, raw: dict) -> bytes:
        from .mock_invoice import render_mock_invoice

        image = render_mock_invoice(raw)
        buf = io.BytesIO()
        image.save(buf, "PDF", resolution=150)
        return buf.getvalue()

    def start_card_save(self, client_id: int, customer: CustomerInfo) -> CardSaveStart:
        return CardSaveStart(token=f"mock-token-{uuid.uuid4().hex[:12]}")


def get_gateway() -> GrowGateway:
    return MockGrowGateway() if settings.grow_mode == "mock" else LiveGrowGateway()
