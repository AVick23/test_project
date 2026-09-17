"""
Authentication: password hashing, JWT, FastAPI dependencies.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from db import get_db
from models import User

logger = logging.getLogger("movie_rec.auth")

# ==============================
# CONFIG
# ==============================
SECRET_KEY = os.getenv(
    "JWT_SECRET",
    "dev-secret-change-me-in-production-please-abc123xyz",
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 7)))  # 7 дней

# ==============================
# PASSWORD HASHING
# ==============================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2-схема для Swagger UI
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    auto_error=False,  # Не падать с 401 если токена нет — пусть decide роут
)


def hash_password(password: str) -> str:
    """Хеширует пароль через bcrypt."""
    if not password:
        raise ValueError("Password cannot be empty")
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Сверяет plain-пароль с хешем."""
    if not plain_password or not hashed_password:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.warning(f"Password verify failed: {e}")
        return False


# ==============================
# JWT
# ==============================
def create_token(
    user_id: int,
    expires_minutes: Optional[int] = None,
    extra_claims: Optional[dict] = None,
) -> str:
    """
    Создаёт JWT для пользователя.
    
    Args:
        user_id: ID пользователя (кладётся в sub)
        expires_minutes: срок жизни в минутах (по умолчанию ACCESS_TOKEN_EXPIRE_MINUTES)
        extra_claims: дополнительные поля в payload
    """
    if expires_minutes is None:
        expires_minutes = ACCESS_TOKEN_EXPIRE_MINUTES

    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[int]:
    """
    Декодирует JWT и возвращает user_id или None.
    
    Не бросает исключения — caller сам решает что делать с None.
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            return None
        return int(sub)
    except JWTError as e:
        logger.debug(f"JWT decode failed: {e}")
        return None
    except (ValueError, TypeError) as e:
        logger.debug(f"JWT parse failed: {e}")
        return None


# ==============================
# FASTAPI DEPENDENCIES
# ==============================
def get_current_user(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme),
) -> Optional[User]:
    """
    Пытается достать текущего юзера из токена.
    Возвращает User или None — роут сам решает, обязательна ли авторизация.
    """
    if not token:
        return None

    user_id = decode_token(token)
    if user_id is None:
        return None

    user = db.query(User).filter(User.id == user_id).first()
    return user


def require_user(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """
    Жёсткая зависимость: если юзера нет — 401.
    Используй для приватных роутов: /interactions, /users/me/*, /recommendations/me.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def register_user(
    db: Session,
    username: str,
    password: str,
    email: Optional[str] = None,
) -> User:
    """
    Создаёт нового пользователя. Бросает HTTPException при конфликтах.
    """
    # Проверка уникальности username
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )

    # Проверка email (если передан)
    if email:
        if db.query(User).filter(User.email == email).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already used",
            )

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"Registered user: {username} (id={user.id})")
    return user


def authenticate_user(
    db: Session,
    username: str,
    password: str,
) -> User:
    """
    Аутентифицирует пользователя. Бросает HTTPException 401 при неверных данных.
    """
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    logger.info(f"Authenticated user: {username} (id={user.id})")
    return user