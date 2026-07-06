from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import DATA_DIR, get_settings
from .models import Base, PHASE_DONE, ROUND0_ID, ROUND0_QUESTION_ID, Question


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
    return create_engine(settings.database_url, connect_args=connect_args, future=True)


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
    value = db.execute(select(func.now())).scalar_one()
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    return datetime.now(UTC).replace(tzinfo=None)


def reset_connection_cache() -> None:
    get_session_factory.cache_clear()
    get_engine.cache_clear()
