import csv
import io
import random
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session as DBSession, selectinload
from app.api.deps import require_roles, client_ip
from app.core.security import hash_password, random_temporary_password
from app.db.session import get_db
from app.models import (Role, User, Administrator, Teacher, SchoolClass, Student, Subject, Topic, Question,
    QuestionOption, Difficulty, QStatus, QType, Examination, ExaminationQuestion, ExaminationSession, ExamStatus,
    SessionStatus, ExaminationResult, Session as LoginSession, AuditLog, CompetitionRound, RoundType,
    CompetitionParticipant, ClassScore, Certificate, Announcement, SchoolSetting, Leaderboard)
from app.services.audit import write_audit
from app.core.time import utcnow
from app.services.serializers import class_payload, student_payload, exam_payload, question_admin_payload

router = APIRouter(prefix="/admin", tags=["Administration"])
Admin = Depends(require_roles(Role.ADMIN))

class InputModel(BaseModel):
    pass

class ClassCreate(InputModel):
    name: str = Field(min_length=2, max_length=20)
    category: Literal["JUNIOR", "SENIOR"]

class ClassPatch(InputModel):
    name: str | None = Field(default=None, min_length=2, max_length=20)
    category: Literal["JUNIOR", "SENIOR"] | None = None
    teacherId: str | None = None

class StudentCreate(InputModel):
    studentCode: str = Field(min_length=2, max_length=40)
    fullName: str = Field(min_length=2, max_length=120)
    classId: str
    gender: Literal["M", "F"] | None = None
    password: str | None = Field(default=None, min_length=6, max_length=100)

class StudentPatch(InputModel):
    fullName: str | None = Field(default=None, min_length=2, max_length=120)
    classId: str | None = None
    gender: Literal["M", "F"] | None = None
    active: bool | None = None

class OptionInput(InputModel):
    label: Literal["A", "B", "C", "D"]
    text: str = Field(min_length=1, max_length=1000)
    isCorrect: bool

class QuestionPatch(InputModel):
    text: str | None = Field(default=None, min_length=4, max_length=5000)
    difficulty: Difficulty | None = None
    marks: int | None = Field(default=None, ge=1, le=20)
    seconds: int | None = Field(default=None, ge=1, le=600)
    explanation: str | None = None
    imageUrl: str | None = Field(default=None, max_length=2048)
    status: QStatus | None = None

class QuestionCreate(InputModel):
    text: str = Field(min_length=4, max_length=5000)
    subjectId: str
    classId: str
    topic: str | None = None
    difficulty: Difficulty
    type: QType = QType.MCQ
    marks: int = Field(default=1, ge=1, le=20)
    seconds: int | None = Field(default=None, ge=1, le=600)
    explanation: str | None = None
    imageUrl: str | None = None
    options: list[OptionInput] = Field(min_length=2, max_length=4)

class ExamCreate(InputModel):
    title: str = Field(min_length=3, max_length=160)
    classId: str
    subjectId: str | None = None
    roundId: str | None = None
    durationMin: int = Field(ge=1, le=300)
    startsAt: datetime
    endsAt: datetime
    questionCount: int = Field(ge=1, le=200)
    negativeMarking: bool = False
    shuffleQuestions: bool = True
    shuffleOptions: bool = True

    @field_validator("startsAt", "endsAt")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

class ExamAction(InputModel):
    action: Literal["GO_LIVE", "PAUSE", "RESUME", "CLOSE", "PUBLISH_RESULTS", "CANCEL", "EXTEND"]
    minutes: int | None = Field(default=None, ge=1, le=300)

class TeacherCreate(InputModel):
    loginId: str = Field(min_length=2, max_length=60)
    fullName: str = Field(min_length=2, max_length=160)
    password: str | None = Field(default=None, min_length=8, max_length=100)

class RoundParticipantsInput(InputModel):
    studentIds: list[str] = Field(min_length=1, max_length=500)

class CertificateCreate(InputModel):
    studentId: str
    achievement: str = Field(min_length=2, max_length=240)

class RoundCreate(InputModel):
    name: str = Field(min_length=2, max_length=160)
    type: RoundType
    orderNo: int = Field(ge=1)
    advanceCount: int | None = Field(default=None, ge=1)
    tieBreakers: dict | list | None = None
    classAggregation: Literal["AVG_PERCENT"] = "AVG_PERCENT"


def conflict(message: str):
    raise HTTPException(409, message)


@router.get("/teachers")
def list_teachers(db: DBSession = Depends(get_db), _admin=Admin):
    rows = db.scalars(select(Teacher).options(selectinload(Teacher.user), selectinload(Teacher.classes)).order_by(Teacher.fullName)).all()
    return [{"id": row.id, "userId": row.userId, "fullName": row.fullName, "loginId": row.user.loginId,
             "active": row.user.active, "classes": [{"id": c.id, "name": c.name} for c in row.classes]} for row in rows]

@router.post("/teachers", status_code=201)
def create_teacher(data: TeacherCreate, request: Request, db: DBSession = Depends(get_db), admin=Admin):
    login_id = data.loginId.strip(); full_name = data.fullName.strip()
    if len(login_id) < 2 or len(full_name) < 2: raise HTTPException(400, "Teacher login ID and full name are required")
    if db.scalar(select(User).where(User.loginId == login_id)): conflict("Login ID already exists")
    password = data.password or random_temporary_password()
    user = User(loginId=login_id, passwordHash=hash_password(password), role=Role.TEACHER, mustChangePw=data.password is None)
    db.add(user); db.flush()
    teacher = Teacher(userId=user.id, fullName=full_name); db.add(teacher)
    write_audit(db, "TEACHER_CREATE", {"loginId": login_id}, admin.id, client_ip(request)); db.commit(); db.refresh(teacher)
    return {"id": teacher.id, "loginId": user.loginId, "fullName": teacher.fullName, "password": None if data.password else password}

@router.get("/topics")
def list_topics(subjectId: str | None = None, db: DBSession = Depends(get_db), _admin=Admin):
    stmt = select(Topic).options(selectinload(Topic.subject)).order_by(Topic.name)
    if subjectId: stmt = stmt.where(Topic.subjectId == subjectId)
    return [{"id": row.id, "name": row.name, "subjectId": row.subjectId, "subject": {"id": row.subject.id, "name": row.subject.name}} for row in db.scalars(stmt).all()]

@router.post("/topics", status_code=201)
def create_topic(data: dict, db: DBSession = Depends(get_db), admin=Admin):
    name = str(data.get("name", "")).strip(); subject_id = str(data.get("subjectId", ""))
    if not name or not subject_id: raise HTTPException(400, "Topic name and subject are required")
    if not db.get(Subject, subject_id): raise HTTPException(400, "Subject not found")
    existing = db.scalar(select(Topic).where(Topic.subjectId == subject_id, Topic.name == name))
    if existing: return {"id": existing.id, "name": existing.name, "subjectId": existing.subjectId}
    row = Topic(name=name, subjectId=subject_id); db.add(row); write_audit(db, "TOPIC_CREATE", {"name": name, "subjectId": subject_id}, admin.id); db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name, "subjectId": row.subjectId}

@router.patch("/questions/{question_id}")
def update_question(question_id: str, data: QuestionPatch, request: Request, db: DBSession = Depends(get_db), admin=Admin):
    row = db.get(Question, question_id)
    if not row: raise HTTPException(404, "Question not found")
    changes = data.model_dump(exclude_unset=True)
    for key in ("text", "difficulty", "marks", "status"):
        if key in changes and changes[key] is None: raise HTTPException(400, f"{key} cannot be null")
    if "text" in changes:
        changes["text"] = (changes["text"] or "").strip()
        if len(changes["text"]) < 4: raise HTTPException(400, "Question text is required")
    for key, value in changes.items(): setattr(row, key, value)
    write_audit(db, "QUESTION_UPDATE", {"questionId": question_id, **{k: (v.value if hasattr(v, "value") else v) for k, v in changes.items()}}, admin.id, client_ip(request)); db.commit()
    return {"id": row.id, "status": row.status.value}

@router.get("/rounds/{round_id}/participants")
def list_round_participants(round_id: str, db: DBSession = Depends(get_db), _admin=Admin):
    if not db.get(CompetitionRound, round_id): raise HTTPException(404, "Competition round not found")
    rows = db.scalars(select(CompetitionParticipant).options(selectinload(CompetitionParticipant.student).selectinload(Student.schoolClass)).where(CompetitionParticipant.roundId == round_id).order_by(CompetitionParticipant.studentId)).all()
    return [{"id": row.id, "studentId": row.studentId, "qualified": row.qualified, "student": {"id": row.student.id, "studentCode": row.student.studentCode, "fullName": row.student.fullName, "class": row.student.schoolClass.name}} for row in rows]

@router.post("/rounds/{round_id}/participants", status_code=201)
def add_round_participants(round_id: str, data: RoundParticipantsInput, request: Request, db: DBSession = Depends(get_db), admin=Admin):
    if not db.get(CompetitionRound, round_id): raise HTTPException(404, "Competition round not found")
    added = 0
    for student_id in set(data.studentIds):
        if not db.get(Student, student_id): continue
        existing = db.scalar(select(CompetitionParticipant).where(CompetitionParticipant.roundId == round_id, CompetitionParticipant.studentId == student_id))
        if not existing: db.add(CompetitionParticipant(roundId=round_id, studentId=student_id)); added += 1
    write_audit(db, "ROUND_PARTICIPANTS_ADD", {"roundId": round_id, "added": added}, admin.id, client_ip(request)); db.commit()
    return {"added": added}

@router.patch("/rounds/{round_id}/participants/{student_id}")
def update_round_participant(round_id: str, student_id: str, data: dict, db: DBSession = Depends(get_db), admin=Admin):
    row = db.scalar(select(CompetitionParticipant).where(CompetitionParticipant.roundId == round_id, CompetitionParticipant.studentId == student_id))
    if not row: raise HTTPException(404, "Competition participant not found")
    row.qualified = bool(data.get("qualified")); db.commit()
    return {"roundId": round_id, "studentId": student_id, "qualified": row.qualified}

@router.post("/class-scores/recalculate")
def recalculate_class_scores(data: dict, db: DBSession = Depends(get_db), admin=Admin):
    round_id = data.get("roundId")
    if round_id:
        round_row = db.get(CompetitionRound, round_id)
        if not round_row: raise HTTPException(404, "Competition round not found")
        if round_row.classAggregation != "AVG_PERCENT": raise HTTPException(400, f"Class aggregation {round_row.classAggregation} is not implemented")
    stmt = select(ExaminationResult).join(ExaminationResult.exam).options(selectinload(ExaminationResult.student)).where(ExaminationResult.published.is_(True))
    if round_id:
        stmt = stmt.where(Examination.roundId == round_id)
        participant_ids = db.scalars(select(CompetitionParticipant.studentId).where(CompetitionParticipant.roundId == round_id)).all()
        if participant_ids:
            stmt = stmt.where(ExaminationResult.studentId.in_(participant_ids))
    results = db.scalars(stmt).all()
    grouped: dict[str, dict[str, list[float]]] = {}
    for result in results:
        grouped.setdefault(result.student.classId, {}).setdefault(result.studentId, []).append((result.score / result.total * 100) if result.total else 0.0)
    db.query(ClassScore).filter(ClassScore.roundId == round_id).delete(synchronize_session=False)
    summaries = []
    for class_id, student_scores in grouped.items():
        student_averages = [sum(scores) / len(scores) for scores in student_scores.values()]
        average = sum(student_averages) / len(student_averages) if student_averages else 0.0
        participants = len(student_averages)
        db.add(ClassScore(classId=class_id, roundId=round_id, avgPercent=average, participants=participants, points=average))
        summaries.append({"classId": class_id, "avgPercent": round(average, 2), "participants": participants, "points": round(average, 2)})
    write_audit(db, "CLASS_SCORES_RECALCULATE", {"roundId": round_id, "classes": len(summaries)}, admin.id); db.commit()
    return sorted(summaries, key=lambda row: (-row["points"], row["classId"]))

@router.get("/certificates")
def list_certificates(db: DBSession = Depends(get_db), _admin=Admin):
    rows = db.scalars(select(Certificate).options(selectinload(Certificate.student)).order_by(Certificate.issuedAt.desc())).all()
    return [{"id": row.id, "code": row.code, "studentId": row.studentId, "studentName": row.student.fullName, "studentCode": row.student.studentCode, "achievement": row.achievement, "issuedAt": row.issuedAt} for row in rows]

@router.post("/certificates", status_code=201)
def issue_certificate(data: CertificateCreate, request: Request, db: DBSession = Depends(get_db), admin=Admin):
    student = db.get(Student, data.studentId)
    if not student: raise HTTPException(404, "Student not found")
    code = uuid4().hex[:12].upper()
    row = Certificate(code=code, studentId=data.studentId, achievement=data.achievement)
    db.add(row); write_audit(db, "CERTIFICATE_ISSUE", {"studentId": data.studentId, "code": code}, admin.id, client_ip(request)); db.commit(); db.refresh(row)
    return {"id": row.id, "code": row.code, "studentId": row.studentId, "achievement": row.achievement, "issuedAt": row.issuedAt}

@router.get("/overview")
def overview(db: DBSession = Depends(get_db), _admin=Admin):
    return {
        "students": db.scalar(select(func.count()).select_from(Student)) or 0,
        "classes": db.scalar(select(func.count()).select_from(SchoolClass)) or 0,
        "examinations": db.scalar(select(func.count()).select_from(Examination)) or 0,
        "questions": db.scalar(select(func.count()).select_from(Question)) or 0,
        "activeExaminations": db.scalar(select(func.count()).select_from(Examination).where(Examination.status == ExamStatus.LIVE)) or 0,
        "publishedResults": db.scalar(select(func.count()).select_from(ExaminationResult).where(ExaminationResult.published.is_(True))) or 0,
    }

@router.get("/classes")
def list_classes(db: DBSession = Depends(get_db), _admin=Admin):
    rows = db.scalars(select(SchoolClass).options(selectinload(SchoolClass.teacher), selectinload(SchoolClass.students)).order_by(SchoolClass.name)).all()
    return [class_payload(row, len(row.students)) for row in rows]

@router.post("/classes", status_code=201)
def create_class(data: ClassCreate, request: Request, db: DBSession = Depends(get_db), admin=Admin):
    class_name = data.name.strip()
    if len(class_name) < 2: raise HTTPException(400, "Class name is required")
    if db.scalar(select(SchoolClass).where(SchoolClass.name == class_name)):
        conflict("A class with this name already exists")
    row = SchoolClass(name=class_name, category=data.category)
    db.add(row)
    write_audit(db, "CLASS_CREATE", data.model_dump(), admin.id, client_ip(request))
    db.commit(); db.refresh(row)
    return class_payload(row, 0)

@router.patch("/classes/{class_id}")
def update_class(class_id: str, data: ClassPatch, request: Request, db: DBSession = Depends(get_db), admin=Admin):
    row = db.get(SchoolClass, class_id)
    if not row: raise HTTPException(404, "Class not found")
    values = data.model_dump(exclude_unset=True)
    if "name" in values:
        values["name"] = (values["name"] or "").strip()
        if len(values["name"]) < 2: raise HTTPException(400, "Class name is required")
        if values["name"] != row.name and db.scalar(select(SchoolClass).where(SchoolClass.name == values["name"])):
            conflict("A class with this name already exists")
    if values.get("teacherId") and not db.get(Teacher, values["teacherId"]):
        raise HTTPException(400, "Teacher not found")
    for key, value in values.items(): setattr(row, key, value)
    write_audit(db, "CLASS_UPDATE", {"id": class_id, **values}, admin.id, client_ip(request))
    db.commit(); db.refresh(row)
    return class_payload(row)

@router.delete("/classes/{class_id}")
def delete_class(class_id: str, request: Request, db: DBSession = Depends(get_db), admin=Admin):
    row = db.get(SchoolClass, class_id)
    if not row: raise HTTPException(404, "Class not found")
    if row.students or row.exams: conflict("This class has students or exams. Move or remove them first.")
    db.delete(row); write_audit(db, "CLASS_DELETE", {"id": class_id}, admin.id, client_ip(request)); db.commit()
    return {"ok": True}

@router.get("/students")
def list_students(q: str = "", classId: str = "", sort: Literal["fullName", "studentCode", "class"] = "fullName", dir: Literal["asc", "desc"] = "asc", page: int = 1, db: DBSession = Depends(get_db), _admin=Admin):
    page = max(1, page); page_size = 20
    stmt = select(Student).join(Student.user).join(Student.schoolClass).options(selectinload(Student.user), selectinload(Student.schoolClass))
    if classId: stmt = stmt.where(Student.classId == classId)
    if q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(Student.fullName.ilike(term), Student.studentCode.ilike(term)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order_col = SchoolClass.name if sort == "class" else getattr(Student, sort)
    stmt = stmt.order_by(order_col.desc() if dir == "desc" else order_col.asc()).offset((page - 1) * page_size).limit(page_size)
    rows = db.scalars(stmt).all()
    return {"rows": [{**student_payload(s), "classId": s.classId} for s in rows], "total": total, "page": page, "pageSize": page_size}

@router.post("/students", status_code=201)
def create_student(data: StudentCreate, request: Request, db: DBSession = Depends(get_db), admin=Admin):
    student_code = data.studentCode.strip(); full_name = data.fullName.strip()
    if len(student_code) < 2 or len(full_name) < 2: raise HTTPException(400, "Student ID and full name are required")
    if not db.get(SchoolClass, data.classId): raise HTTPException(400, "Selected class does not exist")
    if db.scalar(select(User).where(User.loginId == student_code)) or db.scalar(select(Student).where(Student.studentCode == student_code)):
        conflict("Student ID already exists")
    password = data.password or random_temporary_password()
    user = User(loginId=student_code, passwordHash=hash_password(password), role=Role.STUDENT, mustChangePw=data.password is None)
    db.add(user); db.flush()
    student = Student(userId=user.id, studentCode=student_code, fullName=full_name, gender=data.gender, classId=data.classId)
    db.add(student); db.flush()
    write_audit(db, "STUDENT_CREATE", {"studentCode": student_code, "classId": data.classId}, admin.id, client_ip(request))
    db.commit()
    return {"id": student.id, "studentCode": student.studentCode, "password": None if data.password else password}

@router.patch("/students/{student_id}")
def update_student(student_id: str, data: StudentPatch, request: Request, db: DBSession = Depends(get_db), admin=Admin):
    row = db.scalar(select(Student).options(selectinload(Student.user)).where(Student.id == student_id))
    if not row: raise HTTPException(404, "Student not found")
    values = data.model_dump(exclude_unset=True)
    active = values.pop("active", None)
    if values.get("classId") and not db.get(SchoolClass, values["classId"]): raise HTTPException(400, "Selected class does not exist")
    if "fullName" in values:
        values["fullName"] = (values["fullName"] or "").strip()
        if len(values["fullName"]) < 2: raise HTTPException(400, "Full name is required")
    for key, value in values.items(): setattr(row, key, value)
    if active is not None:
        row.user.active = active
        if not active:
            db.query(LoginSession).filter(LoginSession.userId == row.userId).delete(synchronize_session=False)
    write_audit(db, "STUDENT_UPDATE", {"id": student_id, **values, "active": active}, admin.id, client_ip(request))
    db.commit()
    return {"id": row.id}

@router.post("/students/{student_id}/reset-password")
def reset_student_password(student_id: str, request: Request, db: DBSession = Depends(get_db), admin=Admin):
    row = db.scalar(select(Student).options(selectinload(Student.user)).where(Student.id == student_id))
    if not row: raise HTTPException(404, "Student not found")
    password = random_temporary_password()
    row.user.passwordHash = hash_password(password); row.user.mustChangePw = True
    db.query(LoginSession).filter(LoginSession.userId == row.userId).delete(synchronize_session=False)
    write_audit(db, "STUDENT_PASSWORD_RESET", {"id": student_id, "studentCode": row.studentCode}, admin.id, client_ip(request))
    db.commit()
    return {"studentCode": row.studentCode, "password": password}

@router.post("/students/import")
def import_students(data: dict, request: Request, db: DBSession = Depends(get_db), admin=Admin):
    csv_text = data.get("csv")
    if not isinstance(csv_text, str) or len(csv_text) > 1_000_000: raise HTTPException(400, "Invalid CSV upload")
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames: raise HTTPException(400, "The file has no header row")
    normalize = lambda value: "".join(ch for ch in (value or "").strip().lower() if ch.isalpha())
    rows = [{normalize(k): (v or "").strip() for k, v in row.items()} for row in reader]
    if not rows: raise HTTPException(400, "The file has no rows")
    if len(rows) > 300: raise HTTPException(400, "Import up to 300 students at a time")
    classes = {c.name.upper(): c.id for c in db.scalars(select(SchoolClass)).all()}
    seen: set[str] = set(); created = []; skipped = []
    for idx, row in enumerate(rows, start=2):
        code, full_name, class_name = row.get("studentcode", ""), row.get("fullname", ""), row.get("class", "")
        gender, supplied_pw = row.get("gender", ""), row.get("password", "")
        reason = None
        if len(code) < 2 or len(code) > 40 or len(full_name) < 2 or len(full_name) > 120 or not class_name:
            reason = "Missing or invalid studentCode, fullName or class"
        elif gender not in ("", "M", "F"):
            reason = "Gender must be M or F"
        elif class_name.upper() not in classes:
            reason = f'Class "{class_name}" does not exist'
        elif code in seen or db.scalar(select(User.id).where(User.loginId == code)):
            reason = "Student ID already exists"
        elif supplied_pw and len(supplied_pw) < 6:
            reason = "Password must contain at least 6 characters"
        if reason:
            skipped.append({"row": idx, "studentCode": code, "reason": reason}); continue
        seen.add(code); password = supplied_pw or random_temporary_password()
        user = User(loginId=code, passwordHash=hash_password(password), role=Role.STUDENT, mustChangePw=not bool(supplied_pw))
        db.add(user); db.flush()
        student = Student(userId=user.id, studentCode=code, fullName=full_name, classId=classes[class_name.upper()], gender=gender or None)
        db.add(student)
        created.append({"studentCode": code, "fullName": full_name, "class": class_name, "password": None if supplied_pw else password})
    write_audit(db, "STUDENT_IMPORT", {"created": len(created), "skipped": len(skipped)}, admin.id, client_ip(request))
    db.commit()
    return {"created": created, "skipped": skipped}

@router.get("/students/export")
def export_students(request: Request, db: DBSession = Depends(get_db), admin=Admin):
    rows = db.scalars(select(Student).join(Student.schoolClass).options(selectinload(Student.schoolClass), selectinload(Student.user)).order_by(SchoolClass.name, Student.fullName)).all()
    out = io.StringIO(); writer = csv.DictWriter(out, fieldnames=["studentCode", "fullName", "class", "gender", "active"]); writer.writeheader()
    safe = lambda value: ("'" + value) if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value
    for row in rows:
        writer.writerow({"studentCode": safe(row.studentCode), "fullName": safe(row.fullName), "class": safe(row.schoolClass.name), "gender": row.gender or "", "active": "yes" if row.user.active else "no"})
    write_audit(db, "STUDENT_EXPORT", {"count": len(rows)}, admin.id, client_ip(request)); db.commit()
    return Response(content=out.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=students.csv"})

@router.get("/subjects")
def list_subjects(db: DBSession = Depends(get_db), _admin=Admin):
    return [{"id": s.id, "name": s.name} for s in db.scalars(select(Subject).order_by(Subject.name)).all()]

@router.post("/subjects", status_code=201)
def create_subject(data: dict, db: DBSession = Depends(get_db), admin=Admin):
    name = str(data.get("name", "")).strip()
    if not 2 <= len(name) <= 160: raise HTTPException(400, "Subject name must contain 2 to 160 characters")
    if db.scalar(select(Subject).where(Subject.name == name)): conflict("Subject already exists")
    row = Subject(name=name); db.add(row); write_audit(db, "SUBJECT_CREATE", {"name": name}, admin.id); db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name}

@router.get("/questions")
def list_questions(status: str | None = None, db: DBSession = Depends(get_db), _admin=Admin):
    stmt = select(Question).options(selectinload(Question.subject), selectinload(Question.topic), selectinload(Question.options)).order_by(Question.id.desc())
    if status in ("APPROVED", "DRAFT"): stmt = stmt.where(Question.status == QStatus(status))
    return [question_admin_payload(row) for row in db.scalars(stmt).all()]

QUESTION_IMPORT_COLUMNS = [
    "question_number", "class", "subject", "question_type", "question",
    "option_a", "option_b", "option_c", "option_d", "correct_answer",
    "difficulty", "status", "marks",
]


def _csv_question_preview(db: DBSession, raw: bytes, target_class_id: str | None = None,
                          target_subject_id: str | None = None, status_override: str | None = None,
                          selected_rows: set[int] | None = None):
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(400, "CSV file exceeds the 5 MB size limit")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV file must be UTF-8 encoded")
    if "\x00" in text:
        raise HTTPException(400, "Malformed CSV file")

    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames:
        raise HTTPException(400, "The CSV file has no header row")
    fieldnames = [name.strip().lower() for name in reader.fieldnames]
    if len(fieldnames) != len(set(fieldnames)):
        raise HTTPException(400, "CSV contains duplicate column names")
    missing = [name for name in QUESTION_IMPORT_COLUMNS if name not in fieldnames]
    if missing:
        raise HTTPException(400, f"Missing required columns: {', '.join(missing)}")

    def class_key(value: str) -> str:
        return "".join(character for character in value.upper() if character.isalnum())

    classes = {class_key(row.name): row for row in db.scalars(select(SchoolClass)).all()}
    subjects = {row.name.strip().upper(): row for row in db.scalars(select(Subject)).all()}
    target_class = db.get(SchoolClass, target_class_id) if target_class_id else None
    target_subject = db.get(Subject, target_subject_id) if target_subject_id else None
    if target_class_id and not target_class:
        raise HTTPException(400, "Target class not found")
    if target_subject_id and not target_subject:
        raise HTTPException(400, "Target subject not found")

    existing = set()
    for question in db.scalars(select(Question).options(selectinload(Question.options), selectinload(Question.subject))).all():
        option_text = "|".join(sorted((option.text or "").strip().upper() for option in question.options))
        existing.add((question.classId, question.subjectId, question.text.strip().upper(), option_text))

    preview = []
    seen = set()
    valid_count = duplicate_count = 0
    reader.fieldnames = fieldnames
    for offset, source in enumerate(reader, start=2):
        row = {str(key).strip().lower(): (value or "").strip() for key, value in source.items() if key is not None}
        reasons = []
        school_class = target_class
        subject = target_subject

        if not row.get("question_number"):
            reasons.append("question_number is required")
        if not school_class:
            class_name = row.get("class", "")
            school_class = classes.get(class_key(class_name)) if class_name else None
            if not school_class:
                reasons.append(f'Class "{class_name}" does not exist')
        if not subject:
            subject_name = row.get("subject", "")
            subject = subjects.get(subject_name.upper()) if subject_name else None
            if not subject:
                reasons.append(f'Subject "{subject_name}" does not exist')

        text = row.get("question", "")
        if len(text) < 4:
            reasons.append("Question text is required")
        question_type = row.get("question_type", "").upper()
        if question_type not in {item.value for item in QType}:
            reasons.append("Unsupported question type")
        difficulty = row.get("difficulty", "").upper()
        if difficulty not in {item.value for item in Difficulty}:
            reasons.append("Difficulty must be EASY, MEDIUM, HARD, or EXPERT")
        csv_status = status_override.upper() if status_override else row.get("status", "").upper()
        if csv_status not in {item.value for item in QStatus}:
            reasons.append("Status must be DRAFT or APPROVED")

        try:
            marks = int(row.get("marks", ""))
            if marks <= 0 or marks > 20:
                reasons.append("Marks must be a positive number no greater than 20")
        except (TypeError, ValueError):
            marks = 0
            reasons.append("Marks must be a valid positive number")

        options = [
            {"label": "A", "text": row.get("option_a", "")},
            {"label": "B", "text": row.get("option_b", "")},
            {"label": "C", "text": row.get("option_c", "")},
            {"label": "D", "text": row.get("option_d", "")},
        ]
        correct = row.get("correct_answer", "").upper()
        if question_type == "MCQ":
            missing_options = [option["label"] for option in options if not option["text"]]
            if missing_options:
                reasons.append(f'Missing MCQ options: {", ".join(missing_options)}')
            if correct not in {"A", "B", "C", "D"}:
                reasons.append("Correct answer must be A, B, C, or D")
        elif correct not in ("", "A", "B", "C", "D"):
            reasons.append("Correct answer must be A, B, C, or D")

        duplicate = False
        if school_class and subject and text:
            key = (
                school_class.id, subject.id, text.upper(),
                "|".join(sorted(option["text"].strip().upper() for option in options)),
            )
            duplicate = key in existing or key in seen
            if duplicate:
                duplicate_count += 1
            else:
                seen.add(key)

        valid = not reasons
        if valid:
            valid_count += 1
        preview.append({
            "row": offset,
            "questionNumber": row.get("question_number", ""),
            "classId": school_class.id if school_class else None,
            "className": school_class.name if school_class else row.get("class", ""),
            "subjectId": subject.id if subject else None,
            "subjectName": subject.name if subject else row.get("subject", ""),
            "question": text,
            "questionType": question_type,
            "options": options,
            "correctAnswer": correct,
            "difficulty": difficulty,
            "status": csv_status,
            "marks": marks,
            "valid": valid,
            "duplicate": duplicate,
            "selected": selected_rows is None or offset in selected_rows,
            "reasons": reasons,
        })

    if len(preview) > 300:
        raise HTTPException(400, "Import up to 300 questions at a time")
    ready = sum(1 for row in preview if row["valid"] and not row["duplicate"] and row["selected"])
    return {
        "total": len(preview),
        "valid": valid_count,
        "invalid": len(preview) - valid_count,
        "duplicates": duplicate_count,
        "ready": ready,
        "rows": preview,
    }


@router.post("/questions/import-csv")
def import_questions_csv(
    file: UploadFile = File(...),
    mode: str = Form("preview"),
    targetClassId: str | None = Form(default=None),
    targetSubjectId: str | None = Form(default=None),
    statusOverride: str | None = Form(default=None),
    selectedRows: str = Form(""),
    request: Request = None,
    db: DBSession = Depends(get_db),
    admin=Admin,
):
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise HTTPException(400, "Only .csv files are accepted")
    raw = file.file.read(5 * 1024 * 1024 + 1)
    if not raw:
        raise HTTPException(400, "The CSV file is empty")

    if mode not in {"preview", "import"}:
        raise HTTPException(400, "Invalid import mode")
    selected = set()
    if selectedRows:
        try:
            selected = {int(value) for value in selectedRows.split(",") if value.strip()}
        except ValueError:
            raise HTTPException(400, "Invalid selected row list")

    preview = _csv_question_preview(
        db, raw, targetClassId or None, targetSubjectId or None,
        statusOverride or None, selected if mode == "import" else None,
    )
    if mode == "preview":
        return preview

    imported = []
    skipped = []
    failed = []
    try:
        for row in preview["rows"]:
            if selected and row["row"] not in selected:
                skipped.append({"row": row["row"], "reason": "Not selected"})
                continue
            if not row["valid"]:
                failed.append({"row": row["row"], "reason": "; ".join(row["reasons"])})
                continue
            if row["duplicate"]:
                skipped.append({"row": row["row"], "reason": "Duplicate question"})
                continue
            school_class = db.get(SchoolClass, row["classId"]) if row["classId"] else None
            subject = db.get(Subject, row["subjectId"]) if row["subjectId"] else None
            if not school_class or not subject:
                failed.append({"row": row["row"], "reason": "Class or subject no longer exists"})
                continue
            question = Question(
                text=row["question"],
                type=QType(row["questionType"]),
                subjectId=subject.id,
                classId=school_class.id,
                difficulty=Difficulty(row["difficulty"]),
                marks=row["marks"],
                status=QStatus(row["status"]),
                options=[
                    QuestionOption(
                        label=option["label"],
                        text=option["text"],
                        isCorrect=option["label"] == row["correctAnswer"],
                    )
                    for option in row["options"]
                ],
            )
            db.add(question)
            imported.append({"row": row["row"], "question": row["question"]})

        write_audit(
            db, "QUESTION_CSV_IMPORT",
            {"imported": len(imported), "skipped": len(skipped), "failed": len(failed)},
            admin.id, client_ip(request),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "The question import could not be completed")

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["row", "reason"])
    writer.writeheader()
    for item in skipped:
        if item["reason"] != "Not selected":
            writer.writerow(item)
    for item in failed:
        writer.writerow(item)
    return {
        "successfullyImported": len(imported),
        "skipped": len(skipped),
        "failed": len(failed),
        "duplicates": sum(1 for item in skipped if item["reason"] == "Duplicate question"),
        "errorReportCsv": out.getvalue(),
        "imported": imported,
        "skippedRows": skipped,
        "failedRows": failed,
    }

@router.post("/questions", status_code=201)
def create_question(data: QuestionCreate, request: Request, db: DBSession = Depends(get_db), admin=Admin):
    if len(data.options) != 4 or sum(1 for item in data.options if item.isCorrect) != 1:
        raise HTTPException(400, "Provide exactly four options and exactly one correct answer")
    if len({item.label for item in data.options}) != 4: raise HTTPException(400, "Option labels must be unique")
    if any(not item.text.strip() for item in data.options): raise HTTPException(400, "All option texts are required")
    if not db.get(Subject, data.subjectId): raise HTTPException(400, "Subject not found")
    if not db.get(SchoolClass, data.classId): raise HTTPException(400, "Class not found")
    topic = None
    if data.topic and data.topic.strip():
        topic = db.scalar(select(Topic).where(Topic.subjectId == data.subjectId, Topic.name == data.topic.strip()))
        if not topic:
            topic = Topic(subjectId=data.subjectId, name=data.topic.strip()); db.add(topic); db.flush()
    clean_text = data.text.strip()
    if len(clean_text) < 4: raise HTTPException(400, "Question text is required")
    row = Question(text=clean_text, type=data.type, subjectId=data.subjectId, classId=data.classId,
                   topicId=topic.id if topic else None, difficulty=data.difficulty, marks=data.marks,
                   seconds=data.seconds, explanation=data.explanation, imageUrl=data.imageUrl or None,
                   status=QStatus.APPROVED, options=[QuestionOption(label=item.label, text=item.text.strip(), isCorrect=item.isCorrect) for item in data.options])
    db.add(row); db.flush()
    write_audit(db, "QUESTION_CREATE", {"questionId": row.id, "classId": row.classId, "subjectId": row.subjectId}, admin.id, client_ip(request))
    db.commit(); db.refresh(row)
    return question_admin_payload(row)

@router.get("/examinations")
def list_examinations(db: DBSession = Depends(get_db), _admin=Admin):
    stmt = select(Examination).options(selectinload(Examination.schoolClass), selectinload(Examination.round), selectinload(Examination.questions), selectinload(Examination.sessions), selectinload(Examination.results)).order_by(Examination.startsAt.desc())
    return [exam_payload(row, True) for row in db.scalars(stmt).all()]

@router.post("/examinations", status_code=201)
def create_examination(data: ExamCreate, request: Request, db: DBSession = Depends(get_db), admin=Admin):
    if data.endsAt <= data.startsAt: raise HTTPException(400, "Invalid examination schedule")
    if not db.get(SchoolClass, data.classId): raise HTTPException(400, "Class not found")
    if data.subjectId:
        if not db.get(Subject, data.subjectId): raise HTTPException(400, "Subject not found")
    if data.roundId and not db.get(CompetitionRound, data.roundId): raise HTTPException(400, "Competition round not found")
    pool_query = select(Question).where(Question.classId == data.classId, Question.status == QStatus.APPROVED)
    if data.subjectId:
        pool_query = pool_query.where(Question.subjectId == data.subjectId)
    pool = db.scalars(pool_query).all()
    if len(pool) < data.questionCount:
        raise HTTPException(400, f"Only {len(pool)} approved questions exist for this class. Add more questions.")
    random.SystemRandom().shuffle(pool)
    chosen = pool[:data.questionCount]
    exam_title = data.title.strip()
    if len(exam_title) < 3: raise HTTPException(400, "Examination title is required")
    row = Examination(title=exam_title, classId=data.classId, subjectId=data.subjectId, roundId=data.roundId,
        durationMin=data.durationMin, startsAt=data.startsAt, endsAt=data.endsAt,
        status=ExamStatus.SCHEDULED, negativeMarking=data.negativeMarking,
        shuffleQuestions=data.shuffleQuestions, shuffleOptions=data.shuffleOptions,
        questions=[ExaminationQuestion(questionId=q.id, orderNo=i + 1) for i, q in enumerate(chosen)])
    db.add(row); db.flush()
    write_audit(db, "EXAM_CREATE", {"examId": row.id, "title": row.title, "classId": row.classId, "questionCount": len(chosen)}, admin.id, client_ip(request))
    db.commit(); db.refresh(row)
    row = db.scalar(select(Examination).options(selectinload(Examination.schoolClass), selectinload(Examination.round)).where(Examination.id == row.id))
    return exam_payload(row)

@router.patch("/examinations/{exam_id}")
def update_examination(exam_id: str, data: ExamAction, request: Request, db: DBSession = Depends(get_db), admin=Admin):
    exam = db.get(Examination, exam_id)
    if not exam: raise HTTPException(404, "Examination not found")
    if data.action == "EXTEND":
        if exam.status not in (ExamStatus.LIVE, ExamStatus.PAUSED):
            raise HTTPException(409, "Only a live or paused examination can be extended")
        if not data.minutes:
            raise HTTPException(400, "Minutes are required")
        extension = timedelta(minutes=data.minutes)
        exam.endsAt = exam.endsAt + extension
        active_sessions = db.scalars(select(ExaminationSession).where(
            ExaminationSession.examId == exam_id,
            ExaminationSession.status == SessionStatus.IN_PROGRESS,
        )).all()
        for active_session in active_sessions:
            active_session.deadlineAt = active_session.deadlineAt + extension
        action = "EXAM_TIME_EXTEND"; detail = {"examId": exam_id, "minutes": data.minutes}
    elif data.action == "PUBLISH_RESULTS":
        exam.resultsPublished = True
        for result in db.scalars(select(ExaminationResult).where(ExaminationResult.examId == exam_id)).all(): result.published = True
        action = "EXAM_RESULTS_PUBLISH"; detail = {"examId": exam_id}
    elif data.action == "PAUSE":
        if exam.status not in (ExamStatus.LIVE, ExamStatus.SCHEDULED): raise HTTPException(409, "Only a scheduled or live examination can be paused")
        exam.status = ExamStatus.PAUSED; exam.pausedAt = utcnow()
        action = "EXAM_STATUS_UPDATE"; detail = {"examId": exam_id, "status": exam.status.value}
    elif data.action == "RESUME":
        if exam.status != ExamStatus.PAUSED or not exam.pausedAt: raise HTTPException(409, "This examination is not paused")
        resumed_at = utcnow(); pause_duration = resumed_at - exam.pausedAt
        exam.endsAt = exam.endsAt + pause_duration
        active_sessions = db.scalars(select(ExaminationSession).where(ExaminationSession.examId == exam_id, ExaminationSession.status == SessionStatus.IN_PROGRESS)).all()
        for active_session in active_sessions:
            if active_session.deadlineAt > exam.pausedAt:
                active_session.deadlineAt = active_session.deadlineAt + pause_duration
                active_session.startedAt = active_session.startedAt + pause_duration
        exam.status = ExamStatus.LIVE; exam.pausedAt = None
        action = "EXAM_STATUS_UPDATE"; detail = {"examId": exam_id, "status": exam.status.value, "pausedSeconds": int(pause_duration.total_seconds())}
    else:
        if data.action == "GO_LIVE" and exam.status == ExamStatus.PAUSED:
            raise HTTPException(409, "Use RESUME to continue a paused examination")
        status_map = {"GO_LIVE": ExamStatus.LIVE, "CLOSE": ExamStatus.CLOSED, "CANCEL": ExamStatus.CANCELLED}
        if data.action == "GO_LIVE":
            if exam.status not in (ExamStatus.DRAFT, ExamStatus.SCHEDULED):
                raise HTTPException(409, "This examination cannot be started")
            if not exam.questions:
                raise HTTPException(409, "The examination has no questions")
            now = utcnow()
            exam.actualStartedAt = now
            exam.endsAt = now + timedelta(minutes=exam.durationMin)
        exam.status = status_map[data.action]
        if data.action in ("CLOSE", "CANCEL"): exam.pausedAt = None
        if data.action == "CLOSE":
            exam.endsAt = utcnow()
            for active_session in db.scalars(select(ExaminationSession).where(
                ExaminationSession.examId == exam_id,
                ExaminationSession.status == SessionStatus.IN_PROGRESS,
            )).all():
                from app.api.v1.endpoints.student import _submit_session
                _submit_session(db, active_session)
        action = "EXAM_STATUS_UPDATE"; detail = {"examId": exam_id, "status": exam.status.value}
    write_audit(db, action, detail, admin.id, client_ip(request)); db.commit()
    return {"ok": True, "status": exam.status.value, "resultsPublished": exam.resultsPublished}

@router.get("/rounds")
def list_rounds(db: DBSession = Depends(get_db), _admin=Admin):
    rows = db.scalars(select(CompetitionRound).order_by(CompetitionRound.orderNo)).all()
    return [{"id": r.id, "name": r.name, "type": r.type.value, "orderNo": r.orderNo, "advanceCount": r.advanceCount, "tieBreakers": r.tieBreakers, "classAggregation": r.classAggregation} for r in rows]

@router.post("/rounds", status_code=201)
def create_round(data: RoundCreate, db: DBSession = Depends(get_db), admin=Admin):
    round_name = data.name.strip()
    if len(round_name) < 2: raise HTTPException(400, "Round name is required")
    if db.scalar(select(CompetitionRound).where(CompetitionRound.orderNo == data.orderNo)): conflict("A round already uses this order number")
    row = CompetitionRound(name=round_name, type=data.type, orderNo=data.orderNo, advanceCount=data.advanceCount,
                           tieBreakers=data.tieBreakers, classAggregation=data.classAggregation)
    db.add(row); db.commit(); db.refresh(row)
    write_audit(db, "ROUND_CREATE", {"roundId": row.id, "name": row.name}, admin.id); db.commit()
    return {"id": row.id, "name": row.name, "type": row.type.value, "orderNo": row.orderNo}

@router.post("/rounds/{round_id}/leaderboard/generate")
def generate_round_leaderboards(round_id: str, db: DBSession = Depends(get_db), admin=Admin):
    if not db.get(CompetitionRound, round_id): raise HTTPException(404, "Competition round not found")
    from app.api.v1.endpoints.student import public_leaderboard
    snapshot = public_leaderboard(round_id, db)
    individual = Leaderboard(roundId=round_id, scope="INDIVIDUAL", data=snapshot["individual"])
    classes = Leaderboard(roundId=round_id, scope="CLASS", data=snapshot["classes"])
    db.add_all([individual, classes])
    write_audit(db, "ROUND_LEADERBOARD_GENERATE", {"roundId": round_id}, admin.id)
    db.commit()
    return {"roundId": round_id, "individualLeaderboardId": individual.id, "classLeaderboardId": classes.id, "generated": True}

@router.get("/leaderboards")
def list_leaderboard_snapshots(roundId: str | None = None, db: DBSession = Depends(get_db), _admin=Admin):
    stmt = select(Leaderboard).options(selectinload(Leaderboard.round)).order_by(Leaderboard.generatedAt.desc())
    if roundId: stmt = stmt.where(Leaderboard.roundId == roundId)
    return [{"id": row.id, "roundId": row.roundId, "roundName": row.round.name, "scope": row.scope, "data": row.data, "generatedAt": row.generatedAt} for row in db.scalars(stmt).all()]

@router.get("/results")
def list_results(examId: str | None = None, db: DBSession = Depends(get_db), _admin=Admin):
    stmt = select(ExaminationResult).options(selectinload(ExaminationResult.student).selectinload(Student.schoolClass), selectinload(ExaminationResult.exam)).order_by(ExaminationResult.score.desc(), ExaminationResult.timeSeconds.asc())
    if examId: stmt = stmt.where(ExaminationResult.examId == examId)
    return [{"id": r.id, "score": r.score, "total": r.total, "correct": r.correct, "incorrect": r.incorrect, "unanswered": r.unanswered, "timeSeconds": r.timeSeconds, "published": r.published, "student": {"id": r.student.id, "fullName": r.student.fullName, "studentCode": r.student.studentCode, "class": {"id": r.student.schoolClass.id, "name": r.student.schoolClass.name}}, "exam": {"id": r.exam.id, "title": r.exam.title}} for r in db.scalars(stmt).all()]

@router.get("/audit-logs")
def audit_logs(limit: int = 100, db: DBSession = Depends(get_db), _admin=Admin):
    limit = min(max(limit, 1), 500)
    rows = db.scalars(select(AuditLog).order_by(AuditLog.createdAt.desc()).limit(limit)).all()
    return [{"id": r.id, "actorId": r.actorId, "action": r.action, "detail": r.detail, "ip": r.ip, "createdAt": r.createdAt} for r in rows]

@router.get("/announcements")
def list_announcements(db: DBSession = Depends(get_db), _admin=Admin):
    return [{"id": a.id, "title": a.title, "body": a.body, "audience": a.audience, "createdAt": a.createdAt} for a in db.scalars(select(Announcement).order_by(Announcement.createdAt.desc())).all()]

@router.post("/announcements", status_code=201)
def create_announcement(data: dict, db: DBSession = Depends(get_db), admin=Admin):
    title, body, audience = str(data.get("title", "")).strip(), str(data.get("body", "")).strip(), str(data.get("audience", "ALL")).strip()
    if not title or not body: raise HTTPException(400, "Title and body are required")
    row = Announcement(title=title[:200], body=body, audience=audience[:40]); db.add(row); write_audit(db, "ANNOUNCEMENT_CREATE", {"title": title}, admin.id); db.commit(); db.refresh(row)
    return {"id": row.id, "title": row.title, "body": row.body, "audience": row.audience, "createdAt": row.createdAt}

@router.get("/school-settings")
def get_school_settings(db: DBSession = Depends(get_db), _admin=Admin):
    row = db.scalar(select(SchoolSetting).order_by(SchoolSetting.id).limit(1))
    if not row: return None
    return {"id": row.id, "schoolName": row.schoolName, "contactEmail": row.contactEmail, "phone": row.phone, "logoUrl": row.logoUrl, "settings": row.settings}

@router.put("/school-settings")
def put_school_settings(data: dict, db: DBSession = Depends(get_db), admin=Admin):
    name = str(data.get("schoolName", "")).strip()
    if not name: raise HTTPException(400, "School name is required")
    row = db.scalar(select(SchoolSetting).order_by(SchoolSetting.id).limit(1))
    if not row: row = SchoolSetting(schoolName=name); db.add(row)
    row.schoolName = name; row.contactEmail = data.get("contactEmail"); row.phone = data.get("phone"); row.logoUrl = data.get("logoUrl"); row.settings = data.get("settings")
    write_audit(db, "SCHOOL_SETTINGS_UPDATE", {"schoolName": name}, admin.id); db.commit(); db.refresh(row)
    return {"id": row.id, "schoolName": row.schoolName, "contactEmail": row.contactEmail, "phone": row.phone, "logoUrl": row.logoUrl, "settings": row.settings}
