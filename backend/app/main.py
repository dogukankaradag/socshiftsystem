"""FastAPI application entrypoint."""
from __future__ import annotations
import logging
import os
import time as time_mod
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Base, SessionLocal, engine
from .routers import (
    analytics, auth, customers, daily_duty, entries, incidents, mailing, monthly_shifts,
    mpls_teams, reports, roster, shifts, users,
)
from .scheduler import start_scheduler, stop_scheduler
from .seed import seed_defaults

settings = get_settings()

# v0.9.4: Process-wide TZ. Container'da TZ=Europe/Istanbul zaten set, ama
# ekstra güvence — datetime.now() (naive) ve time.strftime() bu zone'da olur.
_TZ_NAME = settings.scheduler_timezone
os.environ.setdefault("TZ", _TZ_NAME)
try:
    time_mod.tzset()  # POSIX only; Windows'ta yok, Linux container'da OK
except AttributeError:
    pass


class _IstanbulFormatter(logging.Formatter):
    """Log timestamp'lerini Europe/Istanbul olarak ve TZ suffix'i ile yaz."""
    _tz = ZoneInfo(_TZ_NAME)

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=self._tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S %z")


_root = logging.getLogger()
_root.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(_IstanbulFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
))
# Root'un mevcut handler'larını temizle, sadece bizimkini bırak (çift log önle)
_root.handlers = [_handler]
log = logging.getLogger("shift-handover")


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
app.include_router(mpls_teams.router, prefix=prefix)
