"""Demo data so the site can be tried right away (SEED_DEMO=true only)."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Charge, ChargeStatus, Client
from .services.billing import month_label, shift_month
from .services.grow import CustomerInfo, dump_raw

HISTORY_MONTHS = 11
# Kindergartens close for part of the summer and for Passover.
SEASON = {4: 0.8, 7: 0.55, 8: 0.3, 9: 0.9}

DEMO_CLIENTS = [
    # name, contact, phone, amount this month, has saved card
    ("גן רימון", "מירב", "0501110001", "1240", True),
    ("גן חצב", "אורית", "0521110002", "980.50", True),
    ("גן אלון", "שירה", "0541110003", "1410", True),
    ("גן תאנה", "דנה", "0501110004", "760", False),
    ("גן שקד", "רותם", "0531110005", "1120", True),
    ("גן כלנית", "נועה", "0581110006", None, True),
    ("גן זית", "טל", "0501110007", "890", True),
    ("גן דובדבן", "הילה", "0521110008", "1305", True),
]


def seed_demo(db: Session) -> None:
    if db.scalar(select(Client.id).limit(1)) is not None:
        return
    month = date.today().strftime("%Y-%m")
    for i, (name, contact, phone, amount, has_card) in enumerate(DEMO_CLIENTS):
        client = Client(
            name=name,
            contact_name=contact,
            phone=phone,
            invoice_name=f"{name} בע״מ" if i % 3 == 0 else None,
            grow_card_token=f"mock-token-demo-{i}" if has_card else None,
        )
        db.add(client)
        db.flush()
        db.add(Charge(client_id=client.id, month=month, amount=Decimal(amount) if amount else None))
    db.commit()


def seed_demo_history(db: Session) -> None:
    """Past months of already-sent charges, so the dashboard has something to show.
    Skipped once any past charge has actually been charged."""
    current = date.today().strftime("%Y-%m")
    past = select(Charge.id).where(Charge.month < current, Charge.status != ChargeStatus.PENDING).limit(1)
    if db.scalar(past) is not None:
        return
    # Empty rows created just by browsing past months are replaced.
    for ch in db.scalars(select(Charge).where(Charge.month < current)):
        db.delete(ch)
    db.flush()
    clients = db.scalars(select(Client).order_by(Client.id)).all()
    for back in range(1, HISTORY_MONTHS + 1):
        month = shift_month(current, -back)
        year, mon = map(int, month.split("-"))
        for client in clients:
            base = 750 + (client.id * 137) % 600
            wobble = 1 + ((client.id * 7 + mon * 3) % 9 - 4) / 100
            amount = Decimal(str(round(base * SEASON.get(mon, 1.0) * wobble, -1)))
            charged_at = datetime(year, mon, 28, 10, tzinfo=timezone.utc)
            raw = {
                "transaction_id": f"MOCK-HIST-{client.id}-{month}",
                "invoice_number": str(30000 + back * 100 + client.id),
                "customer": CustomerInfo.of(client).__dict__,
                "amount": str(amount),
                "description": f"פירות וירקות, {month_label(month)}",
                "date": charged_at.strftime("%d/%m/%Y"),
            }
            db.add(
                Charge(
                    client_id=client.id,
                    month=month,
                    amount=amount,
                    status=ChargeStatus.SENT,
                    grow_transaction_id=raw["transaction_id"],
                    grow_payload=dump_raw(raw),
                    charged_at=charged_at,
                    sent_at=charged_at,
                )
            )
    db.commit()
