from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

url = settings.database_url
connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
if url.startswith("sqlite:///") and ":memory:" not in url:
    db_path = url.removeprefix("sqlite:///")
    path = Path(db_path)
    if not path.is_absolute():
        path = (Path(__file__).resolve().parents[2] / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{path.as_posix()}"

engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
if url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
