import hashlib
import random
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession, selectinload
from app.api.deps import require_roles
from app.db.session import get_db
from app.core.time import utcnow
from app.models import (Role, User, Student, Examination, ExamStatus, ExaminationQuestion,
    ExaminationSession, SessionStatus, StudentAnswer, Question, QuestionOption,
    ExaminationResult, QType, ClassScore, CompetitionRound, CompetitionParticipant)
from app.services.serializers import exam_payload

router = APIRouter(tags=["Student and Competition"])
StudentUser = Depends(require_roles(Role.STUDENT))

class ExamAction(BaseModel):
    action: str = Field(pattern="^(start|save|submit|visibility)$")
    questionId: str | None = None
    optionId: str | None = None
    flagged: bool | None = None


def _student_for_user(db: DBSession, user: User) -> Student:
    student = db.scalar(select(Student).options(selectinload(Student.schoolClass)).where(Student.userId == user.id))
    if not student:
        raise HTTPException(403, "Student profile is not linked to this account")
    return student


def _deterministic_options(options: list[QuestionOption], seed: str):
    return sorted(options, key=lambda option: hashlib.sha256(f"{seed}:{option.id}".encode()).hexdigest())


def _submit_session(db: DBSession, session: ExaminationSession):
    session = db.scalar(select(ExaminationSession).options(
        selectinload(ExaminationSession.exam).selectinload(Examination.questions).selectinload(ExaminationQuestion.question).selectinload(Question.options),
        selectinload(ExaminationSession.student), selectinload(ExaminationSession.answers)
    ).where(ExaminationSession.id == session.id))
    if not session or session.status != SessionStatus.IN_PROGRESS:
        return session
    question_by_id = {link.questionId: link.question for link in session.exam.questions}
    answer_by_question = {answer.questionId: answer for answer in session.answers}
    score = 0.0; correct = 0; incorrect = 0
    for question_id, answer in answer_by_question.items():
        if not answer.optionId: continue
        question = question_by_id.get(question_id)
        option = next((item for item in question.options if item.id == answer.optionId), None) if question else None
        if option and option.isCorrect:
            correct += 1; score += question.marks
        else:
            incorrect += 1
    if session.exam.negativeMarking:
        score = max(0.0, score - incorrect)
    total = float(sum(link.question.marks for link in session.exam.questions))
    answered_count = sum(1 for answer in session.answers if answer.optionId)
    unanswered = max(0, len(session.exam.questions) - answered_count)
    session.status = SessionStatus.SUBMITTED
    elapsed = max(0, int((utcnow() - session.startedAt).total_seconds()))
    result = db.scalar(select(ExaminationResult).where(ExaminationResult.examId == session.examId, ExaminationResult.studentId == session.studentId))
    if result:
        result.score = score; result.total = total; result.correct = correct; result.incorrect = incorrect
        result.unanswered = unanswered; result.timeSeconds = elapsed
    else:
        db.add(ExaminationResult(examId=session.examId, studentId=session.studentId, score=score, total=total,
            correct=correct, incorrect=incorrect, unanswered=unanswered, timeSeconds=elapsed,
            published=session.exam.resultsPublished))
    db.commit()
    return session

@router.get("/student/dashboard")
def student_dashboard(db: DBSession = Depends(get_db), user: User = StudentUser):
    student = _student_for_user(db, user)
    exams = db.scalars(select(Examination).options(selectinload(Examination.schoolClass), selectinload(Examination.round), selectinload(Examination.questions)).where(
        Examination.classId == student.classId, Examination.status.in_([ExamStatus.LIVE, ExamStatus.SCHEDULED])
    ).order_by(Examination.startsAt)).all()
    results = db.scalars(select(ExaminationResult).options(selectinload(ExaminationResult.exam)).where(
        ExaminationResult.studentId == student.id, ExaminationResult.published.is_(True)
    ).order_by(ExaminationResult.id.desc()).limit(10)).all()
    return {
        "student": {"id": student.id, "studentCode": student.studentCode, "fullName": student.fullName,
                    "class": {"id": student.schoolClass.id, "name": student.schoolClass.name}},
        "exams": [{**exam_payload(exam), "_count": {"questions": len(exam.questions)}} for exam in exams],
        "results": [{"id": r.id, "score": r.score, "total": r.total, "timeSeconds": r.timeSeconds,
                     "exam": {"id": r.exam.id, "title": r.exam.title, "endsAt": r.exam.endsAt}} for r in results],
    }

@router.get("/student/exams/{exam_id}")
def get_student_exam(exam_id: str, db: DBSession = Depends(get_db), user: User = StudentUser):
    student = _student_for_user(db, user)
    exam = db.scalar(select(Examination).options(
        selectinload(Examination.schoolClass), selectinload(Examination.round),
        selectinload(Examination.questions).selectinload(ExaminationQuestion.question).selectinload(Question.options),
        selectinload(Examination.questions).selectinload(ExaminationQuestion.question).selectinload(Question.topic)
    ).where(Examination.id == exam_id))
    if not exam or exam.classId != student.classId:
        raise HTTPException(403, "Examination unavailable")
    session = db.scalar(select(ExaminationSession).options(selectinload(ExaminationSession.answers)).where(
        ExaminationSession.examId == exam.id, ExaminationSession.studentId == student.id))
    now = utcnow()
    if exam.status == ExamStatus.PAUSED:
        return {"exam": exam_payload(exam), "session": ({"startedAt": session.startedAt, "deadlineAt": session.deadlineAt, "status": session.status.value, "tabSwitches": session.tabSwitches} if session else None), "submitted": False, "paused": True, "questions": [], "answers": []}
    if session and session.status == SessionStatus.IN_PROGRESS and (session.deadlineAt <= now or exam.endsAt <= now or exam.status in (ExamStatus.CLOSED, ExamStatus.CANCELLED)):
        session = _submit_session(db, session)
    if session and session.status != SessionStatus.IN_PROGRESS:
        result = db.scalar(select(ExaminationResult).where(ExaminationResult.examId == exam.id, ExaminationResult.studentId == student.id))
        result_payload = {"score": result.score, "total": result.total, "published": result.published} if result and result.published else None
        return {"exam": exam_payload(exam), "session": None, "submitted": True, "result": result_payload}
    if not session:
        # A student who has not started must see instructions, not a false submitted state.
        return {"exam": exam_payload(exam), "session": None, "submitted": False, "questions": [], "answers": []}
    order = session.questionOrder or []
    by_id = {link.questionId: link.question for link in exam.questions}
    public_questions = []
    for question_id in order:
        question = by_id.get(question_id)
        if not question: continue
        options = [{"id": o.id, "label": o.label, "text": o.text} for o in question.options]
        if exam.shuffleOptions:
            options = [{"id": o.id, "label": o.label, "text": o.text} for o in _deterministic_options(question.options, f"{session.id}:{question.id}")]
        public_questions.append({"id": question.id, "text": question.text, "type": question.type.value,
            "imageUrl": question.imageUrl, "topic": question.topic.name if question.topic else None, "marks": question.marks, "options": options})
    return {"exam": exam_payload(exam),
        "session": {"startedAt": session.startedAt, "deadlineAt": session.deadlineAt, "status": session.status.value, "tabSwitches": session.tabSwitches},
        "questions": public_questions,
        "answers": [{"questionId": a.questionId, "optionId": a.optionId, "flagged": a.flagged} for a in session.answers],
        "submitted": False}

@router.post("/student/exams/{exam_id}")
def student_exam_action(exam_id: str, data: ExamAction, db: DBSession = Depends(get_db), user: User = StudentUser):
    student = _student_for_user(db, user)
    exam = db.scalar(select(Examination).options(selectinload(Examination.questions)).where(Examination.id == exam_id))
    if not exam or exam.classId != student.classId:
        raise HTTPException(403, "Examination unavailable")
    now = utcnow()
    session = db.scalar(select(ExaminationSession).where(ExaminationSession.examId == exam.id, ExaminationSession.studentId == student.id))
    if data.action == "start":
        if exam.status not in (ExamStatus.LIVE, ExamStatus.SCHEDULED):
            raise HTTPException(409, "Examination is not currently accepting activity")
        if exam.status == ExamStatus.SCHEDULED and now < exam.startsAt:
            raise HTTPException(409, "Examination has not started")
        if now > exam.endsAt: raise HTTPException(409, "Examination has closed")
        if session:
            if session.status != SessionStatus.IN_PROGRESS: return {"started": True, "submitted": True}
            return {"started": True, "deadlineAt": session.deadlineAt}
        ids = [link.questionId for link in exam.questions]
        if exam.shuffleQuestions: random.SystemRandom().shuffle(ids)
        deadline = min(now + timedelta(minutes=exam.durationMin), exam.endsAt)
        session = ExaminationSession(examId=exam.id, studentId=student.id, deadlineAt=deadline, questionOrder=ids)
        db.add(session); db.commit(); db.refresh(session)
        return {"started": True, "deadlineAt": session.deadlineAt}
    if not session: raise HTTPException(409, "Start the examination first")
    if session.status != SessionStatus.IN_PROGRESS: raise HTTPException(409, "Examination has already been submitted")
    if data.action == "submit":
        _submit_session(db, session)
        return {"submitted": True}
    if exam.status == ExamStatus.PAUSED:
        raise HTTPException(409, "The examination is temporarily paused")
    if exam.status in (ExamStatus.CLOSED, ExamStatus.CANCELLED) or session.deadlineAt <= now or exam.endsAt <= now:
        _submit_session(db, session)
        return {"submitted": True}
    if data.action == "visibility":
        session.tabSwitches += 1; db.commit(); return {"recorded": True}
    if data.action == "save":
        if not data.questionId: raise HTTPException(400, "Question is required")
        if data.questionId not in {link.questionId for link in exam.questions}:
            raise HTTPException(400, "Question is not part of this examination")
        if data.optionId:
            option = db.get(QuestionOption, data.optionId)
            if not option or option.questionId != data.questionId:
                raise HTTPException(400, "Invalid answer option")
        answer = db.scalar(select(StudentAnswer).where(StudentAnswer.sessionId == session.id, StudentAnswer.questionId == data.questionId))
        if answer:
            answer.optionId = data.optionId; answer.flagged = bool(data.flagged)
            answer.savedAt = utcnow()
        else:
            db.add(StudentAnswer(sessionId=session.id, questionId=data.questionId, optionId=data.optionId, flagged=bool(data.flagged)))
        db.commit(); return {"saved": True}
    raise HTTPException(400, "Unknown examination action")

@router.get("/leaderboard")
def public_leaderboard(roundId: str | None = None, db: DBSession = Depends(get_db)):
    if roundId:
        round_row = db.get(CompetitionRound, roundId)
        if not round_row:
            raise HTTPException(404, "Competition round not found")
        if round_row.classAggregation != "AVG_PERCENT":
            raise HTTPException(400, f"Class aggregation {round_row.classAggregation} is not implemented")
    stmt = select(ExaminationResult).join(ExaminationResult.exam).options(
        selectinload(ExaminationResult.student).selectinload(Student.schoolClass), selectinload(ExaminationResult.exam)
    ).where(ExaminationResult.published.is_(True)).order_by(ExaminationResult.score.desc(), ExaminationResult.timeSeconds.asc())
    if roundId:
        stmt = stmt.where(Examination.roundId == roundId)
        participant_ids = db.scalars(select(CompetitionParticipant.studentId).where(CompetitionParticipant.roundId == roundId)).all()
        if participant_ids:
            stmt = stmt.where(ExaminationResult.studentId.in_(participant_ids))
    results = db.scalars(stmt).all()
    individual = [{"id": r.id, "score": r.score, "total": r.total, "timeSeconds": r.timeSeconds,
        "student": {"id": r.student.id, "fullName": r.student.fullName, "class": {"id": r.student.schoolClass.id, "name": r.student.schoolClass.name}},
        "exam": {"id": r.exam.id, "title": r.exam.title}} for r in results[:50]]
    grouped: dict[str, dict] = {}
    for result in results:
        key = result.student.classId
        bucket = grouped.setdefault(key, {"classId": key, "className": result.student.schoolClass.name, "students": {}})
        bucket["students"].setdefault(result.student.id, []).append((result.score / result.total * 100) if result.total else 0.0)
    classes = []
    for item in grouped.values():
        # AVG_PERCENT: average each participant's published result percentages, then average participants equally.
        student_averages = [sum(scores) / len(scores) for scores in item["students"].values()]
        average = sum(student_averages) / len(student_averages) if student_averages else 0.0
        classes.append({"classId": item["classId"], "className": item["className"], "avgPercent": round(average, 2),
                        "participants": len(student_averages), "points": round(average, 2)})
    classes.sort(key=lambda row: (-row["points"], row["className"]))
    return {"individual": individual, "classes": classes}
