from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import DATA_DIR, get_settings
from .models import Base, PHASE_DONE, ROUND0_ID, ROUND0_QUESTION_ID, Question
from .timezone import APP_TIMEZONE_NAME, amsterdam_now, to_amsterdam_naive


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
    engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
    if not settings.is_sqlite:
        _configure_postgres_timezone(engine)
    return engine


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_database() -> None:
    Base.metadata.create_all(get_engine())
    with session_scope() as db:
        seed_round0_question(db)


def seed_round0_question(db: Session) -> None:
    question = db.get(Question, ROUND0_QUESTION_ID)
    if question is None:
        question = Question(
            question_id=ROUND0_QUESTION_ID,
            difficulty=0,
            band="Practice",
            topic="System check",
            question_type="MCQ",
            question_text="Practice check: choose any option and submit to confirm that answering works.",
            option_a="The answer button works for me.",
            option_b="I can see and answer this question.",
            option_c="My sign-in key works.",
            option_d=None,
            correct_answer=None,
            rationale=None,
            instructor_note="Round 0 system check; excluded from scoring.",
        )
        db.add(question)


def database_now(db: Session) -> datetime:
    if db.get_bind().dialect.name == "sqlite":
        return amsterdam_now()
    value = db.execute(select(func.now())).scalar_one()
    if isinstance(value, datetime):
        return to_amsterdam_naive(value)
    if isinstance(value, str):
        return to_amsterdam_naive(datetime.fromisoformat(value.replace("Z", "+00:00")))
    return amsterdam_now()


def _configure_postgres_timezone(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def set_timezone(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"SET TIME ZONE '{APP_TIMEZONE_NAME}'")
        finally:
            cursor.close()


def reset_connection_cache() -> None:
    get_session_factory.cache_clear()
    get_engine.cache_clear()
