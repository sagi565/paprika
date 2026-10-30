from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..db import get_db
from ..models import Charge, ChargeStatus, Client
from ..schemas import ClientCounts, CurrentMonth, DashboardOut, MonthRevenue, TopClient, YearRevenue
from ..services.billing import ensure_month_rows, shift_month

router = APIRouter(tags=["dashboard"], dependencies=[Depends(require_auth)])

DONE = (ChargeStatus.CHARGED, ChargeStatus.SENT)


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(months: int = Query(12, ge=3, le=36), db: Session = Depends(get_db)):
    current = date.today().strftime("%Y-%m")
    window = [shift_month(current, -i) for i in range(months - 1, -1, -1)]
    year = current[:4]
    ensure_month_rows(db, current)

    revenue: dict[str, float] = defaultdict(float)
    charged: dict[str, int] = defaultdict(int)
    for month, amount in db.execute(
        select(Charge.month, Charge.amount).where(Charge.month.in_(window), Charge.status.in_(DONE))
    ):
        revenue[month] += float(amount or 0)
        charged[month] += 1

    this_month = db.execute(
        select(Charge.status, Charge.amount).where(Charge.month == current)
    ).all()

    def count(*statuses: str) -> int:
        return sum(1 for s, _ in this_month if s in statuses)

    year_rows = db.execute(
        select(Charge.month, func.sum(Charge.amount))
        .where(Charge.month.startswith(f"{year}-"), Charge.status.in_(DONE))
        .group_by(Charge.month)
    ).all()
    year_total = sum(float(v or 0) for _, v in year_rows)

    top = db.execute(
        select(Client.id, Client.name, func.sum(Charge.amount).label("revenue"))
        .join(Charge.client)
        .where(Charge.month.startswith(f"{year}-"), Charge.status.in_(DONE))
        .group_by(Client.id, Client.name)
        .order_by(func.sum(Charge.amount).desc())
        .limit(5)
    ).all()

    active = db.scalar(select(func.count()).select_from(Client).where(Client.active.is_(True))) or 0
    inactive = db.scalar(select(func.count()).select_from(Client).where(Client.active.is_(False))) or 0
    without_card = (
        db.scalar(
            select(func.count())
            .select_from(Client)
            .where(Client.active.is_(True), Client.grow_card_token.is_(None))
        )
        or 0
    )

    return DashboardOut(
        months=[MonthRevenue(month=m, revenue=revenue[m], charged_count=charged[m]) for m in window],
        current=CurrentMonth(
            month=current,
            clients=len(this_month),
            total_amount=sum(float(a or 0) for _, a in this_month),
            charged_amount=revenue[current],
            charged_count=count(*DONE),
            pending_count=count(ChargeStatus.PENDING, ChargeStatus.PROCESSING),
            failed_count=count(ChargeStatus.FAILED),
            to_send_count=count(ChargeStatus.CHARGED),
            previous_revenue=revenue[shift_month(current, -1)],
        ),
        year=YearRevenue(
            year=int(year),
            revenue=year_total,
            average_month=year_total / len(year_rows) if year_rows else 0,
        ),
        clients=ClientCounts(active=active, inactive=inactive, without_card=without_card),
        top_clients=[TopClient(id=i, name=n, revenue=float(r or 0)) for i, n, r in top],
    )
