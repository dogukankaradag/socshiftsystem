"""Incident tracking routes."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import require_operator, require_supervisor
from ..database import get_db
from ..models import Entry, Incident, IncidentStatus, Priority, User
from ..schemas import IncidentCreate, IncidentOut, IncidentUpdate
from ..services import audit

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _to_out(db: Session, inc: Incident) -> IncidentOut:
    count = db.query(func.count(Entry.id)).filter(Entry.incident_id == inc.id).scalar() or 0
    out = IncidentOut.model_validate(inc)
    out.entry_count = int(count)
    return out


@router.get("", response_model=List[IncidentOut])
def list_incidents(
    status: Optional[IncidentStatus] = None,
    priority: Optional[Priority] = None,
    assigned_to_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(require_operator),
):
    q = db.query(Incident)
    if status:
        q = q.filter(Incident.status == status)
    if priority:
        q = q.filter(Incident.priority == priority)
    if assigned_to_id is not None:
        q = q.filter(Incident.assigned_to_id == assigned_to_id)
    rows = q.order_by(Incident.opened_at.desc()).offset(offset).limit(limit).all()
    return [_to_out(db, i) for i in rows]


@router.post("", response_model=IncidentOut, status_code=201)
def create_incident(payload: IncidentCreate, db: Session = Depends(get_db),
                    current: User = Depends(require_operator)):
    inc = Incident(
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        assigned_to_id=payload.assigned_to_id,
        opened_by_id=current.id,
        tags=payload.tags,
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)
    audit(db, current, "incident.opened", "incident", inc.id,
          {"priority": inc.priority.value})
    return _to_out(db, inc)


@router.patch("/{incident_id}", response_model=IncidentOut)
def update_incident(incident_id: int, payload: IncidentUpdate,
                    db: Session = Depends(get_db),
                    current: User = Depends(require_operator)):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    data = payload.model_dump(exclude_unset=True)
    # status transition -> resolved_at
    if data.get("status") == IncidentStatus.resolved and inc.status != IncidentStatus.resolved:
        inc.resolved_at = datetime.now(timezone.utc)
    if data.get("status") and data["status"] != IncidentStatus.resolved:
        inc.resolved_at = None
    for k, v in data.items():
        setattr(inc, k, v)
    db.commit()
    db.refresh(inc)
    audit(db, current, "incident.updated", "incident", inc.id, data)
    return _to_out(db, inc)


@router.delete("/{incident_id}", status_code=204)
def delete_incident(incident_id: int, db: Session = Depends(get_db),
                    current: User = Depends(require_supervisor)):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    db.delete(inc)
    db.commit()
    audit(db, current, "incident.deleted", "incident", incident_id)
    return None
