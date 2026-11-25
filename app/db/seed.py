from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import User, Administrator, SchoolClass, Subject, Role
from app.core.config import settings
from app.core.security import hash_password


def seed():
    if not settings.admin_login or not settings.admin_password:
        raise SystemExit("Set ADMIN_LOGIN and ADMIN_PASSWORD in backend/.env before seeding.")
    if settings.admin_password.lower().startswith("change-me") or len(settings.admin_password) < 12:
        raise SystemExit("ADMIN_PASSWORD must be a real password of at least 12 characters.")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.loginId == settings.admin_login))
        if not user:
            user = User(loginId=settings.admin_login, passwordHash=hash_password(settings.admin_password), role=Role.ADMIN)
            db.add(user); db.flush()
        elif user.role != Role.ADMIN:
            raise SystemExit("ADMIN_LOGIN is already assigned to a non-administrator account. Choose a different login ID.")
        if not db.scalar(select(Administrator).where(Administrator.userId == user.id)):
            db.add(Administrator(userId=user.id, fullName="Administrator"))
        defaults = [("JSS1", "JUNIOR"), ("JSS2", "JUNIOR"), ("JSS3", "JUNIOR"), ("SS1", "SENIOR"), ("SS2", "SENIOR"), ("SS3", "SENIOR")]
        for name, category in defaults:
            if not db.scalar(select(SchoolClass).where(SchoolClass.name == name)):
                db.add(SchoolClass(name=name, category=category))
        for name in ["Mathematics", "ICT / Data Processing"]:
            if not db.scalar(select(Subject).where(Subject.name == name)):
                db.add(Subject(name=name))
        db.commit()
    print("Seed completed: administrator, six classes and two subjects (missing records only).")

if __name__ == "__main__":
    seed()
