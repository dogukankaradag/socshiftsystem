"""On-prem IMAP poller for DHS / İYS auto-ingest.

Işleyiş:
  - imap_host boşsa hiçbir şey yapmaz.
  - Her çalıştığında (varsayılan: 600 sn) yapılandırılan IMAP klasörüne
    (varsayılan: INBOX) bağlanır ve UNSEEN (okunmamış) mesajları çeker.
  - Her mesaj için önce DHS sonra İYS regex'i konu satırına uygulanır.
    Eşleşmezse body'de (düz metin) arar. Bulursa girişteki ilk rakam grubunu
    `numeric_value` olarak alır.
  - Eşleşen her mesaj için açık vardiya (yoksa oluşturulur) altına
    `source='imap'` etiketli bir Entry oluşturulur ve mail SEEN olarak
    işaretlenir. Eşleşmezse mail olduğu gibi bırakılır.

Neden standart `imaplib` kullanıldı?
  - On-prem / kurumsal Exchange sunucularında genellikle basit IMAP/TLS
    yeterlidir; ek bağımlılık eklemiyoruz. imaplib senkron bir modül olduğu
    için async scheduler içinden thread pool üzerinden çağrılır.
"""
from __future__ import annotations
import asyncio
import email
import imaplib
import logging
import re
from email.header import decode_header, make_header
from typing import Optional

from .ai import ENTRY_TYPE_LABEL_TR
from .config import get_settings
from .database import SessionLocal
from .models import Entry, EntryType
from .services import get_or_create_open_shift

log = logging.getLogger(__name__)
settings = get_settings()


def _decode_header(raw: Optional[str]) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:  # noqa: BLE001
        return raw


def _plain_body(msg: email.message.Message) -> str:
    """Mesajın text/plain gövdesini çıkar. HTML-only ise kabaca etiketleri temizle."""
    if msg.is_multipart():
        # Önce plain'i tercih et.
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = part.get("Content-Disposition", "")
            if ctype == "text/plain" and "attachment" not in (disp or ""):
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:  # noqa: BLE001
                    continue
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    html = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                    return re.sub(r"<[^>]+>", " ", html)
                except Exception:  # noqa: BLE001
                    continue
        return ""
    # Tek parçalı
    try:
        payload = msg.get_payload(decode=True)
        if payload is None:
            return ""
        text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        if msg.get_content_type() == "text/html":
            return re.sub(r"<[^>]+>", " ", text)
        return text
    except Exception:  # noqa: BLE001
        return ""


def _classify(subject: str, body: str) -> Optional[tuple[EntryType, int]]:
    """Konu + body üzerinde DHS / İYS regex'lerini uygula, sayıyı döndür."""
    tests: list[tuple[EntryType, str]] = [
        (EntryType.dhs, settings.imap_subject_dhs_regex),
        (EntryType.iys, settings.imap_subject_iys_regex),
    ]
    for etype, pattern in tests:
        if not pattern:
            continue
        try:
            regex = re.compile(pattern)
        except re.error:
            log.error("Invalid IMAP regex for %s: %r", etype.value, pattern)
            continue
        for hay in (subject, body):
            m = regex.search(hay or "")
            if not m:
                continue
            # İlk rakam grubunu ya da ilk tam sayı dizisini al.
            if m.groups():
                for g in m.groups():
                    if g and g.isdigit():
                        return etype, int(g)
            # Grup yoksa: gövdeden ilk tam sayıyı ara.
            num_match = re.search(r"\d{1,6}", hay or "")
            if num_match:
                return etype, int(num_match.group(0))
    return None


def _poll_sync() -> int:
    """Senkron poll çekirdeği. Yaratılan giriş sayısını döndürür."""
    host = settings.imap_host
    if not host:
        return 0
    created = 0
    conn: Optional[imaplib.IMAP4] = None
    try:
        if settings.imap_use_ssl:
            conn = imaplib.IMAP4_SSL(host, settings.imap_port)
        else:
            conn = imaplib.IMAP4(host, settings.imap_port)
        if settings.imap_username:
            conn.login(settings.imap_username, settings.imap_password or "")
        conn.select(settings.imap_folder)
        status, data = conn.search(None, "UNSEEN")
        if status != "OK" or not data or not data[0]:
            return 0
        ids = data[0].split()
        if not ids:
            return 0
        log.info("IMAP poll: %d unseen message(s)", len(ids))

        db = SessionLocal()
        try:
            shift = get_or_create_open_shift(db)
            for msg_id in ids:
                fetch_status, fetch_data = conn.fetch(msg_id, "(RFC822)")
                if fetch_status != "OK" or not fetch_data:
                    continue
                raw_bytes = fetch_data[0][1] if isinstance(fetch_data[0], tuple) else None
                if not raw_bytes:
                    continue
                msg = email.message_from_bytes(raw_bytes)
                subject = _decode_header(msg.get("Subject"))
                body = _plain_body(msg)

                result = _classify(subject, body)
                if not result:
                    # Eşleşmedi: SEEN işaretleme, sonraki çalıştırmaya bırak.
                    continue
                etype, numeric = result

                entry = Entry(
                    shift_id=shift.id,
                    author_id=shift.supervisor_id or 0,  # 0 olamaz → varsa supervisor, yoksa boş bırak
                    entry_type=etype,
                    title=subject[:255] if subject else None,
                    body="",
                    numeric_value=numeric,
                    source="imap",
                )
                # author_id 0 değil, None da değil ama FK var. Supervisor yoksa
                # ilk admin'i fallback olarak kullan.
                if not entry.author_id:
                    from .models import Role, User
                    admin = db.query(User).filter(User.role == Role.admin).first()
                    if admin:
                        entry.author_id = admin.id
                    else:
                        log.warning("IMAP entry atlandı: author_id boş ve admin bulunamadı")
                        continue

                db.add(entry)
                db.commit()
                created += 1
                log.info("IMAP entry oluşturuldu: %s = %d (subject=%r)",
                         ENTRY_TYPE_LABEL_TR.get(etype, etype.value), numeric, subject[:80])

                # Mail'i SEEN olarak işaretle.
                try:
                    conn.store(msg_id, "+FLAGS", "\\Seen")
                except Exception:  # noqa: BLE001
                    log.exception("IMAP SEEN flag set failed")
        finally:
            db.close()
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass
    return created


async def poll_once() -> int:
    """imap_poll_tick içinden çağrılan async sarmalayıcı."""
    return await asyncio.to_thread(_poll_sync)
