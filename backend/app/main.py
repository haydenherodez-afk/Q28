"""HericR API — osebni CFO + davčni nadzornik za s.p."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import scheduler
from .api import ai_routes, auth_routes, data_routes, files_routes, insight_routes
from .config import get_settings
from .db import SessionLocal, init_db
from .services import watch_rules

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        watch_rules(db)
    finally:
        db.close()
    scheduler.start()
    yield
    scheduler.stop()


settings = get_settings()
app = FastAPI(title="HericR API", version="2.0.0", lifespan=lifespan,
              description="Osebni CFO + davčni nadzornik za s.p. Davke računa deterministični engine; AI razlaga.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in (auth_routes.router, data_routes.router, files_routes.router, insight_routes.router, ai_routes.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True, "app": settings.app_name}
