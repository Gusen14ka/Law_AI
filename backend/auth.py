import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext

from models import User, UserRole
from database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
SESSION_EXPIRE_HOURS = int(os.getenv("SESSION_EXPIRE_HOURS", "24"))

# In-memory session store (replace with Redis in production)
_sessions: dict[str, dict] = {}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_session(user_id: int, role: str) -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "user_id": user_id,
        "role": role,
        "expires": datetime.utcnow() + timedelta(hours=SESSION_EXPIRE_HOURS)
    }
    return token


def destroy_session(token: str):
    _sessions.pop(token, None)


def get_session_data(token: str) -> Optional[dict]:
    data = _sessions.get(token)
    if not data:
        return None
    if datetime.utcnow() > data["expires"]:
        _sessions.pop(token, None)
        return None
    return data


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Не авторизован")

    session_data = get_session_data(token)
    if not session_data:
        raise HTTPException(status_code=401, detail="Сессия истекла")

    result = await db.execute(select(User).where(User.id == session_data["user_id"]))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    return user


def require_role(*roles: UserRole):
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return current_user
    return checker


require_admin = require_role(UserRole.admin)
require_lawyer = require_role(UserRole.admin, UserRole.lawyer)
require_any = require_role(UserRole.admin, UserRole.lawyer, UserRole.user)
