from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, LargeBinary, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class ChargeStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    CHARGED = "charged"
    FAILED = "failed"
    SENT = "sent"

    CHARGEABLE = (PENDING, FAILED)
    EDITABLE = (PENDING, FAILED)


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(200))
    invoice_name: Mapped[str | None] = mapped_column(String(200))
    tax_id: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)
    # Grow card token. Never sent to the browser.
    grow_card_token: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    charges: Mapped[list["Charge"]] = relationship(back_populates="client")

    @property
    def has_card_token(self) -> bool:
        return bool(self.grow_card_token)


class Charge(Base):
    """One client's bill for one month."""

    __tablename__ = "charges"
    __table_args__ = (UniqueConstraint("client_id", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"), index=True)
    month: Mapped[str] = mapped_column(String(7), index=True)  # YYYY-MM
    amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default=ChargeStatus.PENDING, index=True)
    error: Mapped[str | None] = mapped_column(Text)
    grow_transaction_id: Mapped[str | None] = mapped_column(String(100))
    grow_payload: Mapped[str | None] = mapped_column(Text)  # raw JSON from Grow
    invoice_image: Mapped[str | None] = mapped_column(String(200))  # key of the InvoiceImage row
    invoice_error: Mapped[str | None] = mapped_column(Text)
    charged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    client: Mapped[Client] = relationship(back_populates="charges")


class InvoiceImage(Base):
    """Invoice PNG + thumbnail. Kept in the database because hosted disks (Render) are wiped on deploy."""

    __tablename__ = "invoice_images"

    charge_id: Mapped[int] = mapped_column(ForeignKey("charges.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(32))
    image: Mapped[bytes] = mapped_column(LargeBinary)
    thumb: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
