"""Scheduled jobs — automatic + per-report scheduled dispatch + reminders.

Four jobs run concurrently:

  1) Daily cron (settings.report_dispatch_cron, Europe/Istanbul): generates and
     dispatches a report for the currently open shift at each shift change.
  2) Minute tick: scans for reports with status='scheduled' and
     scheduled_at <= now (UTC), and dispatches them. Lets supervisors schedule
     individual reports for a specific GMT+3 time from the UI.
  3) Reminder tick (every REMINDER_TICK_SECONDS): scans for Entry rows whose
     occurs_at falls inside the next REMINDER_LEAD_MINUTES window and for which
     reminder_sent_at is still NULL. Sends a short Turkish heads-up e-mail to
     the TO recipients of the shift's mailing list and stamps reminder_sent_at.
  4) IMAP poll tick (every IMAP_POLL_SECONDS): fetches UNSEEN messages from the
     configured mailbox and creates Entry rows tagged source='imap' for matches
     on the DHS / İYS subject regexes. Skipped when imap_host is empty.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import email_service
from .config import get_settings
from .database import SessionLocal
from .models import Entry, Report, ReportStatus, Shift
from .services import dispatch_report, generate_report, resolve_recipients

log = logging.getLogger(__name__)
settings = get_settings()
scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)


async def auto_dispatch_job():
    """Cron job: dispatch a report for the currently open shift."""
    log.info("auto_dispatch_job running at %s", datetime.now(timezone.utc))
    db = SessionLocal()
    try:
        open_shift = (
            db.query(Shift)
            .filter(Shift.ended_at.is_(None))
            .order_by(Shift.started_at.desc())
            .first()
        )
        if not open_shift:
            log.info("No open shift; nothing to dispatch")
            return

        report = generate_report(db, open_shift, generated_by=None)
        to_list, cc_list = resolve_recipients(db, open_shift)
        if not to_list and not cc_list:
            log.warning("No mailing list configured; report %s left as draft", report.id)
            return
        await dispatch_report(db, report, to_list, cc_list, actor=None)
    finally:
        db.close()


async def scheduled_reports_tick():
    """Minute job: flush any due 'scheduled' reports."""
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        due = (
            db.query(Report)
            .filter(Report.status == ReportStatus.scheduled)
            .filter(Report.scheduled_at.isnot(None))
            .filter(Report.scheduled_at <= now)
            .all()
        )
        if not due:
            return
        log.info("Flushing %d scheduled report(s)", len(due))
        for r in due:
            to_list = [x.strip() for x in (r.recipients or "").split(",") if x.strip()]
            cc_list = [x.strip() for x in (r.cc_recipients or "").split(",") if x.strip()]
            if not to_list and not cc_list:
                # fall back to mailing list for the shift
                shift = db.query(Shift).filter(Shift.id == r.shift_id).first()
                if shift:
                    to_list, cc_list = resolve_recipients(db, shift)
            await dispatch_report(db, r, to_list, cc_list, actor=None)
    finally:
        db.close()


async def reminder_tick():
    """Send 30-minute heads-up e-mails for upcoming scheduled entries.

    Bir giriş için `occurs_at` şimdi ile şimdi+REMINDER_LEAD_MINUTES arasındaysa
    ve `reminder_sent_at` boşsa — o girişin ait olduğu vardiyanın mail listesine
    (TO alıcılarına) kısa bir Türkçe hatırlatma gönderilir ve reminder_sent_at
    stamp'lenir. Böylece aynı giriş için ikinci bir hatırlatma atılmaz.
    """
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=settings.reminder_lead_minutes)
    tz = ZoneInfo(settings.scheduler_timezone)

    db = SessionLocal()
    try:
        from .ai import ENTRY_TYPE_LABEL_TR  # lokal import: dairesel bağımlılıktan kaçın

        rows = (
            db.query(Entry)
            .filter(Entry.occurs_at.isnot(None))
            .filter(Entry.reminder_sent_at.is_(None))
            .filter(Entry.occurs_at > now)
            .filter(Entry.occurs_at <= window_end)
            .all()
        )
        if not rows:
            return
        log.info("reminder_tick: %d upcoming entries in next %d min",
                 len(rows), settings.reminder_lead_minutes)

        for e in rows:
            shift = db.query(Shift).filter(Shift.id == e.shift_id).first()
            to_list, _cc = resolve_recipients(db, shift) if shift else ([], [])
            if not to_list:
                log.warning("Skipping reminder for entry %s: no TO recipients", e.id)
                # İstersek yine de işaretleyelim ki sürekli loglamayalım; ama
                # operatör mailing list eksikse farkında olsun diye
                # reminder_sent_at boş bırakıyoruz.
                continue

            occurs_local = e.occurs_at.astimezone(tz).strftime("%d.%m.%Y %H:%M")
            tur = ENTRY_TYPE_LABEL_TR.get(e.entry_type, e.entry_type.value)
            detay = (e.body or e.title or "").strip() or "(detay yok)"

            minutes_remaining = max(
                0, int((e.occurs_at - now).total_seconds() // 60)
            )
            subject = f"[Hatırlatma] {tur} — {occurs_local} (GMT+3)"
            text = (
                f"Planlı iş hatırlatması\n"
                f"========================\n\n"
                f"Tür: {tur}\n"
                f"Zaman: {occurs_local} (GMT+3) — yaklaşık {minutes_remaining} dk içinde\n\n"
                f"Detay:\n{detay}\n\n"
                f"— Vardiya Devir Sistemi\n"
            )
            html = (
                f"<div style='font-family:system-ui,sans-serif;line-height:1.5'>"
                f"<h2 style='color:#1d4ed8;margin:0 0 8px 0'>Planlı İş Hatırlatması</h2>"
                f"<p style='color:#374151;margin:0 0 12px 0'>"
                f"<b>Tür:</b> {tur}<br>"
                f"<b>Zaman:</b> {occurs_local} (GMT+3) — yaklaşık {minutes_remaining} dk içinde"
                f"</p>"
                f"<div style='padding:10px;border:1px solid #e5e7eb;"
                f"border-radius:6px;background:#fef3c7;white-space:pre-wrap'>{detay}</div>"
                f"<p style='color:#9ca3af;font-size:12px;margin-top:16px'>"
                f"Vardiya Devir Sistemi tarafından otomatik gönderilmiştir.</p>"
                f"</div>"
            )
            try:
                await email_service.send_email(
                    to=to_list, subject=subject,
                    text_body=text, html_body=html,
                )
                e.reminder_sent_at = datetime.now(timezone.utc)
                db.commit()
                log.info("Reminder sent for entry %s (occurs %s)", e.id, occurs_local)
            except Exception:  # noqa: BLE001
                log.exception("Reminder send failed for entry %s", e.id)
                db.rollback()
    finally:
        db.close()


async def imap_poll_tick():
    """Pull new DHS / İYS e-mails from an on-prem IMAP server and auto-insert entries.

    imap_host boşsa hiçbir şey yapmaz (geliştirme / kuru çalıştırma).
    """
    if not settings.imap_host:
        return
    # Local import to avoid loading imaplib at module import time
    from . import imap_poller
    try:
        await imap_poller.poll_once()
    except Exception:  # noqa: BLE001
        log.exception("imap_poll_tick failed")


def start_scheduler():
    if scheduler.running:
        return
    # 1) cron-based shift handover auto-dispatch
    try:
        trigger = CronTrigger.from_crontab(
            settings.report_dispatch_cron,
            timezone=settings.scheduler_timezone,
        )
        scheduler.add_job(auto_dispatch_job, trigger, id="auto_dispatch", replace_existing=True)
    except Exception as exc:  # noqa: BLE001
        log.error("Invalid REPORT_DISPATCH_CRON %r: %s — cron job disabled",
                  settings.report_dispatch_cron, exc)

    # 2) minute tick for per-report scheduled dispatch
    scheduler.add_job(
        scheduled_reports_tick,
        IntervalTrigger(seconds=30),
        id="scheduled_reports_tick",
        replace_existing=True,
    )

    # 3) reminder tick — 30 dk önce planlı işler için hatırlatma
    scheduler.add_job(
        reminder_tick,
        IntervalTrigger(seconds=settings.reminder_tick_seconds),
        id="reminder_tick",
        replace_existing=True,
    )

    # 4) IMAP poll tick — DHS / İYS otomatik girişi
    if settings.imap_host:
        scheduler.add_job(
            imap_poll_tick,
            IntervalTrigger(seconds=settings.imap_poll_seconds),
            id="imap_poll_tick",
            replace_existing=True,
        )

    scheduler.start()
    log.info(
        "Scheduler started (cron=%r, tz=%s, per-report=30s, reminder=%ss, imap=%s)",
        settings.report_dispatch_cron, settings.scheduler_timezone,
        settings.reminder_tick_seconds,
        f"{settings.imap_poll_seconds}s" if settings.imap_host else "disabled",
    )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
