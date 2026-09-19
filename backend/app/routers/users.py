"""Kullanıcı yönetimi (v0.9.11 sıkılaştırılmış RBAC).

Yetki modeli:
* Standard kullanıcı:
    - Sadece kendi profilini görebilir (list endpoint kendi kaydını döner)
    - Sadece kendi parolasını değiştirebilir (email/full_name/role/is_active değil)
    - Kullanıcı silemez / oluşturamaz
* Super Admin:
    - Tüm kullanıcıları listeler
    - Herkesi düzenler + rol atar (super_admin dahil)
    - Kullanıcı oluşturur
    - Pasifleştirir (soft-delete, is_active=False)
    - Kalıcı olarak siler (hard-delete, v0.9.11 yeni)

Koruma kuralları:
- Son aktif super_admin pasifleştirilemez / silinemez / rolü düşürülemez
- Bir kullanıcı kendi hesabını silemez / pasifleştiremez
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import hash_password, require_authenticated, require_super_admin
from ..database import get_db
from ..models import (
    Entry, Incident, Personnel, PersonnelGroup, PersonnelLocation,
    Role, User,
)
from ..schemas import UserCreate, UserOut, UserUpdate
from ..services import audit

router = APIRouter(prefix="/users", tags=["users"])


def _first_name(full_name: str) -> str:
    """v0.9.12: Kullanıcı full_name'inin ilk kelimesini döner.
    Örn: 'Doğukan Karadağ' → 'Doğukan'. Personnel.full_name için kullanılır."""
    return (full_name or "").strip().split(" ")[0] if (full_name or "").strip() else ""


def _upsert_personnel_for_user(
    db: Session,
    user: User,
    location: Optional[PersonnelLocation] = None,
) -> None:
    """v0.9.12+v0.9.13: Standard rolündeki bir user için Personnel oluştur/aktifleştir.

    - super_admin user'lar Personnel'e otomatik eklenmez (yönetici hesapları)
    - is_active=False user'lar Personnel'e eklenmez
    - Aynı first_name'li Personnel varsa dokunulmaz — sadece is_active=True yapılır
    - Yoksa yeni Personnel yaratılır. location parametresi ile İstanbul/Ankara
      atanır (v0.9.13). Varsayılan: İstanbul.
    """
    if user.role == Role.super_admin or not user.is_active:
        return
    fname = _first_name(user.full_name)
    if not fname:
        return
    existing = db.query(Personnel).filter(Personnel.full_name == fname).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
        return
    # v0.9.13: kullanıcı seçtiği lokasyon (İstanbul veya Ankara)
    loc = location or PersonnelLocation.istanbul
    grp = PersonnelGroup.ankara if loc == PersonnelLocation.ankara else PersonnelGroup.istanbul
    db.add(Personnel(
        full_name=fname,
        location=loc,
        group=grp,
        is_oncall_only=False,
        is_fixed_a=False,
        is_active=True,
    ))


def _deactivate_personnel_for_user(db: Session, user: User) -> None:
    """v0.9.12: User silindiğinde/pasifleştirildiğinde ilgili Personnel'i pasifleştir.

    Aynı first_name'li başka aktif standard user varsa Personnel'e dokunulmaz
    (birden fazla 'Ahmet' varsa hepsi silinene kadar Personnel aktif kalır).
    """
    fname = _first_name(user.full_name)
    if not fname:
        return
    other = (
        db.query(User)
        .filter(User.id != user.id)
        .filter(User.is_active.is_(True))
        .filter(User.role != Role.super_admin)
        .all()
    )
    for o in other:
        if _first_name(o.full_name) == fname:
            return  # Başka aktif user var, Personnel'i pasifleştirme
    existing = db.query(Personnel).filter(Personnel.full_name == fname).first()
    if existing and existing.is_active:
        existing.is_active = False


def _ensure_super_admin_for_role_change(current: User, target_role: Role | None) -> None:
    """super_admin'e atamayı (yeni veya update) sadece super_admin yapabilir."""
    if target_role == Role.super_admin and current.role != Role.super_admin:
        raise HTTPException(
            status_code=403,
            detail="Super Admin rolünü yalnızca başka bir Super Admin atayabilir.",
        )


def _guard_last_super_admin(user: User, db: Session) -> None:
    """Sistemde tek aktif super_admin ise, o kullanıcıyı düşürme/silmeyi engelle."""
    if user.role != Role.super_admin or not user.is_active:
        return
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
                "Bu sistemdeki tek aktif Super Admin; bu işlemden önce "
                "başka bir Super Admin atayın."
            ),
        )


@router.get("", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db),
               current: User = Depends(require_authenticated)):
    """v0.9.11: Standard sadece kendini görür; Super Admin herkesi görür."""
    if current.role == Role.super_admin:
        return db.query(User).order_by(User.id.asc()).all()
    # Standard user — yalnızca kendi kaydı
    return [current]


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db),
                current: User = Depends(require_super_admin)):
    """v0.9.11: Sadece Super Admin yeni kullanıcı oluşturabilir."""
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

    # v0.9.15: Audit'i Personnel upsert'ten ÖNCE çağır. Personnel upsert
    # rollback yaparsa session state bozulup audit sonradan crash edebiliyordu
    # (beyaz sayfa root cause). Şimdi audit önce yazılır.
    audit(db, current, "user.created", "user", user.id,
          {"email": user.email, "role": user.role.value,
           "personnel_location": payload.personnel_location.value if payload.personnel_location else None})

    # v0.9.12+v0.9.13: Personnel'e otomatik ekle (aylık vardiya + dağıtıcı
    # listelerine dahil). Lokasyon UserCreate.personnel_location'dan alınır.
    # Hata olsa bile response başarılı — sadece log'a düşer, kullanıcı Personel
    # Yönet'ten elle ekleyebilir.
    try:
        _upsert_personnel_for_user(db, user, location=payload.personnel_location)
        db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Personnel upsert failed for user %s (user created OK)", user.id,
        )
        db.rollback()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db),
                current: User = Depends(require_authenticated)):
    """v0.9.11 yetki kuralları:
    - Standard kullanıcı: yalnızca kendi ID'sini düzenleyebilir ve
      sadece kendi parolasını değiştirebilir (diğer alanlar 403).
    - Super Admin: herkesi düzenler, tüm alanlarda değişiklik yapar.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    is_self = current.id == user.id
    is_super = current.role == Role.super_admin

    data = payload.model_dump(exclude_unset=True)

    # v0.9.11: Standard user yalnızca kendi hesabında değişiklik yapabilir.
    if not is_super and not is_self:
        raise HTTPException(
            status_code=403,
            detail="Yalnızca kendi hesabınızı düzenleyebilirsiniz.",
        )

    # v0.9.11: Standard user (kendi hesabında bile) yalnızca password
    # alanını değiştirebilir. email/full_name/role/is_active değiştiremez.
    if not is_super:
        allowed_fields = {"password"}
        disallowed = set(data.keys()) - allowed_fields
        if disallowed:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Bu alan(lar)ı değiştirme yetkiniz yok: "
                    + ", ".join(sorted(disallowed))
                ),
            )

    # Rol değişikliği guard'ı.
    new_role = data.get("role")
    if new_role is not None:
        _ensure_super_admin_for_role_change(current, new_role)
        # Bir super_admin kendi rolünü düşüremez eğer sistemde başka super_admin yoksa.
        if (
            is_self
            and user.role == Role.super_admin
            and new_role != Role.super_admin
        ):
            _guard_last_super_admin(user, db)

    # v0.9.12: full_name veya is_active değişikliği Personnel'i etkileyebilir.
    old_first = _first_name(user.full_name)
    old_active = user.is_active
    old_role = user.role

    if "password" in data and data["password"]:
        user.hashed_password = hash_password(data.pop("password"))
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)

    # v0.9.12: Personnel senkron
    try:
        new_first = _first_name(user.full_name)
        # Eski adla eski aktif ise ve isim değiştiyse eskiyi pasifleştir
        if old_first and old_first != new_first:
            fake_old = User(  # noqa: silme için isim eşleştirici
                id=user.id, full_name=old_first, is_active=True, role=old_role,
            )
            _deactivate_personnel_for_user(db, fake_old)
        # Aktifse yeni Personnel'i oluştur/aktifleştir
        if user.is_active and user.role != Role.super_admin:
            _upsert_personnel_for_user(db, user)
        # Pasifleşti veya super_admin'e yükseldi
        if (old_active and not user.is_active) or (
            old_role != Role.super_admin and user.role == Role.super_admin
        ):
            _deactivate_personnel_for_user(db, user)
        db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Personnel sync failed for user %s (update OK)", user.id,
        )
        db.rollback()

    audit(db, current, "user.updated", "user", user.id,
          {k: (v if k != "password" else "<hidden>") for k, v in data.items()})
    return user


@router.delete("/{user_id}", status_code=204)
def deactivate_user(user_id: int, db: Session = Depends(get_db),
                    current: User = Depends(require_super_admin)):
    """v0.9.11: Soft-delete (deactivate) — SADECE Super Admin."""
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="Kendinizi pasifleştiremezsiniz.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _guard_last_super_admin(user, db)
    user.is_active = False
    db.commit()
    # v0.9.12: Personnel'i de pasifleştir → aylık vardiya + dağıtıcıdan otomatik çıkar
    try:
        _deactivate_personnel_for_user(db, user)
        db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Personnel deactivate failed for user %s", user.id,
        )
        db.rollback()
    audit(db, current, "user.deactivated", "user", user.id, {})
    return None


@router.delete("/{user_id}/hard", status_code=204)
def hard_delete_user(user_id: int, db: Session = Depends(get_db),
                     current: User = Depends(require_super_admin)):
    """v0.9.11: HARD-DELETE — kullanıcıyı kalıcı olarak siler.

    Yalnızca Super Admin. Kendini silemez. Son aktif super_admin silinemez.
    Kullanıcının açtığı Entry / Incident varsa silme reddedilir (veri
    bütünlüğü) — bu durumda 'Pasifleştir' kullanılmalı. Denetim izi için
    audit log yazılır.
    """
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="Kendinizi silemezsiniz.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _guard_last_super_admin(user, db)

    # Referans kontrolü — Entry.author_id ve Incident.opened_by_id NOT NULL.
    # Bu kullanıcının kaydı varsa silme fail eder, kullanıcı verisi kaybolur.
    # Bu yüzden önce reddediyoruz; kullanıcı pasifleştirmeyi tercih edebilir.
    entry_count = db.query(Entry).filter(Entry.author_id == user.id).count()
    inc_count = db.query(Incident).filter(Incident.opened_by_id == user.id).count()
    if entry_count or inc_count:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Bu kullanıcının {entry_count} vardiya girişi ve {inc_count} "
                "olay kaydı var. Kalıcı silmek veri bütünlüğünü bozar — "
                "'Pasifleştir' seçeneğini kullanın (kayıtlar korunur, "
                "kullanıcı giriş yapamaz)."
            ),
        )

    # v0.9.12: Personnel'i önce pasifleştir → aylık vardiya + dağıtıcıdan otomatik çıkar
    try:
        _deactivate_personnel_for_user(db, user)
        db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Personnel deactivate failed for user %s (continuing hard-delete)", user.id,
        )
        db.rollback()

    # Audit önce yazılmalı — silme sonrası user.id kaybolur.
    audit(db, current, "user.deleted", "user", user.id,
          {"email": user.email, "role": user.role.value})
    db.delete(user)
    db.commit()
    return None
