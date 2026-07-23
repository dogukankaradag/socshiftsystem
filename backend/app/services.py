"""Higher-level service functions shared by routers and scheduler."""
from __future__ import annotations
import logging
from datetime import datetime, time, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from . import ai, email_service, report_builder
from .config import get_settings
from sqlalchemy import or_

from .models import (
    AuditLog, Entry, EntryType, MailingList, Report, ReportStatus, Shift, ShiftType, User,
)

log = logging.getLogger(__name__)
_settings = get_settings()


def detect_shift_type(now_utc: Optional[datetime] = None) -> ShiftType:
    """Aktif vardiyayı (A/B/C) yerel saate (Europe/Istanbul) göre algıla.

    A: 07:30 - 15:30
    B: 15:30 - 23:30
    C: 23:30 - 07:30 (gece, bir sonraki güne sarar)
    """
    tz = ZoneInfo(_settings.scheduler_timezone)
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    local = now_utc.astimezone(tz).time()

    a_start, a_end = time(7, 30), time(15, 30)
    b_start, b_end = time(15, 30), time(23, 30)
    if a_start <= local < a_end:
        return ShiftType.a
    if b_start <= local < b_end:
        return ShiftType.b
    return ShiftType.c


def get_or_create_open_shift(db: Session, shift_type: Optional[ShiftType] = None) -> Shift:
    """Açık vardiya varsa döner, yoksa saate göre A/B/C tipinde yeni bir tane oluşturur."""
    open_shift = (
        db.query(Shift)
        .filter(Shift.ended_at.is_(None))
        .order_by(Shift.started_at.desc())
        .first()
    )
    if open_shift:
        return open_shift
    if shift_type is None:
        shift_type = detect_shift_type()
    shift = Shift(shift_type=shift_type, started_at=datetime.now(timezone.utc))
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


def audit(db: Session, actor: Optional[User], action: str,
          target_type: Optional[str] = None, target_id: Optional[int] = None,
          payload: Optional[dict] = None) -> None:
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        action=action, target_type=target_type, target_id=target_id,
        payload=payload or None,
    )
    db.add(entry)
    db.commit()


def resolve_recipients(db: Session, shift: Shift,
                       override: Optional[list[str]] = None) -> tuple[list[str], list[str]]:
    """Resolve TO + CC lists for a shift report.

    Priority:
      1) Explicit override (TO only)
      2) Mailing list bound to the shift_type
      3) Default mailing list
    Returns (to_list, cc_list). Either may be empty.
    """
    if override:
        return override, []

    ml = (
        db.query(MailingList)
        .filter(MailingList.shift_type == shift.shift_type)
        .first()
    )
    if not ml:
        ml = db.query(MailingList).filter(MailingList.is_default.is_(True)).first()
    if not ml:
        return [], []

    to_list = [r.strip() for r in (ml.recipients or "").split(",") if r.strip()]
    cc_list = [r.strip() for r in (ml.cc_recipients or "").split(",") if r.strip()]
    return to_list, cc_list


def generate_report(db: Session, shift: Shift, generated_by: Optional[User] = None,
                    subject_override: Optional[str] = None) -> Report:
    """Build a Report row (status=draft) from the shift's current entries.

    Rapora ayrıca, `occurs_at > şimdi` olan diğer vardiyalardaki planlı
    girişler de "Yaklaşan Planlı İşler" olarak dahil edilir. Böylece
    3 gün sonra için girilen bir plan, araya giren her vardiya raporuna
    otomatik olarak taşınır ve operatöre hatırlatılır.
    """
    # v0.9.5: Tek-seferlik türler (dispatch sonrası bir sonraki rapora
    # dahil edilmez). reported_at NULL olanlar rapora girer:
    #   - callers, dhs, iys, important_work → dispatch sonrası otomatik işaretlenir
    #   - info                              → dispatch modal'ında kullanıcı seçer
    # Diğer türler (ör. l2_escalation, ddos_transfer) reported_at'tan bağımsız
    # her zaman dahil (DDoS için ayrı ResolveScheduledModal akışı çalışır).
    _reset_types = (
        EntryType.callers,
        EntryType.dhs,
        EntryType.iys,
        EntryType.important_work,
        EntryType.info,
    )
    entries: List[Entry] = (
        db.query(Entry)
        .filter(Entry.shift_id == shift.id)
        .filter(or_(
            Entry.entry_type.notin_(_reset_types),
            Entry.reported_at.is_(None),
        ))
        .order_by(Entry.created_at.asc())
        .all()
    )
    now_utc = datetime.now(timezone.utc)
    # "Yaklaşan Planlı İşler" listesi yalnızca **DDoS Taşıma** türü için
    # üretilir. v0.6.0'dan itibaren occurs_at sadece DDoS Taşıma'da
    # doldurulabiliyor; bu defansif filtre eski/legacy kayıtlardan başka
    # türlerin (Arayanlar, Bilgi, vb.) bir sonraki vardiyanın raporuna
    # sızmasını da kesin olarak engeller.
    upcoming: List[Entry] = (
        db.query(Entry)
        .filter(Entry.shift_id != shift.id)
        .filter(Entry.entry_type == EntryType.ddos_transfer)
        .filter(Entry.occurs_at.isnot(None))
        .filter(Entry.occurs_at > now_utc)
        .order_by(Entry.occurs_at.asc())
        .all()
    )
    ai_result = ai.summarize_shift(entries, upcoming=upcoming)
    title, summary, md, html = report_builder.build_report(
        shift, entries, ai_result,
        upcoming=upcoming, subject_override=subject_override,
    )

    report = Report(
        shift_id=shift.id,
        generated_by_id=generated_by.id if generated_by else None,
        title=title,
        summary=summary,
        body_markdown=md,
        body_html=html,
        status=ReportStatus.draft,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    audit(db, generated_by, "report.generated", "report", report.id,
          {"shift_id": shift.id, "entry_count": len(entries),
           "upcoming_count": len(upcoming)})
    return report


async def dispatch_report(db: Session, report: Report,
                          to_recipients: list[str],
                          cc_recipients: Optional[list[str]] = None,
                          actor: Optional[User] = None,
                          keep_info_entry_ids: Optional[list[int]] = None) -> Report:
    """Email the report to TO + CC and update its status.

    v0.9.5: `keep_info_entry_ids` is a list of Entry.id values (info type)
    that the user explicitly wants to CARRY OVER to the next report. All
    other info entries in this shift will be marked reported_at (won't
    appear in next generate). If None, ALL info entries are cleared
    (backward-compatible default).
    """
    cc_recipients = cc_recipients or []
    if not to_recipients and not cc_recipients:
        report.status = ReportStatus.failed
        report.error_message = "Alıcı tanımlanmamış."
        db.commit()
        return report

    report.recipients = ",".join(to_recipients) if to_recipients else None
    report.cc_recipients = ",".join(cc_recipients) if cc_recipients else None

    try:
        await email_service.send_email(
            to=to_recipients,
            cc=cc_recipients,
            subject=report.title,
            text_body=report.body_markdown,
            html_body=report.body_html,
        )
        report.status = ReportStatus.dispatched
        report.dispatched_at = datetime.now(timezone.utc)
        report.error_message = None
        audit(db, actor, "report.dispatched", "report", report.id,
              {"to": to_recipients, "cc": cc_recipients})
        # v0.9.5: Tek-seferlik türleri işaretle → bir sonraki generate'de
        # rapora dahil olmaz. Veri silinmez, sadece reported_at set edilir.
        auto_reset_types = (
            EntryType.callers,
            EntryType.dhs,
            EntryType.iys,
            EntryType.important_work,
        )
        auto_marked = (
            db.query(Entry)
            .filter(Entry.shift_id == report.shift_id)
            .filter(Entry.entry_type.in_(auto_reset_types))
            .filter(Entry.reported_at.is_(None))
            .update(
                {Entry.reported_at: report.dispatched_at},
                synchronize_session=False,
            )
        )
        if auto_marked:
            log.info(
                "Marked %d auto-reset entries (callers/dhs/iys/impwork) "
                "as reported for shift %s (report %s)",
                auto_marked, report.shift_id, report.id,
            )

        # v0.9.5: Info entries — kullanıcı seçimine göre işaretle.
        # keep_info_entry_ids listesindekiler DOKUNULMAZ (bir sonrakine taşınır);
        # diğer tüm reported_at=NULL info entry'leri işaretlenir.
        keep_ids = set(keep_info_entry_ids or [])
        info_query = (
            db.query(Entry)
            .filter(Entry.shift_id == report.shift_id)
            .filter(Entry.entry_type == EntryType.info)
            .filter(Entry.reported_at.is_(None))
        )
        if keep_ids:
            info_query = info_query.filter(Entry.id.notin_(keep_ids))
        info_marked = info_query.update(
            {Entry.reported_at: report.dispatched_at},
            synchronize_session=False,
        )
        if info_marked or keep_ids:
            log.info(
                "Info entries: marked %d, kept %d for shift %s (report %s)",
                info_marked, len(keep_ids), report.shift_id, report.id,
            )
    except Exception as exc:  # noqa: BLE001
        log.exception("Dispatch failed for report %s", report.id)
        report.status = ReportStatus.failed
        report.error_message = str(exc)[:500]
    db.commit()
    db.refresh(report)
    return report
