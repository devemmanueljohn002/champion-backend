from sqlalchemy.orm import Session
from app.models import AuditLog


def write_audit(db: Session, action: str, detail: dict | None = None, actor_id: str | None = None, ip: str | None = None):
    db.add(AuditLog(actorId=actor_id, action=action, detail=detail or {}, ip=ip))
