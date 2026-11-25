from datetime import datetime
from fastapi import Depends, Request
from sqlalchemy.orm import Session as DBSession
from app.core.config import settings
from app.core.errors import forbidden, unauthorized
from app.core.security import hash_session_token
from app.db.session import get_db
from app.models import Session, User, Role
from app.core.time import utcnow


def get_current_user(request: Request, db: DBSession = Depends(get_db)) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise unauthorized()
    session = db.get(Session, hash_session_token(token))
    now = utcnow()
    if not session or session.expiresAt <= now:
        if session:
            db.delete(session)
            db.commit()
        raise unauthorized()
    user = db.get(User, session.userId)
    if not user or not user.active:
        raise unauthorized()
    return user


def require_roles(*roles: Role):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise forbidden()
        return user
    return dependency


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:80]
    return request.client.host if request.client else None
