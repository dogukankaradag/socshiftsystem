"""Idempotent seed routine — creates the default admin user and default mailing list."""
from __future__ import annotations
import logging

from sqlalchemy.orm import Session

from .auth import hash_password
from .config import get_settings
from .models import MailingList, Role, User

log = logging.getLogger(__name__)
settings = get_settings()


def seed_defaults(db: Session) -> None:
    admin = db.query(User).filter(User.email == settings.seed_admin_email).first()
    if not admin:
        admin = User(
            email=settings.seed_admin_email,
            full_name=settings.seed_admin_name,
            hashed_password=hash_password(settings.seed_admin_password),
            role=Role.admin,
            is_active=True,
        )
        db.add(admin)
        log.info("Seeded default admin: %s", settings.seed_admin_email)

    default_list = db.query(MailingList).filter(MailingList.is_default.is_(True)).first()
    if not default_list:
        db.add(MailingList(
            name="default",
            recipients=settings.default_mailing_list,
            is_default=True,
        ))
        log.info("Seeded default mailing list")

    db.commit()
