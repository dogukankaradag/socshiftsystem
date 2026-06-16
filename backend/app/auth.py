"""JWT-based authentication and RBAC dependencies."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import User, Role

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login")


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


def create_access_token(subject: str, extra: Optional[dict] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode = {"sub": subject, "exp": expire}
    if extra:
        to_encode.update(extra)
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        email: str = payload.get("sub")
        if not email:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active:
        raise credentials_exc
    return user


def require_roles(*roles: Role):
    """Dependency factory that allows only specified roles."""
    allowed = set(roles)

    def _checker(current: User = Depends(get_current_user)) -> User:
        if current.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {[r.value for r in allowed]}",
            )
        return current

    return _checker


# --- v0.6.2: 2 rollü dependency'ler ---
# Yeni isimler — kod tabanı zamanla bunlara geçer.
require_authenticated = require_roles(Role.standard, Role.super_admin)
require_super_admin = require_roles(Role.super_admin)

# Eski isimler (operator / supervisor / admin) geriye dönük uyumluluk için
# require_authenticated'a alias. Eski require_admin de aynı şekilde —
# v0.6.2 ile "admin" kavramı standard yetkilerinde eridi. Süper admin'e
# özel davranış gerektiren yeni endpoint'lerde require_super_admin kullanın.
require_admin = require_authenticated
require_supervisor = require_authenticated
require_operator = require_authenticated
