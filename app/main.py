from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.api.v1.router import api_router
from app.routers.questions import router as question_router
from starlette.websockets import WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from app.db.session import SessionLocal
from app.core.security import hash_session_token
from app.models import Session, User, Role, Examination, Student
from app.core.time import utcnow


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield

app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan,
              docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json")

if settings.cors_origin_list:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
        allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Requested-With"])

@app.exception_handler(StarletteHTTPException)
async def http_error(_request: Request, exc: StarletteHTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "Request could not be completed"
    return JSONResponse(status_code=exc.status_code, content={"error": message})

@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": "Check the submitted fields", "issues": exc.errors()})

@app.exception_handler(IntegrityError)
async def integrity_error(_request: Request, _exc: IntegrityError):
    return JSONResponse(status_code=409, content={"error": "That value conflicts with an existing record or relationship"})

@app.get("/healthz", tags=["Health"])
def health():
    return {"status": "ok", "service": "championship-api"}

app.include_router(api_router, prefix=settings.api_v1_prefix)

from app.routers.questions import router as question_router


class ExaminationEventManager:
    def __init__(self):
        self.connections: dict[str, set[WebSocket]] = {}

    async def connect(self, exam_id: str, websocket: WebSocket):
        await websocket.accept()
        self.connections.setdefault(exam_id, set()).add(websocket)

    def disconnect(self, exam_id: str, websocket: WebSocket):
        self.connections.get(exam_id, set()).discard(websocket)

    async def broadcast(self, exam_id: str, event: dict):
        stale = []
        for websocket in self.connections.get(exam_id, set()).copy():
            try:
                await websocket.send_json(event)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(exam_id, websocket)


examination_events = ExaminationEventManager()


@app.websocket("/ws/examinations/{exam_id}")
async def examination_socket(websocket: WebSocket, exam_id: str):
    token = websocket.cookies.get(settings.session_cookie_name)
    if not token:
        await websocket.close(code=4401)
        return
    db: DBSession = SessionLocal()
    try:
        session = db.get(Session, hash_session_token(token))
        if not session or session.expiresAt <= utcnow():
            await websocket.close(code=4401)
            return
        user = db.get(User, session.userId)
        exam = db.get(Examination, exam_id)
        if not user or not exam or not user.active:
            await websocket.close(code=4403)
            return
        if user.role == Role.STUDENT:
            student = db.scalar(select(Student).where(Student.userId == user.id))
            if not student or student.classId != exam.classId:
                await websocket.close(code=4403)
                return
        elif user.role != Role.ADMIN:
            await websocket.close(code=4403)
            return
        await examination_events.connect(exam_id, websocket)
        await websocket.send_json({
            "type": "EXAM_STATE_SYNC",
            "status": exam.status.value,
            "endsAt": exam.endsAt.isoformat() if exam.endsAt else None,
        })
        while True:
            message = await websocket.receive_json()
            if message.get("type") in {"STUDENT_HEARTBEAT", "QUESTION_FLAGGED", "ANSWER_UPDATED", "STUDENT_JOINED"}:
                await examination_events.broadcast(exam_id, {
                    "type": message["type"],
                    "studentId": user.id,
                })
    except WebSocketDisconnect:
        pass
    finally:
        examination_events.disconnect(exam_id, websocket)
        db.close()
