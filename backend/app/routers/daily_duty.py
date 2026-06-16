"""Dağıtıcı + Öğlen Nöbetçi günlük atama endpoint'leri (v0.8.1).

GET    /api/daily-duty?year=Y&month=M   herkes okur
POST   /api/daily-duty/generate         super_admin (jeneratör)
POST   /api/daily-duty                  super_admin (elle ekle)
PATCH  /api/daily-duty/{id}             super_admin (düzenle)
DELETE /api/daily-duty/{id}             super_admin

Tek sayfa UI tarafından kullanılır: ay başına dağıtıcı + öğlen ataması
birlikte döner; client iki kolonda gösterir.
"""
from __future__ import annotations
from calendar import monthrange
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from ..auth import require_authenticated, require_super_admin
from ..daily_duty_generator import generate_month
from ..database import get_db
from ..models import DailyDuty, Personnel, User
from ..schemas import (
    DailyDutyCreate, DailyDutyOut, DailyDutyUpdate,
    GenerateDailyDutyRequest, GenerateDailyDutyResult,
)
from ..services import audit


router = APIRouter(prefix="/daily-duty", tags=["daily-duty"])


def _to_out(d: DailyDuty) -> DailyDutyOut:
    out = DailyDutyOut.model_validate(d)
    out.personnel_name = d.personnel.full_name if d.personnel else None
    return out


@router.get("", response_model=List[DailyDutyOut])
def list_for_month(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    _=Depends(require_authenticated),
):
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    rows = (
        db.query(DailyDuty)
        .options(joinedload(DailyDuty.personnel))
        .filter(DailyDuty.day >= first)
        .filter(DailyDuty.day <= last)
        .order_by(DailyDuty.day.asc(), DailyDuty.duty_type.asc())
        .all()
    )
    return [_to_out(r) for r in rows]


@router.post("/generate", response_model=GenerateDailyDutyResult)
def generate_schedule(
    payload: GenerateDailyDutyRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_super_admin),
):
    res = generate_month(db, payload.year, payload.month, payload.overwrite_manual)
    audit(db, current, "daily_duty.generated", "daily_duty", None,
          {"year": payload.year, "month": payload.month,
           "created": res.assignments_created,
           "preserved": res.assignments_preserved,
           "overwrite_manual": payload.overwrite_manual})
    return GenerateDailyDutyResult(
        year=payload.year, month=payload.month,
        weekdays_generated=res.weekdays_generated,
        assignments_created=res.assignments_created,
        assignments_preserved=res.assignments_preserved,
        per_person_distributor=res.per_person_distributor,
        per_person_lunch=res.per_person_lunch,
        warnings=res.warnings,
    )


@router.post("", response_model=DailyDutyOut, status_code=201)
def create_duty(
    payload: DailyDutyCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_super_admin),
):
    """Super admin elle bir atama ekler (v0.8.3: gün+tür başına 2 seat'e kadar).

    İki kuralı zorlar:
      - Aynı (day, duty_type) için max 2 kişi.
      - Aynı kişi aynı (day, duty_type)'a 2 kez atanamaz.
    """
    if not db.query(Personnel).filter(Personnel.id == payload.personnel_id).first():
        raise HTTPException(404, detail="Personel bulunamadı.")

    existing = (
        db.query(DailyDuty)
        .filter(DailyDuty.day == payload.day,
                DailyDuty.duty_type == payload.duty_type)
        .all()
    )
    if any(e.personnel_id == payload.personnel_id for e in existing):
        raise HTTPException(
            409,
            detail="Bu kişi bu gün için aynı göreve zaten atanmış.",
        )
    if len(existing) >= 2:
        raise HTTPException(
            409,
            detail=(
                "Bu gün için bu görev türünde 2 seat zaten dolu. "
                "Önce mevcut bir atamayı silin veya PATCH ile değiştirin."
            ),
        )

    d = DailyDuty(
        day=payload.day,
        duty_type=payload.duty_type,
        personnel_id=payload.personnel_id,
        note=payload.note,
        modified_by_user_id=current.id,  # manual lock
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    audit(db, current, "daily_duty.created_manual", "daily_duty", d.id, {})
    return _to_out(d)


@router.patch("/{duty_id}", response_model=DailyDutyOut)
def update_duty(
    duty_id: int,
    payload: DailyDutyUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_super_admin),
):
    d = (
        db.query(DailyDuty).options(joinedload(DailyDuty.personnel))
        .filter(DailyDuty.id == duty_id).first()
    )
    if not d:
        raise HTTPException(404, detail="Atama bulunamadı.")
    data = payload.model_dump(exclude_unset=True)
    if "personnel_id" in data:
        if not db.query(Personnel).filter(Personnel.id == data["personnel_id"]).first():
            raise HTTPException(404, detail="Personel bulunamadı.")
    for k, v in data.items():
        setattr(d, k, v)
    d.modified_by_user_id = current.id
    db.commit()
    db.refresh(d)
    audit(db, current, "daily_duty.updated", "daily_duty", d.id, data)
    return _to_out(d)


@router.delete("/{duty_id}", status_code=204)
def delete_duty(
    duty_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_super_admin),
):
    d = db.query(DailyDuty).filter(DailyDuty.id == duty_id).first()
    if not d:
        raise HTTPException(404, detail="Atama bulunamadı.")
    db.delete(d)
    db.commit()
    audit(db, current, "daily_duty.deleted", "daily_duty", duty_id, {})
