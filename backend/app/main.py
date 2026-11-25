import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .db import Base, SessionLocal, add_missing_columns, engine
from .routers import auth, charges, clients, dashboard, grow_webhook, passkeys, whatsapp as whatsapp_router
from .seed import seed_demo, seed_demo_history
from .services import whatsapp
from .services.billing import recover_interrupted, start_invoice_watcher
from .services.invoices import import_legacy_files

logging.basicConfig(level=logging.INFO)

_KEY_PARAM = re.compile(r"([?&]key=)[^&\s]*")


class HideWebhookKey(logging.Filter):
    """Grow calls our webhooks with ?key=<GROW_WEBHOOK_KEY>; keep it out of the access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_KEY_PARAM.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args)
        return True


# uvicorn has set up its loggers by the time it imports this module.
logging.getLogger("uvicorn.access").addFilter(HideWebhookKey())


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    add_missing_columns()
    with SessionLocal() as db:
        recover_interrupted(db)
        whatsapp.recover_interrupted(db)
        import_legacy_files(db)
        if settings.seed_demo:
            seed_demo(db)
            seed_demo_history(db)
    whatsapp.restore_session()
    stop_watcher = start_invoice_watcher()
    yield
    stop_watcher.set()


app = FastAPI(
    title="Paprika billing",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

for module in (auth, passkeys, clients, charges, dashboard, grow_webhook, whatsapp_router):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}
