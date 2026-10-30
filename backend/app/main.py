import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .db import Base, SessionLocal, engine
from .routers import auth, charges, clients, dashboard, grow_webhook
from .seed import seed_demo, seed_demo_history
from .services.billing import recover_interrupted
from .services.invoices import import_legacy_files

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        recover_interrupted(db)
        import_legacy_files(db)
        if settings.seed_demo:
            seed_demo(db)
            seed_demo_history(db)
    yield


app = FastAPI(
    title="Paprika billing",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

for module in (auth, clients, charges, dashboard, grow_webhook):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}
