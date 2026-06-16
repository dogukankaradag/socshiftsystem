"""Müşteri İrtibat Listesi — CRUD endpoint'leri (v0.6.1).

Entry tablosunda "Arayanlar" türündeki girişler bu listeden autocomplete
edilir. Kurum (CustomerOrg) ile irtibat (CustomerContact) 1-N ilişkisinde:
bir kurumun birden fazla irtibat kişisi olabilir.

Tarihsel veri bütünlüğü için Entry kayıtlarındaki caller_org_name /
caller_contact_name / caller_contact_phone alanları **snapshot** olarak
tutulur — bu router üzerinden silme/güncelleme eski Entry'leri etkilemez.
"""
from __future__ import annotations
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from ..auth import require_authenticated
# v0.6.2: Standart kullanıcılar tüm CRUD'ı yapabilir; super_admin'e özel
# bir kısıt yok. Eski require_admin / require_operator alias'larını burada
# tek isimle birleştiriyoruz.
require_operator = require_authenticated
require_admin = require_authenticated
from ..database import get_db
from ..models import CustomerContact, CustomerOrg, User
from ..schemas import (
    CustomerContactCreate, CustomerContactOut, CustomerContactUpdate,
    CustomerOrgCreate, CustomerOrgOut, CustomerOrgUpdate,
)
from ..services import audit

router = APIRouter(prefix="/customers", tags=["customers"])


# --- Listeleme (tüm kurumlar + irtibatları) ---------------------------------

@router.get("/orgs", response_model=List[CustomerOrgOut])
def list_orgs(
    db: Session = Depends(get_db),
    _=Depends(require_operator),
):
    """Tüm kurumları irtibatlarıyla birlikte döndürür (autocomplete + sayfa)."""
    rows = (
        db.query(CustomerOrg)
        .options(selectinload(CustomerOrg.contacts))
        .order_by(CustomerOrg.name.asc())
        .all()
    )
    return rows


# --- Kurum (CustomerOrg) CRUD ------------------------------------------------

@router.post("/orgs", response_model=CustomerOrgOut, status_code=201)
def create_org(
    payload: CustomerOrgCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_operator),
):
    """Yeni kurum oluştur. İsteğe bağlı olarak ilk irtibat kişisini de ekler."""
    existing = db.query(CustomerOrg).filter(CustomerOrg.name == payload.name).first()
    if existing:
        raise HTTPException(409, detail="Aynı isimde bir kurum zaten var.")

    org = CustomerOrg(name=payload.name.strip(), notes=payload.notes)
    db.add(org)
    db.flush()  # id'yi al

    if payload.initial_contact:
        contact = CustomerContact(
            org_id=org.id,
            name=payload.initial_contact.name.strip(),
            phone=(payload.initial_contact.phone or "").strip() or None,
            notes=payload.initial_contact.notes,
        )
        db.add(contact)

    db.commit()
    db.refresh(org)
    audit(db, current, "customer_org.created", "customer_org", org.id,
          {"name": org.name})
    return org


@router.patch("/orgs/{org_id}", response_model=CustomerOrgOut)
def update_org(
    org_id: int,
    payload: CustomerOrgUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_operator),
):
    org = db.query(CustomerOrg).filter(CustomerOrg.id == org_id).first()
    if not org:
        raise HTTPException(404, detail="Kurum bulunamadı.")

    if payload.name is not None:
        new_name = payload.name.strip()
        if new_name != org.name:
            dup = db.query(CustomerOrg).filter(CustomerOrg.name == new_name).first()
            if dup:
                raise HTTPException(409, detail="Aynı isimde bir kurum zaten var.")
            org.name = new_name
    if payload.notes is not None:
        org.notes = payload.notes
    db.commit()
    db.refresh(org)
    audit(db, current, "customer_org.updated", "customer_org", org.id, {})
    return org


@router.delete("/orgs/{org_id}", status_code=204)
def delete_org(
    org_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
):
    """Kurumu ve tüm irtibatlarını sil (cascade). Sadece admin yetkisi."""
    org = db.query(CustomerOrg).filter(CustomerOrg.id == org_id).first()
    if not org:
        raise HTTPException(404, detail="Kurum bulunamadı.")
    db.delete(org)
    db.commit()
    audit(db, current, "customer_org.deleted", "customer_org", org_id,
          {"name": org.name})


# --- İrtibat (CustomerContact) CRUD -----------------------------------------

@router.post("/orgs/{org_id}/contacts", response_model=CustomerContactOut,
             status_code=201)
def create_contact(
    org_id: int,
    payload: CustomerContactCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_operator),
):
    """Bir kuruma yeni irtibat kişisi ekle."""
    org = db.query(CustomerOrg).filter(CustomerOrg.id == org_id).first()
    if not org:
        raise HTTPException(404, detail="Kurum bulunamadı.")

    contact = CustomerContact(
        org_id=org.id,
        name=payload.name.strip(),
        phone=(payload.phone or "").strip() or None,
        notes=payload.notes,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    audit(db, current, "customer_contact.created", "customer_contact", contact.id,
          {"org_id": org_id, "name": contact.name})
    return contact


@router.patch("/contacts/{contact_id}", response_model=CustomerContactOut)
def update_contact(
    contact_id: int,
    payload: CustomerContactUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_operator),
):
    contact = db.query(CustomerContact).filter(CustomerContact.id == contact_id).first()
    if not contact:
        raise HTTPException(404, detail="İrtibat bulunamadı.")

    if payload.name is not None:
        contact.name = payload.name.strip()
    if payload.phone is not None:
        contact.phone = payload.phone.strip() or None
    if payload.notes is not None:
        contact.notes = payload.notes
    db.commit()
    db.refresh(contact)
    audit(db, current, "customer_contact.updated", "customer_contact", contact.id, {})
    return contact


@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_operator),
):
    contact = db.query(CustomerContact).filter(CustomerContact.id == contact_id).first()
    if not contact:
        raise HTTPException(404, detail="İrtibat bulunamadı.")
    db.delete(contact)
    db.commit()
    audit(db, current, "customer_contact.deleted", "customer_contact", contact_id,
          {"name": contact.name, "org_id": contact.org_id})
