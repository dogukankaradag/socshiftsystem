"""Report generation, preview, dispatch, and PDF export."""
from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..auth import require_operator, require_supervisor
from ..config import get_settings
from ..database import get_db
from ..export import report_to_pdf
from ..models import Entry, Report, ReportStatus, Shift, User
from ..schemas import ReportGenerateRequest, ReportOut
from ..services import audit, dispatch_report, generate_report, resolve_recipients

router = APIRouter(prefix="/reports", tags=["reports"])
settings = get_settings()


def _to_utc(dt: datetime) -> datetime:
    """Interpret naive datetimes as being in the configured scheduler_timezone (GMT+3),
    then convert to UTC. Aware datetimes are converted directly."""
    if dt.tzinfo is None:
        tz = ZoneInfo(settings.scheduler_timezone)
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc)


@router.get("", response_model=List[ReportOut])
def list_reports(
    shift_id: Optional[int] = None,
    limit: int = 25,
    offset: int = 0,
    db: Session = Depends(get_db),
    _=Depends(require_operator),
):
    q = db.query(Report)
    if shift_id is not None:
        q = q.filter(Report.shift_id == shift_id)
    return q.order_by(Report.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: int, db: Session = Depends(get_db), _=Depends(require_operator)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapor bulunamadı")
    return report


@router.post("/generate", response_model=ReportOut, status_code=201)
async def generate(
    payload: ReportGenerateRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_supervisor),
):
    shift = db.query(Shift).filter(Shift.id == payload.shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Vardiya bulunamadı")

    # Operatör son adımda hangi vardiya etiketiyle (A/B/C) raporun
    # oluşturulacağını seçebilir; gönderilirse vardiyanın mevcut tipi güncellenir.
    if payload.shift_type is not None and payload.shift_type != shift.shift_type:
        previous = shift.shift_type.value
        shift.shift_type = payload.shift_type
        db.commit()
        db.refresh(shift)
        audit(db, current, "shift.type_overridden", "shift", shift.id,
              {"from": previous, "to": payload.shift_type.value})

    report = generate_report(
        db, shift, generated_by=current,
        subject_override=payload.subject_override,
    )

    to_override = [str(e) for e in payload.to_recipients] if payload.to_recipients else None
    cc_override = [str(e) for e in payload.cc_recipients] if payload.cc_recipients else None

    if payload.scheduled_at is not None:
        # Persist TO/CC and schedule for later dispatch by the scheduler tick.
        to_list = to_override or []
        cc_list = cc_override or []
        if not to_list and not cc_list:
            # fall back to mailing list if user didn't supply anything
            fb_to, fb_cc = resolve_recipients(db, shift)
            to_list = to_list or fb_to
            cc_list = cc_list or fb_cc

        scheduled_utc = _to_utc(payload.scheduled_at)
        report.recipients = ",".join(to_list) if to_list else None
        report.cc_recipients = ",".join(cc_list) if cc_list else None
        report.scheduled_at = scheduled_utc
        report.status = ReportStatus.scheduled
        db.commit()
        db.refresh(report)
        audit(db, current, "report.scheduled", "report", report.id,
              {"scheduled_at": scheduled_utc.isoformat(), "to": to_list, "cc": cc_list})
        return report

    if payload.dispatch:
        if to_override is None and cc_override is None:
            to_list, cc_list = resolve_recipients(db, shift)
        else:
            to_list, cc_list = to_override or [], cc_override or []
        await dispatch_report(db, report, to_list, cc_list, actor=current)

    return report


@router.post("/{report_id}/dispatch", response_model=ReportOut)
async def dispatch(report_id: int, db: Session = Depends(get_db),
                   current: User = Depends(require_supervisor)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapor bulunamadı")
    to_list = [x.strip() for x in (report.recipients or "").split(",") if x.strip()]
    cc_list = [x.strip() for x in (report.cc_recipients or "").split(",") if x.strip()]
    if not to_list and not cc_list:
        shift = db.query(Shift).filter(Shift.id == report.shift_id).first()
        to_list, cc_list = resolve_recipients(db, shift) if shift else ([], [])
    return await dispatch_report(db, report, to_list, cc_list, actor=current)


@router.post("/{report_id}/cancel-schedule", response_model=ReportOut)
def cancel_schedule(report_id: int, db: Session = Depends(get_db),
                    current: User = Depends(require_supervisor)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapor bulunamadı")
    if report.status != ReportStatus.scheduled:
        raise HTTPException(status_code=400, detail="Yalnızca zamanlanmış raporlar iptal edilebilir.")
    report.status = ReportStatus.draft
    report.scheduled_at = None
    db.commit()
    db.refresh(report)
    audit(db, current, "report.schedule_cancelled", "report", report.id)
    return report


@router.get("/{report_id}/export.pdf")
def export_pdf(report_id: int, db: Session = Depends(get_db), _=Depends(require_operator)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapor bulunamadı")
    entries = db.query(Entry).filter(Entry.shift_id == report.shift_id).order_by(Entry.created_at.asc()).all()
    pdf_bytes = report_to_pdf(report, entries)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report_{report.id}.pdf"'},
    )
