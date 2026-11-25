from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession, selectinload
from app.api.deps import require_roles
from app.db.session import get_db
from app.models import Role, User, Teacher, SchoolClass

router = APIRouter(prefix="/teacher", tags=["Teacher"])
TeacherUser = Depends(require_roles(Role.TEACHER))

@router.get("/dashboard")
def teacher_dashboard(db: DBSession = Depends(get_db), user: User = TeacherUser):
    teacher = db.scalar(select(Teacher).options(selectinload(Teacher.classes).selectinload(SchoolClass.students)).where(Teacher.userId == user.id))
    if not teacher:
        return {"teacher": None, "classes": []}
    return {"teacher": {"id": teacher.id, "fullName": teacher.fullName},
        "classes": [{"id": c.id, "name": c.name, "category": c.category, "studentCount": len(c.students)} for c in teacher.classes]}
