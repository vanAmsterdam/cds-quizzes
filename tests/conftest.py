from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cds_quizzes.config import DEFAULT_SAMPLE_ROSTER_PATH, DEFAULT_WORKBOOK_PATH
from cds_quizzes.database import seed_round0_question
from cds_quizzes.importers import import_roster, import_workbook
from cds_quizzes.models import Base


@pytest.fixture()
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.sqlite'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    session = Session()
    seed_round0_question(session)
    import_workbook(session, DEFAULT_WORKBOOK_PATH)
    import_roster(session, DEFAULT_SAMPLE_ROSTER_PATH)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
