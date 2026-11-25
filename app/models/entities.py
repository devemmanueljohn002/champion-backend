from __future__ import annotations
from datetime import datetime
from enum import Enum
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.core.time import utcnow


def new_id() -> str:
    return uuid4().hex


class Role(str, Enum):
    ADMIN = "ADMIN"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"

class Difficulty(str, Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
    EXPERT = "EXPERT"

class QType(str, Enum):
    MCQ = "MCQ"
    TRUE_FALSE = "TRUE_FALSE"
    NUMERIC = "NUMERIC"
    EXPRESSION = "EXPRESSION"
    IMAGE = "IMAGE"

class ExamStatus(str, Enum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"

class SessionStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    EXPIRED = "EXPIRED"

class QStatus(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"

class RoundType(str, Enum):
    PRELIM = "PRELIM"
    QUARTER = "QUARTER"
    SEMI = "SEMI"
    FINAL = "FINAL"
    HEAD_TO_HEAD = "HEAD_TO_HEAD"
    CLASS_BATTLE = "CLASS_BATTLE"


def enum_col(enum_cls):
    return SAEnum(enum_cls, native_enum=False, values_callable=lambda cls: [e.value for e in cls], length=32)

class User(Base):
    __tablename__ = "User"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    loginId: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    passwordHash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(enum_col(Role))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mustChangePw: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    student: Mapped[Student | None] = relationship(back_populates="user", uselist=False)
    teacher: Mapped[Teacher | None] = relationship(back_populates="user", uselist=False)
    admin: Mapped[Administrator | None] = relationship(back_populates="user", uselist=False)
    sessions: Mapped[list[Session]] = relationship(back_populates="user", cascade="all, delete-orphan")

class Administrator(Base):
    __tablename__ = "Administrator"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    userId: Mapped[str] = mapped_column(ForeignKey("User.id"), unique=True)
    fullName: Mapped[str] = mapped_column(String(160))
    user: Mapped[User] = relationship(back_populates="admin")

class Teacher(Base):
    __tablename__ = "Teacher"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    userId: Mapped[str] = mapped_column(ForeignKey("User.id"), unique=True)
    fullName: Mapped[str] = mapped_column(String(160))
    user: Mapped[User] = relationship(back_populates="teacher")
    classes: Mapped[list[SchoolClass]] = relationship(back_populates="teacher")

class SchoolClass(Base):
    __tablename__ = "SchoolClass"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(20), unique=True)
    category: Mapped[str] = mapped_column(String(32))
    teacherId: Mapped[str | None] = mapped_column(ForeignKey("Teacher.id", ondelete="SET NULL"), nullable=True)
    teacher: Mapped[Teacher | None] = relationship(back_populates="classes")
    students: Mapped[list[Student]] = relationship(back_populates="schoolClass")
    exams: Mapped[list[Examination]] = relationship(back_populates="schoolClass")
    scores: Mapped[list[ClassScore]] = relationship(back_populates="schoolClass")

class Student(Base):
    __tablename__ = "Student"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    userId: Mapped[str] = mapped_column(ForeignKey("User.id"), unique=True)
    studentCode: Mapped[str] = mapped_column(String(40), unique=True)
    fullName: Mapped[str] = mapped_column(String(120))
    gender: Mapped[str | None] = mapped_column(String(8), nullable=True)
    photoUrl: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    classId: Mapped[str] = mapped_column(ForeignKey("SchoolClass.id"))
    isDemo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user: Mapped[User] = relationship(back_populates="student")
    schoolClass: Mapped[SchoolClass] = relationship(back_populates="students")
    sessions: Mapped[list[ExaminationSession]] = relationship(back_populates="student")
    results: Mapped[list[ExaminationResult]] = relationship(back_populates="student")
    participations: Mapped[list[CompetitionParticipant]] = relationship(back_populates="student")
    certificates: Mapped[list[Certificate]] = relationship(back_populates="student")
    __table_args__ = (Index("Student_classId_idx", "classId"),)

class Subject(Base):
    __tablename__ = "Subject"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    topics: Mapped[list[Topic]] = relationship(back_populates="subject")
    questions: Mapped[list[Question]] = relationship(back_populates="subject")

class Topic(Base):
    __tablename__ = "Topic"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    subjectId: Mapped[str] = mapped_column(ForeignKey("Subject.id"))
    subject: Mapped[Subject] = relationship(back_populates="topics")
    questions: Mapped[list[Question]] = relationship(back_populates="topic")
    __table_args__ = (UniqueConstraint("subjectId", "name", name="Topic_subjectId_name_key"),)

class Question(Base):
    __tablename__ = "Question"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    text: Mapped[str] = mapped_column(Text)
    type: Mapped[QType] = mapped_column(enum_col(QType), default=QType.MCQ)
    subjectId: Mapped[str] = mapped_column(ForeignKey("Subject.id"))
    topicId: Mapped[str | None] = mapped_column(ForeignKey("Topic.id", ondelete="SET NULL"), nullable=True)
    classId: Mapped[str] = mapped_column(String)
    difficulty: Mapped[Difficulty] = mapped_column(enum_col(Difficulty))
    marks: Mapped[int] = mapped_column(Integer, default=1)
    seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    imageUrl: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[QStatus] = mapped_column(enum_col(QStatus), default=QStatus.DRAFT)
    isDemo: Mapped[bool] = mapped_column(Boolean, default=False)
    subject: Mapped[Subject] = relationship(back_populates="questions")
    topic: Mapped[Topic | None] = relationship(back_populates="questions")
    options: Mapped[list[QuestionOption]] = relationship(back_populates="question", cascade="all, delete-orphan")
    examLinks: Mapped[list[ExaminationQuestion]] = relationship(back_populates="question")
    __table_args__ = (Index("Question_classId_subjectId_status_idx", "classId", "subjectId", "status"),)

class QuestionOption(Base):
    __tablename__ = "QuestionOption"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    questionId: Mapped[str] = mapped_column(ForeignKey("Question.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(8))
    text: Mapped[str] = mapped_column(Text)
    isCorrect: Mapped[bool] = mapped_column(Boolean)
    question: Mapped[Question] = relationship(back_populates="options")
    answers: Mapped[list[StudentAnswer]] = relationship(back_populates="option")

class CompetitionRound(Base):
    __tablename__ = "CompetitionRound"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    type: Mapped[RoundType] = mapped_column(enum_col(RoundType))
    orderNo: Mapped[int] = mapped_column(Integer)
    advanceCount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tieBreakers: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    classAggregation: Mapped[str] = mapped_column(String(40), default="AVG_PERCENT")
    exams: Mapped[list[Examination]] = relationship(back_populates="round")
    participants: Mapped[list[CompetitionParticipant]] = relationship(back_populates="round")
    leaderboards: Mapped[list[Leaderboard]] = relationship(back_populates="round")

class Examination(Base):
    __tablename__ = "Examination"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(160))
    status: Mapped[ExamStatus] = mapped_column(enum_col(ExamStatus), default=ExamStatus.DRAFT)
    classId: Mapped[str] = mapped_column(ForeignKey("SchoolClass.id"))
    subjectId: Mapped[str | None] = mapped_column(ForeignKey("Subject.id"), nullable=True)
    roundId: Mapped[str | None] = mapped_column(ForeignKey("CompetitionRound.id", ondelete="SET NULL"), nullable=True)
    durationMin: Mapped[int] = mapped_column(Integer, default=40)
    startsAt: Mapped[datetime] = mapped_column(DateTime)
    endsAt: Mapped[datetime] = mapped_column(DateTime)
    actualStartedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pausedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shuffleQuestions: Mapped[bool] = mapped_column(Boolean, default=True)
    shuffleOptions: Mapped[bool] = mapped_column(Boolean, default=True)
    negativeMarking: Mapped[bool] = mapped_column(Boolean, default=False)
    passMark: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resultsPublished: Mapped[bool] = mapped_column(Boolean, default=False)
    schoolClass: Mapped[SchoolClass] = relationship(back_populates="exams")
    subject: Mapped[Subject | None] = relationship()
    round: Mapped[CompetitionRound | None] = relationship(back_populates="exams")
    questions: Mapped[list[ExaminationQuestion]] = relationship(back_populates="exam", cascade="all, delete-orphan")
    sessions: Mapped[list[ExaminationSession]] = relationship(back_populates="exam")
    results: Mapped[list[ExaminationResult]] = relationship(back_populates="exam")
    __table_args__ = (Index("Examination_classId_status_idx", "classId", "status"),)

class ExaminationQuestion(Base):
    __tablename__ = "ExaminationQuestion"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    examId: Mapped[str] = mapped_column(ForeignKey("Examination.id", ondelete="CASCADE"))
    questionId: Mapped[str] = mapped_column(ForeignKey("Question.id"))
    orderNo: Mapped[int] = mapped_column(Integer)
    exam: Mapped[Examination] = relationship(back_populates="questions")
    question: Mapped[Question] = relationship(back_populates="examLinks")
    __table_args__ = (UniqueConstraint("examId", "questionId", name="ExaminationQuestion_examId_questionId_key"),)

class ExaminationSession(Base):
    __tablename__ = "ExaminationSession"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    examId: Mapped[str] = mapped_column(ForeignKey("Examination.id"))
    studentId: Mapped[str] = mapped_column(ForeignKey("Student.id"))
    startedAt: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    deadlineAt: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[SessionStatus] = mapped_column(enum_col(SessionStatus), default=SessionStatus.IN_PROGRESS)
    questionOrder: Mapped[list] = mapped_column(JSON)
    tabSwitches: Mapped[int] = mapped_column(Integer, default=0)
    exam: Mapped[Examination] = relationship(back_populates="sessions")
    student: Mapped[Student] = relationship(back_populates="sessions")
    answers: Mapped[list[StudentAnswer]] = relationship(back_populates="session", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("examId", "studentId", name="ExaminationSession_examId_studentId_key"),)

class StudentAnswer(Base):
    __tablename__ = "StudentAnswer"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    sessionId: Mapped[str] = mapped_column(ForeignKey("ExaminationSession.id", ondelete="CASCADE"))
    questionId: Mapped[str] = mapped_column(String)
    optionId: Mapped[str | None] = mapped_column(ForeignKey("QuestionOption.id", ondelete="SET NULL"), nullable=True)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    savedAt: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    session: Mapped[ExaminationSession] = relationship(back_populates="answers")
    option: Mapped[QuestionOption | None] = relationship(back_populates="answers")
    __table_args__ = (UniqueConstraint("sessionId", "questionId", name="StudentAnswer_sessionId_questionId_key"),)

class ExaminationResult(Base):
    __tablename__ = "ExaminationResult"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    examId: Mapped[str] = mapped_column(ForeignKey("Examination.id"))
    studentId: Mapped[str] = mapped_column(ForeignKey("Student.id"))
    score: Mapped[float] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    correct: Mapped[int] = mapped_column(Integer)
    incorrect: Mapped[int] = mapped_column(Integer)
    unanswered: Mapped[int] = mapped_column(Integer)
    timeSeconds: Mapped[int] = mapped_column(Integer)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    isDemo: Mapped[bool] = mapped_column(Boolean, default=False)
    exam: Mapped[Examination] = relationship(back_populates="results")
    student: Mapped[Student] = relationship(back_populates="results")
    __table_args__ = (UniqueConstraint("examId", "studentId", name="ExaminationResult_examId_studentId_key"),)

class CompetitionParticipant(Base):
    __tablename__ = "CompetitionParticipant"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    roundId: Mapped[str] = mapped_column(ForeignKey("CompetitionRound.id"))
    studentId: Mapped[str] = mapped_column(ForeignKey("Student.id"))
    qualified: Mapped[bool] = mapped_column(Boolean, default=False)
    round: Mapped[CompetitionRound] = relationship(back_populates="participants")
    student: Mapped[Student] = relationship(back_populates="participations")
    __table_args__ = (UniqueConstraint("roundId", "studentId", name="CompetitionParticipant_roundId_studentId_key"),)

class Leaderboard(Base):
    __tablename__ = "Leaderboard"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    roundId: Mapped[str] = mapped_column(ForeignKey("CompetitionRound.id"))
    scope: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict | list] = mapped_column(JSON)
    generatedAt: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    round: Mapped[CompetitionRound] = relationship(back_populates="leaderboards")

class ClassScore(Base):
    __tablename__ = "ClassScore"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    classId: Mapped[str] = mapped_column(ForeignKey("SchoolClass.id"))
    roundId: Mapped[str | None] = mapped_column(String, nullable=True)
    avgPercent: Mapped[float] = mapped_column(Float)
    participants: Mapped[int] = mapped_column(Integer)
    points: Mapped[float] = mapped_column(Float, default=0)
    schoolClass: Mapped[SchoolClass] = relationship(back_populates="scores")

class Certificate(Base):
    __tablename__ = "Certificate"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    studentId: Mapped[str] = mapped_column(ForeignKey("Student.id"))
    achievement: Mapped[str] = mapped_column(String(240))
    issuedAt: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    student: Mapped[Student] = relationship(back_populates="certificates")

class AuditLog(Base):
    __tablename__ = "AuditLog"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    actorId: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(80), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (Index("AuditLog_createdAt_idx", "createdAt"),)

class SchoolSetting(Base):
    __tablename__ = "SchoolSetting"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    schoolName: Mapped[str] = mapped_column(String(200))
    contactEmail: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    logoUrl: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    settings: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

class Announcement(Base):
    __tablename__ = "Announcement"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    audience: Mapped[str] = mapped_column(String(40))
    createdAt: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Session(Base):
    __tablename__ = "Session"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    userId: Mapped[str] = mapped_column(ForeignKey("User.id", ondelete="CASCADE"))
    expiresAt: Mapped[datetime] = mapped_column(DateTime)
    createdAt: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user: Mapped[User] = relationship(back_populates="sessions")
    __table_args__ = (Index("Session_userId_idx", "userId"),)
