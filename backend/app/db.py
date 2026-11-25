from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

# prepare_threshold=None: no server-side prepared statements, so pooled URLs (PgBouncer) work too.
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args={"prepare_threshold": None})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db


# Columns added after the first deploy. create_all() makes new tables but never alters
# existing ones, so these are added here (idempotent, PostgreSQL).
NEW_COLUMNS = (
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS card_consent_at TIMESTAMPTZ",
    "ALTER TABLE charges ADD COLUMN IF NOT EXISTS grow_unique_id BIGINT",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS grow_card_transaction_id VARCHAR(100)",
    # Old 13-digit (millisecond) identifiers are rejected by Grow (error 1013); start again.
    "UPDATE charges SET grow_unique_id = NULL WHERE grow_unique_id > 4294967295",
    "CREATE UNIQUE INDEX IF NOT EXISTS charges_grow_unique_id ON charges (grow_unique_id)",
    # transactionUniqueIdentifier values: never repeated; on startup moved to at least the
    # current Unix time (fits Grow's 32-bit limit until 2106), so a reset database can't reuse one.
    "CREATE SEQUENCE IF NOT EXISTS grow_unique_id_seq",
    "SELECT setval('grow_unique_id_seq', GREATEST((SELECT last_value FROM grow_unique_id_seq),"
    " extract(epoch from now())::bigint))",
)


def add_missing_columns() -> None:
    with engine.begin() as conn:
        for statement in NEW_COLUMNS:
            conn.execute(text(statement))
