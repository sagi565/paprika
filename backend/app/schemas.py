import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import Charge

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


def normalize_phone(value: str) -> str:
    """Store Israeli numbers in local form: 0501234567."""
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    if not re.fullmatch(r"0\d{8,9}", digits):
        raise ValueError("מספר טלפון לא תקין")
    return digits


class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    phone: str
    email: str | None = Field(default=None, max_length=200)
    invoice_name: str | None = Field(default=None, max_length=200)
    tax_id: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=300)
    notes: str | None = None
    active: bool = True

    @field_validator("name", "contact_name", "email", "invoice_name", "tax_id", "address", "notes", mode="before")
    @classmethod
    def strip_blank(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: str) -> str:
        return normalize_phone(v)


class ClientOut(ClientIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    has_card_token: bool
    grow_card_transaction_id: str | None = None
    created_at: datetime


class ClientBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    contact_name: str | None
    phone: str
    active: bool
    has_card_token: bool


class ChargeOut(BaseModel):
    id: int
    month: str
    amount: float | None
    status: str
    error: str | None
    invoice_error: str | None
    has_invoice: bool
    invoice_key: str | None  # changes when the invoice image is replaced (cache busting)
    wa_state: str | None  # direct WhatsApp send: queued / sending / failed
    wa_error: str | None
    grow_transaction_id: str | None
    charged_at: datetime | None
    sent_at: datetime | None
    updated_at: datetime
    client: ClientBrief

    @classmethod
    def of(cls, ch: Charge) -> "ChargeOut":
        return cls(
            id=ch.id,
            month=ch.month,
            amount=float(ch.amount) if ch.amount is not None else None,
            status=ch.status,
            error=ch.error,
            invoice_error=ch.invoice_error,
            has_invoice=bool(ch.invoice_image),
            invoice_key=ch.invoice_image,
            wa_state=ch.wa_state,
            wa_error=ch.wa_error,
            grow_transaction_id=ch.grow_transaction_id,
            charged_at=ch.charged_at,
            sent_at=ch.sent_at,
            updated_at=ch.updated_at,
            client=ClientBrief.model_validate(ch.client),
        )


class ChargeDetail(ChargeOut):
    next_unsent_id: int | None = None


class MonthSummary(BaseModel):
    clients: int
    total_amount: float
    pending_count: int
    processing_count: int
    charged_count: int
    charged_amount: float
    failed_count: int
    sent_count: int
    sending_count: int  # queued for / in the middle of a direct WhatsApp send


class MonthOut(BaseModel):
    month: str
    rows: list[ChargeOut]
    summary: MonthSummary


class ChargeUpdate(BaseModel):
    amount: float | None = Field(default=None, ge=0, le=1_000_000)


class SentUpdate(BaseModel):
    sent: bool


class StartedOut(BaseModel):
    started: int


class LoginIn(BaseModel):
    password: str


class MeOut(BaseModel):
    business_name: str
    grow_mode: str


class PasskeyCredentialIn(BaseModel):
    # The browser's PublicKeyCredential as JSON (base64url fields); checked by the webauthn library.
    credential: dict


class PasskeyOut(BaseModel):
    id: int
    credential_id: str  # base64url; lets the browser recognize its own entry ("this device")
    name: str
    created_at: datetime
    last_used_at: datetime | None


class MonthRevenue(BaseModel):
    month: str
    revenue: float
    charged_count: int


class CurrentMonth(BaseModel):
    month: str
    clients: int
    total_amount: float
    charged_amount: float
    charged_count: int
    pending_count: int
    failed_count: int
    to_send_count: int
    previous_revenue: float


class YearRevenue(BaseModel):
    year: int
    revenue: float
    average_month: float


class ClientCounts(BaseModel):
    active: int
    inactive: int
    without_card: int


class TopClient(BaseModel):
    id: int
    name: str
    revenue: float


class DashboardOut(BaseModel):
    months: list[MonthRevenue]
    current: CurrentMonth
    year: YearRevenue
    clients: ClientCounts
    top_clients: list[TopClient]


class ImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[str]


class WhatsAppPairing(BaseModel):
    method: str
    qr: str | None
    qr_svg: str | None = None  # the QR as an SVG image, drawn on the server
    code: str | None
    connected: bool
    error: str | None
    done: bool


class WhatsAppStatus(BaseModel):
    available: bool  # wacli is installed on the server
    linked: bool
    phone: str | None
    linked_at: datetime | None
    pairing: WhatsAppPairing | None


class WhatsAppLinkIn(BaseModel):
    method: str = Field(pattern="^(qr|code)$")
    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        local = normalize_phone(v)
        if not re.fullmatch(r"05\d{8}", local):
            raise ValueError("צריך את מספר הנייד שהוואטסאפ רשום עליו (05X)")
        return local


class CardSaveIn(BaseModel):
    # Grow requires the customer's consent to keep the card for future charges.
    consent: bool = False
    # ...and that the customer accepted the site's terms (/terms) before the payment page.
    terms: bool = False


class CardSaveOut(BaseModel):
    has_card_token: bool
    url: str | None = None
