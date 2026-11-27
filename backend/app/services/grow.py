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

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


DUPLICATE_UNIQUE_ID = 1010  # Grow: this transactionUniqueIdentifier was already used


# Grow error 1013: transactionUniqueIdentifier must be a positive integer that fits in 32 bits.
# Values come from the grow_unique_id_seq sequence (see db.py): never repeated, and moved
# forward to the current Unix time on every startup, so a database reset can't reuse one.
MAX_UNIQUE_ID = 4_294_967_295


class InvoiceNotReady(Exception):
    """Grow has not sent the invoice for this transaction yet."""


@dataclass
class InvoiceSource:
    """Where the invoice is: Grow's link (a PDF, an image or a web page), or the document itself."""

    url: str | None = None
    data: bytes | None = None


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
    unique_id: int  # transactionUniqueIdentifier; Grow refuses a second request with the same value
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
    def find_token_charge(self, card_token: str, unique_id: int) -> ChargeResult | None:
        """The completed transaction sent with this unique id, or None if Grow has none."""

    @abstractmethod
    def find_invoice(self, transaction_id: str, raw: dict) -> InvoiceSource:
        """Where the invoice is. May add what it learns (e.g. invoice_url) to `raw`, which the
        caller saves. Raise InvoiceNotReady if Grow has not issued it yet."""

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


_INVOICE_KEYS = ("invoice_url", "invoiceUrl", "invoiceLink", "invoice_link", "documentUrl", "document_url")
_INVOICE_KEY_HINT = re.compile(r"invoice|document|receipt|kabala|heshbonit", re.I)


def find_invoice_url(node) -> str | None:
    """The invoice link anywhere in a Grow response or notification: a known field name first,
    then any https value whose key mentions an invoice/document."""
    found = []
    for item in _dicts(node):
        for key in _INVOICE_KEYS:
            value = item.get(key)
            if isinstance(value, str) and value.startswith("https://"):
                return value
        for key, value in item.items():
            if isinstance(value, str) and value.startswith("https://") and _INVOICE_KEY_HINT.search(str(key)):
                found.append(value)
    return found[0] if found else None


def _dicts(node):
    """Every dict in a JSON value, outermost first."""
    if isinstance(node, dict):
        yield node
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return
    for child in children:
        yield from _dicts(child)


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
            code = int(err["id"]) if str(err.get("id", "")).isdigit() else None
            suffix = f" (קוד {code})" if code else ""
            raise ChargeFailed(f"Grow: {message}{suffix}", code)
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
                # Grow rejects any second request with the same value (error 1010), whatever
                # happened to the first. A retry after an unknown outcome reuses it on purpose.
                # Grow: send exactly one of transactionUniqueIdentifier/transactionGroupIdentifier.
                "transactionUniqueIdentifier": req.unique_id,
                # Not in the token spec; asked Grow whether invoices for token charges use it.
                "invoiceNotifyUrl": webhook_url("invoice-notify"),
            },
        )
        raw = {k: v for k, v in data.items() if k not in ("cardToken", "processToken")}
        return ChargeResult(transaction_id=str(data.get("transactionId") or ""), raw=raw)

    def find_token_charge(self, card_token: str, unique_id: int) -> ChargeResult | None:
        # Send only one of the two identifiers: Grow returns an error if both are sent.
        data = self._post(
            "getTokenTransactionsByExternalIdentifiers",
            {
                "userId": settings.grow_user_id,
                "cardToken": card_token,
                "transactionUniqueIdentifier": unique_id,
            },
        )
        # Like getPaymentProcessInfo; an incomplete transaction has only received_time/complete_time.
        for item in _dicts(data):
            transaction_id = item.get("transactionId")
            if transaction_id:
                raw = {k: v for k, v in item.items() if k not in ("cardToken", "processToken")}
                return ChargeResult(transaction_id=str(transaction_id), raw=raw)
        return None

    def find_invoice(self, transaction_id: str, raw: dict) -> InvoiceSource:
        # A token charge's invoice link comes only in Grow's "invoice created" notification,
        # stored in raw by the webhook. There is nothing to ask Grow for: getTransactionInfo
        # has no invoice field in Grow's docs, and it answers token charges with error 716.
        url = find_invoice_url(raw)
        if not url:
            raise InvoiceNotReady
        raw["invoice_url"] = url
        return InvoiceSource(url=url)

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

    def find_token_charge(self, card_token: str, unique_id: int) -> ChargeResult | None:
        return None  # mock charges never fail halfway, so there is never anything to find

    def find_invoice(self, transaction_id: str, raw: dict) -> InvoiceSource:
        from .mock_invoice import render_mock_invoice

        image = render_mock_invoice(raw)
        buf = io.BytesIO()
        image.save(buf, "PDF", resolution=150)
        return InvoiceSource(data=buf.getvalue())

    def start_card_save(self, client_id: int, customer: CustomerInfo) -> CardSaveStart:
        return CardSaveStart(token=f"mock-token-{uuid.uuid4().hex[:12]}")


def get_gateway() -> GrowGateway:
    return MockGrowGateway() if settings.grow_mode == "mock" else LiveGrowGateway()
