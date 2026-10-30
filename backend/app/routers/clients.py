import csv
import io
import re

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..db import get_db
from ..models import Charge, Client
from ..schemas import CardSaveOut, ClientIn, ClientOut, ImportResult
from ..services.grow import CustomerInfo, get_gateway

router = APIRouter(prefix="/clients", tags=["clients"], dependencies=[Depends(require_auth)])

MAX_IMPORT_BYTES = 1_000_000

# Accepted CSV headers (Hebrew or English) for each client field.
HEADER_ALIASES = {
    "name": ("name", "שם הגן", "שם", "גן"),
    "contact_name": ("contact_name", "שם הגננת", "גננת", "איש קשר"),
    "phone": ("phone", "טלפון", "נייד"),
    "email": ("email", "מייל", "אימייל"),
    "invoice_name": ("invoice_name", "שם לחשבונית"),
    "tax_id": ("tax_id", "ח.פ", 'ח"פ', "מספר עוסק"),
    "address": ("address", "כתובת"),
    "notes": ("notes", "הערות"),
}


def _get_client(db: Session, client_id: int) -> Client:
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "הגן לא נמצא")
    return client


def _name_taken(db: Session, name: str, exclude_id: int | None = None) -> bool:
    stmt = select(Client.id).where(func.lower(Client.name) == name.lower())
    if exclude_id is not None:
        stmt = stmt.where(Client.id != exclude_id)
    return db.scalar(stmt) is not None


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    field = str(err["loc"][0]) if err.get("loc") else ""
    label = HEADER_ALIASES.get(field, (field, field))[1]
    return f"{label}: {err['msg'].removeprefix('Value error, ')}"


@router.get("", response_model=list[ClientOut])
def list_clients(q: str = "", include_inactive: bool = False, db: Session = Depends(get_db)):
    stmt = select(Client).order_by(Client.name)
    if not include_inactive:
        stmt = stmt.where(Client.active.is_(True))
    q = q.strip()
    if q:
        like = f"%{q}%"
        conditions = [Client.name.ilike(like), Client.contact_name.ilike(like)]
        digits = re.sub(r"\D", "", q)
        if digits:
            conditions.append(Client.phone.contains(digits))
        stmt = stmt.where(or_(*conditions))
    return db.scalars(stmt).all()


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(body: ClientIn, db: Session = Depends(get_db)):
    if _name_taken(db, body.name):
        raise HTTPException(status.HTTP_409_CONFLICT, "כבר קיים גן בשם הזה")
    client = Client(**body.model_dump())
    db.add(client)
    db.commit()
    return client


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: int, db: Session = Depends(get_db)):
    return _get_client(db, client_id)


@router.put("/{client_id}", response_model=ClientOut)
def update_client(client_id: int, body: ClientIn, db: Session = Depends(get_db)):
    client = _get_client(db, client_id)
    if _name_taken(db, body.name, exclude_id=client_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "כבר קיים גן בשם הזה")
    for key, value in body.model_dump().items():
        setattr(client, key, value)
    db.commit()
    return client


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(client_id: int, db: Session = Depends(get_db)):
    client = _get_client(db, client_id)
    if db.scalar(select(Charge.id).where(Charge.client_id == client_id).limit(1)) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "לגן יש היסטוריית חיובים, ולכן אי אפשר למחוק אותו. אפשר לסמן אותו כלא פעיל."
        )
    db.delete(client)
    db.commit()


@router.post("/import", response_model=ImportResult)
def import_clients(file: UploadFile, db: Session = Depends(get_db)):
    raw = file.file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "הקובץ גדול מדי")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1255", errors="replace")  # Hebrew Excel exports

    reader = csv.DictReader(io.StringIO(text))
    mapping: dict[str, str] = {}
    for column in reader.fieldnames or []:
        key = next((k for k, aliases in HEADER_ALIASES.items() if column.strip().lower() in aliases), None)
        if key:
            mapping[column] = key
    if not {"name", "phone"} <= set(mapping.values()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "בקובץ חייבות להיות עמודות 'שם הגן' ו'טלפון'")

    existing = {n.lower() for n in db.scalars(select(Client.name))}
    created, skipped, errors = 0, 0, []
    for line_no, row in enumerate(reader, start=2):
        data = {key: row.get(column) for column, key in mapping.items()}
        if not any((v or "").strip() for v in data.values()):
            continue
        try:
            parsed = ClientIn(**data)
        except ValidationError as exc:
            errors.append(f"שורה {line_no}: {_first_error(exc)}")
            continue
        if parsed.name.lower() in existing:
            skipped += 1
            continue
        db.add(Client(**parsed.model_dump()))
        existing.add(parsed.name.lower())
        created += 1
    db.commit()
    return ImportResult(created=created, skipped=skipped, errors=errors)


@router.post("/{client_id}/card", response_model=CardSaveOut)
def start_card_save(client_id: int, db: Session = Depends(get_db)):
    """Start saving the client's card in Grow. Mock mode saves a fake token immediately;
    live mode is expected to return a Grow page URL for the client to fill in."""
    client = _get_client(db, client_id)
    try:
        result = get_gateway().start_card_save(CustomerInfo.of(client))
    except NotImplementedError:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "שמירת כרטיס דרך Grow עוד לא מומשה") from None
    if result.token:
        client.grow_card_token = result.token
        db.commit()
    return CardSaveOut(has_card_token=client.has_card_token, url=result.url)


@router.delete("/{client_id}/card", response_model=CardSaveOut)
def remove_card(client_id: int, db: Session = Depends(get_db)):
    client = _get_client(db, client_id)
    client.grow_card_token = None
    db.commit()
    return CardSaveOut(has_card_token=False)
