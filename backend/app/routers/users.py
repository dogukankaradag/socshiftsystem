"""Kullanıcı yönetimi (v0.6.2 yeni rol sistemi).

* Standart kullanıcılar: kullanıcı listele/oluştur/düzenle/deactive yapabilir.
* Super Admin: standart + super_admin atama yetkisi.

Super admin **yalnızca super_admin'ler tarafından** atanabilir/değiştirilebilir;
standart kullanıcı kendi rolünü veya başkasının rolünü super_admin'e
yükseltemez. Bir super_admin kendi süper-admin'liğini düşüremez (en az
bir super_admin garantili).
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import hash_password, require_authenticated
from ..database import get_db
from ..models import Role, User
from ..schemas import UserCreate, UserOut, UserUpdate
from ..services import audit

router = APIRouter(prefix="/users", tags=["users"])


def _ensure_super_admin_for_role_change(current: User, target_role: Role | None) -> None:
    """super_admin'e atamayı (yeni veya update) sadece super_admin yapabilir."""
    if target_role == Role.super_admin and current.role != Role.super_admin:
        raise HTTPException(
            status_code=403,
            detail="Super Admin rolünü yalnızca başka bir Super Admin atayabilir.",
        )


@router.get("", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), _=Depends(require_authenticated)):
    return db.query(User).order_by(User.id.asc()).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db),
                current: User = Depends(require_authenticated)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    _ensure_super_admin_for_role_change(current, payload.role)
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit(db, current, "user.created", "user", user.id,
          {"email": user.email, "role": user.role.value})
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db),
                current: User = Depends(require_authenticated)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    data = payload.model_dump(exclude_unset=True)

    # Rol değişikliği guard'ı.
    new_role = data.get("role")
    if new_role is not None:
        _ensure_super_admin_for_role_change(current, new_role)
        # Bir super_admin kendi rolünü düşüremez eğer sistemde başka super_admin yoksa.
        if (
            user.id == current.id
            and user.role == Role.super_admin
            and new_role != Role.super_admin
        ):
            other_super = (
                db.query(User)
                .filter(User.role == Role.super_admin)
                .filter(User.id != user.id)
                .filter(User.is_active.is_(True))
                .first()
            )
            if not other_super:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Sistemde tek aktif Super Admin sizsiniz; rolünüzü "
                        "düşürmeden önce başka birini Super Admin yapın."
                    ),
                )

    if "password" in data and data["password"]:
        user.hashed_password = hash_password(data.pop("password"))
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    audit(db, current, "user.updated", "user", user.id, data)
    return user


@router.delete("/{user_id}", status_code=204)
def deactivate_user(user_id: int, db: Session = Depends(get_db),
                    current: User = Depends(require_authenticated)):
    """Soft-delete: deactivate rather than remove (preserves audit trail)."""
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Son aktif super_admin'i deactivate etme.
    if user.role == Role.super_admin and user.is_active:
        other_super = (
            db.query(User)
            .filter(User.role == Role.super_admin)
            .filter(User.id != user.id)
            .filter(User.is_active.is_(True))
            .first()
        )
        if not other_super:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Bu sistemdeki tek aktif Super Admin; pasifleştirmeden önce "
                    "başka bir Super Admin atayın."
                ),
            )
    user.is_active = False
    db.commit()
    audit(db, current, "user.deactivated", "user", user.id)
    return None
