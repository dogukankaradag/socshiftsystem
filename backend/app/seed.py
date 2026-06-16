"""Seed + migration routines (v0.6.2 rol sistemi dahil)."""
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

log = logging.getLogger(__name__)
settings = get_settings()


def _migrate_roles(db: Session) -> None:
    """v0.6.2 rol sistemi geçişi (PostgreSQL + SQLite ortak yol).

    PostgreSQL enum tipi `Base.metadata.create_all()` ile **yeni değer
    eklenmez**; bunun için `ALTER TYPE role ADD VALUE` gerekir. Bu yüzden:

      1) PG ise: yeni enum değerleri (`standard`, `super_admin`) ekle.
         `IF NOT EXISTS` ile idempotent. Autocommit izolasyonu zorunlu
         çünkü bazı PG sürümleri ALTER TYPE'ı transaction içinde reddeder.
      2) Eski rolleri (`operator/supervisor/admin`) standard'a UPDATE et.
      3) En az bir super_admin yoksa seed_admin email'ini super_admin'e
         yükselt. Hiç kullanıcı yoksa seed_defaults sonradan oluşturur.

    SQLite enum'u string'e benzediği için ALTER TYPE adımı atlanır;
    UPDATE doğrudan çalışır.
    """
    dialect = engine.dialect.name

    # 1) PG enum'una yeni değerleri ekle (autocommit ile).
    if dialect == "postgresql":
        try:
            with engine.connect() as conn:
                conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                conn.execute(text("ALTER TYPE role ADD VALUE IF NOT EXISTS 'standard'"))
                conn.execute(text("ALTER TYPE role ADD VALUE IF NOT EXISTS 'super_admin'"))
            log.info("Role enum altered (added 'standard' + 'super_admin' if missing)")
        except Exception:
            # ALTER hata verirse bile sistem yine de açılmaya çalışsın.
            log.exception("ALTER TYPE role ADD VALUE failed (continuing)")

    # 2) Eski rol değerlerini standard'a güncelle (PG/SQLite ortak).
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

    # 3) En az bir super_admin var mı? Yoksa seed_admin'i yükselt.
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
    """v0.8.3: eski (day, duty_type) unique index'i sil; yeni index zaten
    create_all tarafından oluşturulur. PG için manuel DROP gerekir."""
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            # Eski v0.8.1 index'i (sadece varsa düşür)
            conn.execute(text("DROP INDEX IF EXISTS ix_daily_duty_unique"))
        log.info("Old daily_duty unique index dropped (if existed).")
    except Exception:
        log.exception("daily_duty index migration failed (continuing)")


def _migrate_monthly_shift_slot_enum(db: Session) -> None:
    """v0.8.6: monthlyshiftslot enum'una 'wfh' değerini ekle.
    PG'de ALTER TYPE; SQLite'da atlanır (string enum)."""
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


def seed_defaults(db: Session) -> None:
    # Önce mevcut rolleri migrate et.
    _migrate_roles(db)
    # v0.8.3: eski daily_duty unique index'ini sil
    _migrate_daily_duty_index(db)
    # v0.8.6: monthlyshiftslot enum'una 'wfh' ekle
    _migrate_monthly_shift_slot_enum(db)

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

    db.commit()


# v0.7.0: Aylık vardiya jeneratörü için bilinen personel seed verisi.
# Excel'deki renk kodlamasından çıkardığım gruplama:
#   fixed_a (siyah font, İstanbul, vardiyaya hiç girmez): Rıdvan, Fatih
#   istanbul (mavi font, vardiyaya girer): Mehmet, Beyza, Kübra, Enes, Duygu, İrfan
#   istanbul (mavi, on-call rotasyonu): Yağız, Sabri
#   ankara (kırmızı, vardiyaya girer): Doğukan, Burak, Talha, Hasan, Furkan
#   ankara (kırmızı, on-call rotasyonu): Ülkü, Zehra
_SEED_PERSONNEL = [
    # (name, location, group, is_oncall_only, is_fixed_a)
    ("Rıdvan", PersonnelLocation.istanbul, PersonnelGroup.fixed_a, False, True),
    ("Fatih",  PersonnelLocation.istanbul, PersonnelGroup.fixed_a, False, True),
    ("Mehmet", PersonnelLocation.istanbul, PersonnelGroup.istanbul, False, False),
    ("Beyza",  PersonnelLocation.istanbul, PersonnelGroup.istanbul, False, False),
    ("Kübra",  PersonnelLocation.istanbul, PersonnelGroup.istanbul, False, False),
    ("Enes",   PersonnelLocation.istanbul, PersonnelGroup.istanbul, False, False),
    ("Duygu",  PersonnelLocation.istanbul, PersonnelGroup.istanbul, False, False),
    ("İrfan",  PersonnelLocation.istanbul, PersonnelGroup.istanbul, False, False),
    ("Yağız",  PersonnelLocation.istanbul, PersonnelGroup.istanbul, True,  False),
    ("Sabri",  PersonnelLocation.istanbul, PersonnelGroup.istanbul, True,  False),
    ("Doğukan", PersonnelLocation.ankara, PersonnelGroup.ankara, False, False),
    ("Burak",   PersonnelLocation.ankara, PersonnelGroup.ankara, False, False),
    ("Talha",   PersonnelLocation.ankara, PersonnelGroup.ankara, False, False),
    ("Hasan",   PersonnelLocation.ankara, PersonnelGroup.ankara, False, False),
    ("Furkan",  PersonnelLocation.ankara, PersonnelGroup.ankara, False, False),
    ("Ülkü",    PersonnelLocation.ankara, PersonnelGroup.ankara, True,  False),
    ("Zehra",   PersonnelLocation.ankara, PersonnelGroup.ankara, True,  False),
]


def _seed_personnel(db: Session) -> None:
    """Idempotent: aynı isimle kişi varsa atlanır (kullanıcı manuel güncelleyebilir)."""
    for name, loc, group, oncall_only, fixed_a in _SEED_PERSONNEL:
        if db.query(Personnel).filter(Personnel.full_name == name).first():
            continue
        db.add(Personnel(
            full_name=name,
            location=loc,
            group=group,
            is_oncall_only=oncall_only,
            is_fixed_a=fixed_a,
            is_active=True,
        ))
    log.info("Personnel seeded (idempotent): %d names", len(_SEED_PERSONNEL))
