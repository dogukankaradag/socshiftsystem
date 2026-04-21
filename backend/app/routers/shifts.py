"""Shift lifecycle routes."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import require_operator, require_supervisor
from ..database import get_db
from ..models import Entry, Shift, ShiftType, User
from ..schemas import ShiftCreate, ShiftOut, ShiftUpdate
from ..services import audit, get_or_create_open_shift

router = APIRouter(prefix="/shifts", tags=["shifts"])


def _with_count(db: Session, shift: Shift) -> ShiftOut:
    count = db.query(func.count(Entry.id)).filter(Entry.shift_id == shift.id).scalar() or 0
    out = ShiftOut.model_validate(shift)
    out.entry_count = int(count)
    return out


@router.get("", response_model=List[ShiftOut])
def list_shifts(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    shift_type: Optional[ShiftType] = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
    _=Depends(require_operator),
):
    q = db.query(Shift)
    if shift_type:
        q = q.filter(Shift.shift_type == shift_type)
    if active_only:
        q = q.filter(Shift.ended_at.is_(None))
    shifts = q.order_by(Shift.started_at.desc()).offset(offset).limit(limit).all()
    return [_with_count(db, s) for s in shifts]


@router.get("/current", response_model=ShiftOut)
def current_shift(db: Session = Depends(get_db), _=Depends(require_operator)):
    shift = get_or_create_open_shift(db)
    return _with_count(db, shift)


@router.post("", response_model=ShiftOut, status_code=201)
def start_shift(payload: ShiftCreate, db: Session = Depends(get_db),
                current: User = Depends(require_supervisor)):
    shift = Shift(
        shift_type=payload.shift_type,
        started_at=payload.started_at or datetime.now(timezone.utc),
        supervisor_id=payload.supervisor_id or current.id,
        notes=payload.notes,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    audit(db, current, "shift.started", "shift", shift.id,
          {"shift_type": shift.shift_type.value})
    return _with_count(db, shift)


@router.patch("/{shift_id}", response_model=ShiftOut)
def update_shift(shift_id: int, payload: ShiftUpdate,
                 db: Session = Depends(get_db),
                 current: User = Depends(require_supervisor)):
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(shift, k, v)
    db.commit()
    db.refresh(shift)
    audit(db, current, "shift.updated", "shift", shift.id, data)
    return _with_count(db, shift)


@router.post("/{shift_id}/end", response_model=ShiftOut)
def end_shift(shift_id: int, db: Session = Depends(get_db),
              current: User = Depends(require_supervisor)):
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    if shift.ended_at:
        raise HTTPException(status_code=400, detail="Shift already ended")
    shift.ended_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(shift)
    audit(db, current, "shift.ended", "shift", shift.id)
    return _with_count(db, shift)
