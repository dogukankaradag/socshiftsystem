"""FastAPI application entrypoint."""
from __future__ import annotations
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Base, SessionLocal, engine
from .routers import (
    analytics, auth, customers, daily_duty, entries, incidents, mailing, monthly_shifts,
    reports, roster, shifts, users,
)
from .scheduler import start_scheduler, stop_scheduler
from .seed import seed_defaults

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("shift-handover")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    log.info("Starting %s in %s mode", settings.app_name, settings.environment)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    log.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "app": settings.app_name, "env": settings.environment}


# Register routers
prefix = settings.api_prefix
app.include_router(auth.router, prefix=prefix)
app.include_router(users.router, prefix=prefix)
app.include_router(shifts.router, prefix=prefix)
app.include_router(entries.router, prefix=prefix)
app.include_router(incidents.router, prefix=prefix)
app.include_router(reports.router, prefix=prefix)
app.include_router(analytics.router, prefix=prefix)
app.include_router(mailing.router, prefix=prefix)
app.include_router(roster.router, prefix=prefix)
app.include_router(customers.router, prefix=prefix)
app.include_router(monthly_shifts.router, prefix=prefix)
app.include_router(monthly_shifts.personnel_router, prefix=prefix)
app.include_router(daily_duty.router, prefix=prefix)
