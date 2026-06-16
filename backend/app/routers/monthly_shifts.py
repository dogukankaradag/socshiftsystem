"""Aylık vardiya çizelgesi endpoint'leri (v0.7.0).

İki ayrı resource:
    /personnel             — Personel master CRUD (super_admin yazma)
    /monthly-shifts        — Aylık atama CRUD + generate (super_admin yazma)

Okuma her authenticated kullanıcıya açık (read-only); yazma yalnızca
super_admin yetkisinde.
"""
from __future__ import annotations
from calendar import monthrange
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from ..auth import require_authenticated, require_super_admin
from ..database import get_db
from ..models import MonthlyShiftAssignment, Personnel, User
from ..monthly_shift_generator import generate_month
from ..schemas import (
    GenerateMonthlyShiftRequest, GenerateMonthlyShiftResult,
    MonthlyShiftAssignmentCreate, MonthlyShiftAssignmentOut,
    MonthlyShiftAssignmentUpdate,
    PersonnelCreate, PersonnelOut, PersonnelUpdate,
)
from ..services import audit


# --- /personnel router ------------------------------------------------------
personnel_router = APIRouter(prefix="/personnel", tags=["personnel"])


@personnel_router.get("", response_model=List[PersonnelOut])
def list_personnel(
    only_active: bool = Query(True, description="True ise sadece aktif personel"),
    db: Session = Depends(get_db),
    _=Depends(require_authenticated),
):
    q = db.query(Personnel)
    if only_active:
        q = q.filter(Personnel.is_active.is_(True))
    return q.order_by(Personnel.full_name.asc()).all()


@personnel_router.post("", response_model=PersonnelOut, status_code=201)
def create_personnel(
    payload: PersonnelCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_super_admin),
):
    if db.query(Personnel).filter(Personnel.full_name == payload.full_name).first():
        raise HTTPException(409, detail="Aynı isimde personel zaten var.")
    p = Personnel(**payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    audit(db, current, "personnel.created", "personnel", p.id, {"name": p.full_name})
    return p


@personnel_router.patch("/{personnel_id}", response_model=PersonnelOut)
def update_personnel(
    personnel_id: int,
    payload: PersonnelUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_super_admin),
):
    p = db.query(Personnel).filter(Personnel.id == personnel_id).first()
    if not p:
        raise HTTPException(404, detail="Personel bulunamadı.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    audit(db, current, "personnel.updated", "personnel", p.id, {})
    return p


@personnel_router.delete("/{personnel_id}", status_code=204)
def delete_personnel(
    personnel_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_super_admin),
):
    p = db.query(Personnel).filter(Personnel.id == personnel_id).first()
    if not p:
        raise HTTPException(404, detail="Personel bulunamadı.")
    # Atama bağlıysa soft delete (is_active=False), yoksa hard delete.
    has_assignments = (
        db.query(MonthlyShiftAssignment)
        .filter(MonthlyShiftAssignment.personnel_id == p.id)
        .first() is not None
    )
    if has_assignments:
        p.is_active = False
        db.commit()
        audit(db, current, "personnel.deactivated", "personnel", p.id, {})
    else:
        db.delete(p)
        db.commit()
        audit(db, current, "personnel.deleted", "personnel", p.id, {})


# --- /monthly-shifts router -------------------------------------------------
router = APIRouter(prefix="/monthly-shifts", tags=["monthly-shifts"])


def _to_out(a: MonthlyShiftAssignment) -> MonthlyShiftAssignmentOut:
    out = MonthlyShiftAssignmentOut.model_validate(a)
    out.personnel_name = a.personnel.full_name if a.personnel else None
    return out


@router.get("", response_model=List[MonthlyShiftAssignmentOut])
def list_assignments(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    _=Depends(require_authenticated),
):
    """Bir ayın tüm vardiya atamalarını döndürür (personnel eager-load)."""
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    rows = (
        db.query(MonthlyShiftAssignment).options(joinedload(MonthlyShiftAssignment.personnel))
        .filter(MonthlyShiftAssignment.day >= first_day)
        .filter(MonthlyShiftAssignment.day <= last_day)
        .order_by(MonthlyShiftAssignment.day.asc(), MonthlyShiftAssignment.slot.asc())
        .all()
    )
    return [_to_out(a) for a in rows]


@router.post("/generate", response_model=GenerateMonthlyShiftResult)
def generate_schedule(
    payload: GenerateMonthlyShiftRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_super_admin),
):
    """Belirtilen ayın çizelgesini otomatik üretir."""
    res = generate_month(db, payload.year, payload.month, payload.overwrite_manual)
    audit(db, current, "monthly_shifts.generated", "monthly_shifts", None,
          {"year": payload.year, "month": payload.month,
           "created": res.assignments_created, "preserved": res.assignments_preserved,
           "overwrite_manual": payload.overwrite_manual})
    return GenerateMonthlyShiftResult(
        year=payload.year,
        month=payload.month,
        days_generated=res.days_generated,
        assignments_created=res.assignments_created,
        assignments_preserved=res.assignments_preserved,
        warnings=res.warnings,
    )


@router.post("", response_model=MonthlyShiftAssignmentOut, status_code=201)
def create_assignment(
    payload: MonthlyShiftAssignmentCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_super_admin),
):
    """Super admin elle bir atama ekler (manuel lock'lu olarak)."""
    if not db.query(Personnel).filter(Personnel.id == payload.personnel_id).first():
        raise HTTPException(404, detail="Personel bulunamadı.")
    # Aynı kişi + aynı gün varsa hata.
    existing = (
        db.query(MonthlyShiftAssignment)
        .filter(MonthlyShiftAssignment.personnel_id == payload.personnel_id)
        .filter(MonthlyShiftAssignment.day == payload.day)
        .first()
    )
    if existing:
        raise HTTPException(
            409, detail="Bu kişi için bu güne zaten bir atama var; PATCH ile güncelleyin.",
        )
    a = MonthlyShiftAssignment(
        personnel_id=payload.personnel_id,
        day=payload.day,
        slot=payload.slot,
        note=payload.note,
        modified_by_user_id=current.id,  # manual lock
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    audit(db, current, "monthly_shift.created_manual", "monthly_shift", a.id, {})
    return _to_out(a)


@router.patch("/{assignment_id}", response_model=MonthlyShiftAssignmentOut)
def update_assignment(
    assignment_id: int,
    payload: MonthlyShiftAssignmentUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_super_admin),
):
    """Super admin bir atamayı düzenler — değişiklik manuel lock olarak işaretlenir."""
    a = (
        db.query(MonthlyShiftAssignment).options(joinedload(MonthlyShiftAssignment.personnel))
        .filter(MonthlyShiftAssignment.id == assignment_id).first()
    )
    if not a:
        raise HTTPException(404, detail="Atama bulunamadı.")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(a, k, v)
    a.modified_by_user_id = current.id  # manual lock — generate bunu korur
    db.commit()
    db.refresh(a)
    audit(db, current, "monthly_shift.updated", "monthly_shift", a.id, data)
    return _to_out(a)


@router.delete("/{assignment_id}", status_code=204)
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_super_admin),
):
    a = db.query(MonthlyShiftAssignment).filter(MonthlyShiftAssignment.id == assignment_id).first()
    if not a:
        raise HTTPException(404, detail="Atama bulunamadı.")
    db.delete(a)
    db.commit()
    audit(db, current, "monthly_shift.deleted", "monthly_shift", assignment_id, {})
