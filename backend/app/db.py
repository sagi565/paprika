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
)


def add_missing_columns() -> None:
    with engine.begin() as conn:
        for statement in NEW_COLUMNS:
            conn.execute(text(statement))
