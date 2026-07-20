"""Seed + migration routines."""
from __future__ import annotations
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import get_settings
from .database import engine
from .models import (
    MailingList, Personnel, PersonnelGroup, PersonnelLocation, Role, User,
)
from .personnel_config import get_personnel_config

log = logging.getLogger(__name__)
settings = get_settings()


def _migrate_roles(db: Session) -> None:
    """Rol sistemi geçişi (PostgreSQL + SQLite ortak yol).

    PostgreSQL enum tipi `Base.metadata.create_all()` ile yeni değer eklenmez;
    bunun için `ALTER TYPE role ADD VALUE` gerekir. Bu yüzden:

      1) PG ise: yeni enum değerleri (`standard`, `super_admin`) ekle.
         `IF NOT EXISTS` ile idempotent.
      2) Eski rolleri (`operator/supervisor/admin`) standard'a UPDATE et.
      3) En az bir super_admin yoksa seed_admin email'ini super_admin'e yükselt.
    """
    dialect = engine.dialect.name

    if dialect == "postgresql":
        try:
            with engine.connect() as conn:
                conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                conn.execute(text("ALTER TYPE role ADD VALUE IF NOT EXISTS 'standard'"))
                conn.execute(text("ALTER TYPE role ADD VALUE IF NOT EXISTS 'super_admin'"))
            log.info("Role enum altered (added 'standard' + 'super_admin' if missing)")
        except Exception:
            log.exception("ALTER TYPE role ADD VALUE failed (continuing)")

    try:
        with engine.begin() as conn:
            for legacy in ("operator", "supervisor", "admin"):
                conn.execute(
                    text("UPDATE users SET role = 'standard' WHERE role = :legacy"),
                    {"legacy": legacy},
                )
        log.info("Legacy role values normalized to 'standard'")
    except Exception:
        log.exception("Legacy role migration UPDATE failed (continuing)")

    try:
        has_super = (
            db.query(User).filter(User.role == Role.super_admin).first() is not None
        )
    except Exception:
        log.exception("Super admin check failed; skipping promotion this run")
        return

    if has_super:
        return

    target = db.query(User).filter(User.email == settings.seed_admin_email).first()
    if target:
        target.role = Role.super_admin
        db.commit()
        log.info("Promoted seed admin to super_admin: %s", target.email)


def _migrate_daily_duty_index(db: Session) -> None:
    """Eski (day, duty_type) unique index'i sil."""
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text("DROP INDEX IF EXISTS ix_daily_duty_unique"))
        log.info("Old daily_duty unique index dropped (if existed).")
    except Exception:
        log.exception("daily_duty index migration failed (continuing)")


def _migrate_monthly_shift_slot_enum(db: Session) -> None:
    """monthlyshiftslot enum'una 'wfh' değerini ekle."""
    dialect = engine.dialect.name
    if dialect != "postgresql":
        return
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text("ALTER TYPE monthlyshiftslot ADD VALUE IF NOT EXISTS 'wfh'"))
        log.info("monthlyshiftslot enum: 'wfh' added (if missing).")
    except Exception:
        log.exception("monthlyshiftslot enum migration failed (continuing)")


def _migrate_entry_mpls_columns(db: Session) -> None:
    """entries tablosuna mpls_team_id + mpls_reminder_enabled kolonları."""
    dialect = engine.dialect.name
    if dialect != "postgresql":
        return
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(
                "ALTER TABLE entries "
                "ADD COLUMN IF NOT EXISTS mpls_team_id INTEGER "
                "REFERENCES mpls_teams(id)"
            ))
            conn.execute(text(
                "ALTER TABLE entries "
                "ADD COLUMN IF NOT EXISTS mpls_reminder_enabled BOOLEAN "
                "DEFAULT FALSE NOT NULL"
            ))
        log.info("entries.mpls_team_id + mpls_reminder_enabled columns added (if missing).")
    except Exception:
        log.exception("entries MPLS columns migration failed (continuing)")


def _migrate_entry_reported_at(db: Session) -> None:
    """entries.reported_at kolonu (callers reset için)."""
    dialect = engine.dialect.name
    if dialect != "postgresql":
        return
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(
                "ALTER TABLE entries "
                "ADD COLUMN IF NOT EXISTS reported_at TIMESTAMP WITH TIME ZONE"
            ))
        log.info("entries.reported_at column added (if missing).")
    except Exception:
        log.exception("entries.reported_at migration failed (continuing)")


def _location_enum(value: str) -> PersonnelLocation:
    try:
        return PersonnelLocation(value)
    except ValueError:
        return PersonnelLocation.istanbul


def _group_enum(value: str) -> PersonnelGroup:
    try:
        return PersonnelGroup(value)
    except ValueError:
        return PersonnelGroup.istanbul


def _seed_personnel(db: Session) -> None:
    """Config'ten okunan personeli DB'ye idempotent şekilde ekler."""
    cfg = get_personnel_config()
    added = 0
    for spec in cfg.personnel:
        if db.query(Personnel).filter(Personnel.full_name == spec.full_name).first():
            continue
        db.add(Personnel(
            full_name=spec.full_name,
            location=_location_enum(spec.location),
            group=_group_enum(spec.group),
            is_oncall_only=spec.is_oncall_only,
            is_fixed_a=spec.is_fixed_a,
            is_active=True,
        ))
        added += 1
    if added:
        log.info("Personnel seeded (idempotent): %d new records", added)


def _deactivate_stale_personnel(db: Session) -> None:
    """Config listesinde YER ALMAYAN personeli is_active=False yapar.

    Böylece kadrodan çıkarılan kişiler config'ten silinerek Aylık Vardiya
    listesinden otomatik düşer. Kayıtları silmez — geçmiş atamalar korunur.
    """
    cfg = get_personnel_config()
    active_names = {p.full_name for p in cfg.personnel}
    stale = (
        db.query(Personnel)
        .filter(Personnel.is_active.is_(True))
        .filter(~Personnel.full_name.in_(active_names))
        .all()
    ) if active_names else []
    for p in stale:
        p.is_active = False
    if stale:
        db.commit()
        log.info("Deactivated %d stale personnel (not in config)", len(stale))


def seed_defaults(db: Session) -> None:
    _migrate_roles(db)
    _migrate_daily_duty_index(db)
    _migrate_monthly_shift_slot_enum(db)
    _migrate_entry_mpls_columns(db)
    _migrate_entry_reported_at(db)

    admin = db.query(User).filter(User.email == settings.seed_admin_email).first()
    if not admin:
        admin = User(
            email=settings.seed_admin_email,
            full_name=settings.seed_admin_name,
            hashed_password=hash_password(settings.seed_admin_password),
            role=Role.super_admin,
            is_active=True,
        )
        db.add(admin)
        log.info("Seeded default super_admin: %s", settings.seed_admin_email)

    default_list = db.query(MailingList).filter(MailingList.is_default.is_(True)).first()
    if not default_list:
        db.add(MailingList(
            name="default",
            recipients=settings.default_mailing_list,
            is_default=True,
        ))
        log.info("Seeded default mailing list")

    _seed_personnel(db)
    _deactivate_stale_personnel(db)

    db.commit()
