"""Async SMTP sender with on-prem support and dry-run fallback.

If SMTP_HOST is empty, messages are written to the application log instead of
sent — useful for local dev. Configure on-premise relay (e.g., Postfix or
Exchange Edge / Hub Transport with anonymous receive connector) by setting
SMTP_HOST plus port and (optional) auth in the .env file.
"""
from __future__ import annotations
import logging
from email.message import EmailMessage
from typing import Iterable, List, Optional

import aiosmtplib

from .config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()


def _split_clean(values: Optional[Iterable[str]]) -> List[str]:
    if not values:
        return []
    return [v.strip() for v in values if v and v.strip()]


async def send_email(
    to: Iterable[str],
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    cc: Optional[Iterable[str]] = None,
    attachments: Optional[List[tuple]] = None,
) -> None:
    to_list = _split_clean(to)
    cc_list = _split_clean(cc)
    if not to_list and not cc_list:
        log.warning("send_email: no recipients, skipping")
        return

    if not settings.smtp_host:
        log.info(
            "[KURU-CALISMA EMAIL] to=%s cc=%s subject=%r body_chars=%d html=%s attachments=%d",
            to_list, cc_list, subject, len(text_body),
            bool(html_body), len(attachments or []),
        )
        return

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    if to_list:
        msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    for filename, content, mimetype in (attachments or []):
        maintype, _, subtype = mimetype.partition("/")
        msg.add_attachment(content, maintype=maintype, subtype=subtype or "octet-stream", filename=filename)

    all_recipients = to_list + cc_list

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
            start_tls=settings.smtp_use_tls,
            use_tls=settings.smtp_use_ssl,
            recipients=all_recipients,
        )
        log.info("Email sent to=%s cc=%s subject=%r", to_list, cc_list, subject)
    except Exception as exc:  # noqa: BLE001
        log.exception("SMTP send failed: %s", exc)
        raise
