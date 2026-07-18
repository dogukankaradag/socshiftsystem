"""MPLS Ekipleri CRUD (v0.8.14).

DDoS Taşıma girişlerinde seçilebilir MPLS ekipleri. Her ekibin mail adresi
manuel olarak sisteme girilir; taşıma tarihine 30 dk kala (Entry.occurs_at)
otomatik hatırlatma bu mail adresine gönderilir.

Standart kullanıcılar okuma + oluşturma yetkisi; super_admin silme yetkisi.
"""
from __future__ import annotations
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import require_authenticated, require_super_admin
from ..database import get_db
from ..models import MplsTeam, User
from ..schemas import MplsTeamCreate, MplsTeamOut, MplsTeamUpdate
from ..services import audit


router = APIRouter(prefix="/mpls-teams", tags=["mpls-teams"])


@router.get("", response_model=List[MplsTeamOut])
def list_teams(
    only_active: bool = Query(True, description="False → pasifleri de dahil et"),
    db: Session = Depends(get_db),
    _=Depends(require_authenticated),
):
    q = db.query(MplsTeam)
    if only_active:
        q = q.filter(MplsTeam.is_active.is_(True))
    return q.order_by(MplsTeam.name.asc()).all()


@router.post("", response_model=MplsTeamOut, status_code=201)
def create_team(
    payload: MplsTeamCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_authenticated),
):
    if db.query(MplsTeam).filter(MplsTeam.name == payload.name).first():
        raise HTTPException(409, detail="Aynı isimde MPLS ekibi zaten var.")
    team = MplsTeam(
        name=payload.name.strip(),
        email=payload.email,
        notes=payload.notes,
        is_active=payload.is_active,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    audit(db, current, "mpls_team.created", "mpls_team", team.id,
          {"name": team.name, "email": team.email})
    return team


@router.patch("/{team_id}", response_model=MplsTeamOut)
def update_team(
    team_id: int,
    payload: MplsTeamUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_authenticated),
):
    team = db.query(MplsTeam).filter(MplsTeam.id == team_id).first()
    if not team:
        raise HTTPException(404, detail="MPLS ekibi bulunamadı.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(team, k, v)
    db.commit()
    db.refresh(team)
    audit(db, current, "mpls_team.updated", "mpls_team", team.id, {})
    return team


@router.delete("/{team_id}", status_code=204)
def delete_team(
    team_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_super_admin),
):
    """Silme yalnızca super_admin. Referans veren Entry varsa soft-delete
    (is_active=False), yoksa hard delete."""
    team = db.query(MplsTeam).filter(MplsTeam.id == team_id).first()
    if not team:
        raise HTTPException(404, detail="MPLS ekibi bulunamadı.")
    # Referans var mı? (Entry.mpls_team_id → mpls_teams.id)
    from ..models import Entry
    has_refs = db.query(Entry).filter(Entry.mpls_team_id == team.id).first() is not None
    if has_refs:
        team.is_active = False
        db.commit()
        audit(db, current, "mpls_team.deactivated", "mpls_team", team.id, {})
    else:
        db.delete(team)
        db.commit()
        audit(db, current, "mpls_team.deleted", "mpls_team", team_id, {})
