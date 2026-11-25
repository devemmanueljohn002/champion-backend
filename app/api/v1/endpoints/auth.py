from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from app.api.deps import get_current_user, client_ip
from app.core.config import settings
from app.core.security import hash_password, hash_session_token, new_session_token, verify_password
from app.db.session import get_db
from app.models import AuditLog, Session, User
from app.core.time import utcnow
from app.services.audit import write_audit

router = APIRouter(prefix="/auth", tags=["Authentication"])

class LoginInput(BaseModel):
    loginId: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)

@router.post("/login")
def login(data: LoginInput, request: Request, response: Response, db: DBSession = Depends(get_db)):
    login_id = data.loginId.strip()
    since = utcnow() - timedelta(minutes=15)
    failures = db.scalars(select(AuditLog).where(AuditLog.action == "LOGIN_FAIL", AuditLog.createdAt >= since).order_by(AuditLog.createdAt.desc())).all()
    fail_count = sum(1 for row in failures if (row.detail or {}).get("loginId") == login_id)
    if fail_count >= 5:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")
    user = db.scalar(select(User).where(User.loginId == login_id))
    if not user or not user.active or not verify_password(data.password, user.passwordHash):
        write_audit(db, "LOGIN_FAIL", {"loginId": login_id}, ip=client_ip(request))
        db.commit()
        raise HTTPException(status_code=401, detail="Wrong ID or password")
    token = new_session_token()
    db.add(Session(id=hash_session_token(token), userId=user.id, expiresAt=utcnow() + timedelta(days=settings.session_days)))
    write_audit(db, "LOGIN", {}, user.id, client_ip(request))
    db.commit()
    response.set_cookie(settings.session_cookie_name, token, max_age=settings.session_days * 86400,
                        httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, path="/")
    return {"role": user.role.value, "mustChangePw": user.mustChangePw}

@router.post("/logout")
def logout(request: Request, response: Response, db: DBSession = Depends(get_db)):
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        row = db.get(Session, hash_session_token(token))
        if row:
            db.delete(row)
            db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/", httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite)
    return {"ok": True}

@router.get("/me")
def me(user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    payload = {"id": user.id, "loginId": user.loginId, "role": user.role.value,
               "active": user.active, "mustChangePw": user.mustChangePw, "createdAt": user.createdAt}
    if user.student:
        payload["student"] = {"id": user.student.id, "studentCode": user.student.studentCode, "fullName": user.student.fullName, "classId": user.student.classId}
    if user.teacher:
        payload["teacher"] = {"id": user.teacher.id, "fullName": user.teacher.fullName}
    if user.admin:
        payload["admin"] = {"id": user.admin.id, "fullName": user.admin.fullName}
    return payload

@router.post("/change-password")
def change_password(data: dict, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    current = str(data.get("currentPassword", ""))
    new = str(data.get("newPassword", ""))
    if len(new) < 8 or len(new) > 200:
        raise HTTPException(400, "New password must contain between 8 and 200 characters")
    if not verify_password(current, user.passwordHash):
        raise HTTPException(400, "Current password is incorrect")
    user.passwordHash = hash_password(new)
    user.mustChangePw = False
    db.commit()
    return {"ok": True}
