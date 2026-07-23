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
from pydantic import BaseModel

from ..models import Entry, EntryType, Report, ReportStatus, Shift, User
from ..schemas import ReportGenerateRequest, ReportOut, ReportUpdate
from ..services import audit, dispatch_report, generate_report, resolve_recipients

router = APIRouter(prefix="/reports", tags=["reports"])
settings = get_settings()


def _to_utc(dt: datetime) -> datetime:
    """Interpret naive datetimes as being in the configured scheduler_timezone (Europe/Istanbul),
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
        await dispatch_report(
            db, report, to_list, cc_list, actor=current,
            keep_info_entry_ids=payload.keep_info_entry_ids,
        )

    return report


class DispatchRequest(BaseModel):
    """v0.9.5: dispatch endpoint payload — kullanıcı info entry kararlarını iletir."""
    keep_info_entry_ids: Optional[List[int]] = None


@router.post("/{report_id}/dispatch", response_model=ReportOut)
async def dispatch(
    report_id: int,
    payload: Optional[DispatchRequest] = None,
    db: Session = Depends(get_db),
    current: User = Depends(require_supervisor),
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapor bulunamadı")
    to_list = [x.strip() for x in (report.recipients or "").split(",") if x.strip()]
    cc_list = [x.strip() for x in (report.cc_recipients or "").split(",") if x.strip()]
    if not to_list and not cc_list:
        shift = db.query(Shift).filter(Shift.id == report.shift_id).first()
        to_list, cc_list = resolve_recipients(db, shift) if shift else ([], [])
    keep_ids = payload.keep_info_entry_ids if payload else None
    return await dispatch_report(
        db, report, to_list, cc_list, actor=current,
        keep_info_entry_ids=keep_ids,
    )


class PendingInfoEntry(BaseModel):
    id: int
    title: Optional[str]
    body: Optional[str]
    created_at: datetime


@router.get("/pending-info/{shift_id}", response_model=List[PendingInfoEntry])
def list_pending_info(
    shift_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_operator),
):
    """v0.9.5: Bir shift'in henüz raporlanmamış (reported_at=NULL) Info
    girişlerini döner. Dispatch modal'ında kullanıcıya sunulur —
    kullanıcı hangilerinin bir sonraki rapora taşınacağına karar verir."""
    rows = (
        db.query(Entry)
        .filter(Entry.shift_id == shift_id)
        .filter(Entry.entry_type == EntryType.info)
        .filter(Entry.reported_at.is_(None))
        .order_by(Entry.created_at.asc())
        .all()
    )
    return [
        PendingInfoEntry(
            id=r.id, title=r.title, body=r.body, created_at=r.created_at,
        )
        for r in rows
    ]


@router.patch("/{report_id}", response_model=ReportOut)
def update_report(
    report_id: int,
    payload: ReportUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_supervisor),
):
    """Taslak / planlı / başarısız raporun başlık, gövde, alıcı veya planlama
    saatini günceller. Gönderilmiş raporlar değiştirilemez."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapor bulunamadı")
    if report.status == ReportStatus.dispatched:
        raise HTTPException(
            status_code=400,
            detail="Gönderilmiş rapor değiştirilemez. Yeni bir rapor oluşturun.",
        )

    data = payload.model_dump(exclude_unset=True)
    audit_payload: dict = {}

    if "title" in data and data["title"] is not None:
        report.title = data["title"]
        audit_payload["title"] = data["title"]
    if "summary" in data and data["summary"] is not None:
        report.summary = data["summary"]
        audit_payload["summary_len"] = len(data["summary"])
    if "body_markdown" in data and data["body_markdown"] is not None:
        report.body_markdown = data["body_markdown"]
        # body_html cache'ini düşür ki PDF/preview yeniden render olsun
        report.body_html = None
        audit_payload["body_markdown_len"] = len(data["body_markdown"])
    if "recipients" in data:
        if data["recipients"] is None:
            report.recipients = None
        else:
            report.recipients = ",".join(str(e) for e in data["recipients"])
        audit_payload["recipients"] = report.recipients
    if "cc_recipients" in data:
        if data["cc_recipients"] is None:
            report.cc_recipients = None
        else:
            report.cc_recipients = ",".join(str(e) for e in data["cc_recipients"])
        audit_payload["cc_recipients"] = report.cc_recipients
    if "scheduled_at" in data:
        if data["scheduled_at"] is None:
            report.scheduled_at = None
            # planlama düşürüldüyse statüyü taslağa çevir
            if report.status == ReportStatus.scheduled:
                report.status = ReportStatus.draft
        else:
            sched = data["scheduled_at"]
            if sched.tzinfo is None:
                sched = _to_utc(sched)
            else:
                sched = sched.astimezone(timezone.utc)
            report.scheduled_at = sched
            # planlama eklendiyse statüyü scheduled'a yükselt (failed/draft'tan)
            if report.status in (ReportStatus.draft, ReportStatus.failed):
                report.status = ReportStatus.scheduled
        audit_payload["scheduled_at"] = (
            report.scheduled_at.isoformat() if report.scheduled_at else None
        )

    db.commit()
    db.refresh(report)
    audit(db, current, "report.updated", "report", report.id, audit_payload)
    return report


@router.delete("/{report_id}", status_code=204)
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_supervisor),
):
    """Raporu siler. Gönderilmiş raporlar denetim izi için silinemez —
    bu durumda kullanıcı bunu süpervizör/admine açıkça bildirir."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapor bulunamadı")
    if report.status == ReportStatus.dispatched:
        raise HTTPException(
            status_code=400,
            detail=(
                "Gönderilmiş rapor silinemez (denetim kaydı). "
                "Lütfen yeni bir rapor düzeltmesi yayımlayın."
            ),
        )
    status_value = report.status.value if hasattr(report.status, "value") else str(report.status)
    db.delete(report)
    db.commit()
    audit(db, current, "report.deleted", "report", report_id, {"status": status_value})
    return None


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
