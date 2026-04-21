"""Mailing list configuration (admin)."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import MailingList
from ..schemas import MailingListCreate, MailingListOut

router = APIRouter(prefix="/mailing-lists", tags=["mailing-lists"])


@router.get("", response_model=List[MailingListOut])
def list_lists(db: Session = Depends(get_db), _=Depends(require_admin)):
    return db.query(MailingList).order_by(MailingList.id.asc()).all()


@router.post("", response_model=MailingListOut, status_code=201)
def create_list(payload: MailingListCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(MailingList).filter(MailingList.name == payload.name).first():
        raise HTTPException(status_code=409, detail="Name already exists")
    if payload.is_default:
        # ensure single default
        db.query(MailingList).filter(MailingList.is_default.is_(True)).update({"is_default": False})
    ml = MailingList(**payload.model_dump())
    db.add(ml)
    db.commit()
    db.refresh(ml)
    return ml


@router.delete("/{list_id}", status_code=204)
def delete_list(list_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    ml = db.query(MailingList).filter(MailingList.id == list_id).first()
    if not ml:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(ml)
    db.commit()
