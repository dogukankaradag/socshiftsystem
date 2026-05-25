"""Shift entry CRUD + search + CSV export."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..auth import require_operator
from ..database import get_db
from ..export import entries_to_csv
from ..models import Entry, EntryType, NUMERIC_ENTRY_TYPES, Shift, User
from ..schemas import EntryCreate, EntryOut, EntryUpdate
from ..services import audit, get_or_create_open_shift

# "Yeni vardiya raporu hazırlanırken" pop-up'ında karar gerektiren tipler.
# Diğer tipler (DHS/İYS sayım, Önemli İşler, Eskale, Arayanlar) bir önceki
# vardiyanın planlamasını taşımadığı için karar akışına dahil edilmez.
RESOLVABLE_ENTRY_TYPES = {EntryType.ddos_transfer, EntryType.info}

router = APIRouter(prefix="/entries", tags=["entries"])


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Naive datetime'i UTC say, aware ise UTC'ye çevir. Null geçer."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# Turkish display labels for auto-generated titles when the user doesn't supply one.
ENTRY_TYPE_LABEL = {
    EntryType.ddos_transfer: "DDoS Taşıma",
    EntryType.info: "Bilgi",
    EntryType.important_work: "Yapılan Önemli İşler",
    EntryType.l2_escalation: "L2'ye Eskale Edilen Konu",
    EntryType.callers: "Arayanlar",
    EntryType.dhs: "DHS",
    EntryType.iys: "İYS",
}


def _auto_title(entry_type: EntryType, body: Optional[str], numeric_value: Optional[int]) -> str:
    label = ENTRY_TYPE_LABEL.get(entry_type, entry_type.value)
    if entry_type in NUMERIC_ENTRY_TYPES and numeric_value is not None:
        return f"{label}: {numeric_value}"
    if body:
        snippet = body.strip().splitlines()[0][:80]
        return f"{label} - {snippet}" if snippet else label
    return label


def _to_out(e: Entry) -> EntryOut:
    out = EntryOut.model_validate(e)
    out.author_name = e.author.full_name if e.author else None
    return out


@router.get("", response_model=List[EntryOut])
def list_entries(
    shift_id: Optional[int] = None,
    entry_type: Optional[EntryType] = None,
    q: Optional[str] = Query(None, description="search in title/body"),
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    include_duplicates: bool = True,
    hide_past_scheduled: bool = Query(
        False,
        description=(
            "true ise, occurs_at zamanı geçmiş (geçmişte planlanmış) girişler "
            "listeden çıkarılır. occurs_at boş olanlar ve gelecek tarihliler "
            "etkilenmez. Panel görünümünü sadeleştirmek için kullanılır; "
            "analitik/CSV export ham veriyi kullanmaya devam eder."
        ),
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(require_operator),
):
    query = db.query(Entry).options(joinedload(Entry.author))
    if shift_id is not None:
        query = query.filter(Entry.shift_id == shift_id)
    if entry_type:
        query = query.filter(Entry.entry_type == entry_type)
    if since:
        query = query.filter(Entry.created_at >= since)
    if until:
        query = query.filter(Entry.created_at <= until)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Entry.title.ilike(like), Entry.body.ilike(like)))
    if not include_duplicates:
        query = query.filter(Entry.is_duplicate_of.is_(None))
    if hide_past_scheduled:
        # occurs_at NULL (zaman bilgisi olmayanlar) veya occurs_at >= now
        # (zamanı henüz gelmemiş/yaklaşan planlı işler) görünür kalır.
        # occurs_at < now (zamanı geçmiş planlamalar) gizlenir.
        now = datetime.now(timezone.utc)
        query = query.filter(or_(Entry.occurs_at.is_(None), Entry.occurs_at >= now))

    rows = query.order_by(Entry.created_at.desc()).offset(offset).limit(limit).all()
    return [_to_out(e) for e in rows]


@router.get("/upcoming", response_model=List[EntryOut])
def upcoming_entries(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _=Depends(require_operator),
):
    """Henüz zamanı gelmemiş planlı girişler (occurs_at > now)."""
    now = datetime.now(timezone.utc)
    rows = (
        db.query(Entry).options(joinedload(Entry.author))
        .filter(Entry.occurs_at.isnot(None))
        .filter(Entry.occurs_at > now)
        .order_by(Entry.occurs_at.asc())
        .limit(limit)
        .all()
    )
    return [_to_out(e) for e in rows]


@router.post("", response_model=EntryOut, status_code=201)
def create_entry(payload: EntryCreate, db: Session = Depends(get_db),
                 current: User = Depends(require_operator)):
    shift_id = payload.shift_id
    if shift_id is None:
        shift = get_or_create_open_shift(db)
        shift_id = shift.id
    else:
        if not db.query(Shift).filter(Shift.id == shift_id).first():
            raise HTTPException(status_code=400, detail="Shift not found")

    # Validation: numeric types require a numeric_value; text types require body.
    if payload.entry_type in NUMERIC_ENTRY_TYPES:
        if payload.numeric_value is None:
            raise HTTPException(
                status_code=400,
                detail=f"{payload.entry_type.value} için sayı girişi zorunludur.",
            )
    else:
        if not payload.body or not payload.body.strip():
            raise HTTPException(
                status_code=400,
                detail="Bu tür giriş için açıklama (detay) zorunludur.",
            )

    title = payload.title or _auto_title(payload.entry_type, payload.body, payload.numeric_value)

    entry = Entry(
        shift_id=shift_id,
        author_id=current.id,
        entry_type=payload.entry_type,
        title=title,
        body=payload.body or "",
        numeric_value=payload.numeric_value,
        occurs_at=_ensure_utc(payload.occurs_at),
        incident_id=payload.incident_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    audit(db, current, "entry.created", "entry", entry.id,
          {"type": entry.entry_type.value, "occurs_at": entry.occurs_at.isoformat() if entry.occurs_at else None})
    return _to_out(entry)


@router.patch("/{entry_id}", response_model=EntryOut)
def update_entry(entry_id: int, payload: EntryUpdate, db: Session = Depends(get_db),
                 current: User = Depends(require_operator)):
    """Vardiya girişini günceller. Tüm yetkili (operatör+) kullanıcılar
    birbirlerinin girişlerini düzenleyebilir; her değişiklik audit log'a
    yazıldığı için sorumluluk her zaman izlenebilir."""
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    data = payload.model_dump(exclude_unset=True)
    if "occurs_at" in data:
        data["occurs_at"] = _ensure_utc(data["occurs_at"])
        # Tarih değişirse, hatırlatma durumunu sıfırla ki yeni zamana göre
        # hatırlatma yine gönderilsin.
        entry.reminder_sent_at = None
    for k, v in data.items():
        setattr(entry, k, v)
    db.commit()
    db.refresh(entry)
    audit_payload = {
        "by_author": entry.author_id == current.id,
        "fields": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in data.items()},
    }
    audit(db, current, "entry.updated", "entry", entry.id, audit_payload)
    return _to_out(entry)


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: int, db: Session = Depends(get_db),
                 current: User = Depends(require_operator)):
    """Vardiya girişini siler. Tüm operatörler birbirlerinin girişini
    silebilir (vardiya devir sürecinde planlama değişiklikleri için).
    Her silme audit log'a yazılır, böylece denetim mümkündür."""
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    type_value = entry.entry_type.value if hasattr(entry.entry_type, "value") else str(entry.entry_type)
    audit_payload = {
        "type": type_value,
        "original_author_id": entry.author_id,
        "by_author": entry.author_id == current.id,
    }
    db.delete(entry)
    db.commit()
    audit(db, current, "entry.deleted", "entry", entry_id, audit_payload)
    return None


# ---------- Pending resolution flow ----------
#
# Yeni vardiya raporu hazırlanırken, "DDoS Taşıma" ve "Bilgi" tipindeki girişlerden
# occurs_at zamanı geçmiş olanlar için operatöre karar sorulur:
#   - completed         → giriş silinir (audit kaydı tutulur)
#   - reschedule (date) → occurs_at yeni tarihe güncellenir, hatırlatma resetlenir
#   - keep_unscheduled  → occurs_at NULL olur; tarih belli değil, manuel müdahale
#                         ile tarih atanana kadar listede görünür kalır.
#
# Diğer tipler bu akışa dahil edilmez (kullanıcı talebi).


class ResolveAction(BaseModel):
    """`/entries/{id}/resolve` payload'u.

    DDoS Taşıma için: completed | reschedule | keep_unscheduled
    Bilgi için:       keep | completed  (keep = raporda kalmaya devam etsin)
    """
    action: str = Field(
        ...,
        description="completed | reschedule | keep_unscheduled | keep",
        pattern="^(completed|reschedule|keep_unscheduled|keep)$",
    )
    new_occurs_at: Optional[datetime] = Field(
        default=None,
        description="action=reschedule ise zorunlu, yeni planlama zamanı (UTC)",
    )


@router.get("/pending-resolution", response_model=List[EntryOut])
def pending_resolution(
    db: Session = Depends(get_db),
    _=Depends(require_operator),
):
    """Yeni rapor öncesi karar bekleyen girişler.

    İki farklı kural birleştirilir (OR):
      • DDoS Taşıma: occurs_at < now (zamanı geçmiş planlamalar)
      • Bilgi:        bir önceki vardiyaya ait olan tüm Bilgi girişleri
                      (occurs_at önemli değil; her yeni rapor sonunda kullanıcıya
                       "raporda kalmaya devam etsin mi?" diye sorulur).

    Aktif (henüz kapatılmamış) vardiyanın Bilgi girişleri **dahil edilmez** —
    bunlar henüz devredilmedi, hâlâ aynı operatörün vardiyasında.
    """
    from ..models import Shift  # circular import'tan kaçınmak için lokal
    now = datetime.now(timezone.utc)

    # Aktif (ended_at IS NULL) vardiyaların ID'leri — bunlardaki Bilgi'leri hariç tut.
    active_shift_ids = [
        sid for (sid,) in db.query(Shift.id).filter(Shift.ended_at.is_(None)).all()
    ]

    rows = (
        db.query(Entry).options(joinedload(Entry.author))
        .filter(Entry.entry_type.in_(RESOLVABLE_ENTRY_TYPES))
        .filter(
            # DDoS: zamanı geçmiş planlamalar
            ((Entry.entry_type == EntryType.ddos_transfer)
             & Entry.occurs_at.isnot(None)
             & (Entry.occurs_at < now))
            |
            # Bilgi: aktif vardiya dışındaki tüm Bilgi girişleri
            ((Entry.entry_type == EntryType.info)
             & (~Entry.shift_id.in_(active_shift_ids) if active_shift_ids else True))
        )
        .order_by(Entry.entry_type.asc(), Entry.occurs_at.asc().nullslast(), Entry.created_at.asc())
        .all()
    )
    return [_to_out(e) for e in rows]


@router.post("/{entry_id}/resolve", response_model=Optional[EntryOut])
def resolve_entry(
    entry_id: int,
    payload: ResolveAction,
    db: Session = Depends(get_db),
    current: User = Depends(require_operator),
):
    """Geçmiş planlamalı bir DDoS Taşıma / Bilgi girişini karara bağlar.

    Diğer tipler için 400 döner — bu akış sadece RESOLVABLE_ENTRY_TYPES için.
    """
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.entry_type not in RESOLVABLE_ENTRY_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Bu tür için karar akışı uygulanamaz (sadece DDoS Taşıma ve Bilgi).",
        )

    type_value = entry.entry_type.value
    audit_payload = {
        "type": type_value,
        "action": payload.action,
        "old_occurs_at": entry.occurs_at.isoformat() if entry.occurs_at else None,
    }

    if payload.action == "completed":
        # Tamamlandı → giriş silinir, denetim için audit kaydı kalır.
        db.delete(entry)
        db.commit()
        audit(db, current, "entry.resolved", "entry", entry_id, audit_payload)
        return None

    if payload.action == "reschedule":
        if payload.new_occurs_at is None:
            raise HTTPException(
                status_code=400,
                detail="reschedule için new_occurs_at zorunludur.",
            )
        new_dt = _ensure_utc(payload.new_occurs_at)
        entry.occurs_at = new_dt
        # Yeni tarih → hatırlatma yeniden gönderilebilsin.
        entry.reminder_sent_at = None
        db.commit()
        db.refresh(entry)
        audit_payload["new_occurs_at"] = new_dt.isoformat() if new_dt else None
        audit(db, current, "entry.resolved", "entry", entry.id, audit_payload)
        return _to_out(entry)

    if payload.action == "keep_unscheduled":
        # Tarih belli değil → occurs_at NULL. Giriş listede kalmaya devam eder
        # ta ki manuel müdahale ile yeni bir tarih atanana kadar.
        entry.occurs_at = None
        entry.reminder_sent_at = None
        db.commit()
        db.refresh(entry)
        audit(db, current, "entry.resolved", "entry", entry.id, audit_payload)
        return _to_out(entry)

    if payload.action == "keep":
        # Bilgi: "raporda kalmaya devam etsin" → giriş aynen kalır, sadece
        # audit log'a karar yazılır. State değişikliği yok.
        audit(db, current, "entry.resolved", "entry", entry.id, audit_payload)
        return _to_out(entry)

    # Pydantic regex bunu zaten engelliyor ama defansif olarak:
    raise HTTPException(status_code=400, detail="Geçersiz action.")


@router.get("/export.csv")
def export_csv(
    shift_id: Optional[int] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    db: Session = Depends(get_db),
    _=Depends(require_operator),
):
    query = db.query(Entry)
    if shift_id is not None:
        query = query.filter(Entry.shift_id == shift_id)
    if since:
        query = query.filter(Entry.created_at >= since)
    if until:
        query = query.filter(Entry.created_at <= until)
    rows = query.order_by(Entry.created_at.asc()).all()
    csv_bytes = entries_to_csv(rows)
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=entries.csv"},
    )
