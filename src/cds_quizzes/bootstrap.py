from __future__ import annotations

from sqlalchemy import func, select

from .config import DEFAULT_SAMPLE_ROSTER_PATH, DEFAULT_WORKBOOK_PATH, get_settings
from .database import init_database, session_scope
from .importers import import_roster, import_workbook
from .models import FormQuestion, Student


def initialize_app_data() -> None:
    init_database()
    settings = get_settings()
    with session_scope() as db:
        form_count = db.execute(select(func.count()).select_from(FormQuestion)).scalar_one()
        if form_count == 0 and DEFAULT_WORKBOOK_PATH.exists():
            import_workbook(db, DEFAULT_WORKBOOK_PATH)

        student_count = db.execute(select(func.count()).select_from(Student)).scalar_one()
        if settings.is_sqlite and student_count == 0 and DEFAULT_SAMPLE_ROSTER_PATH.exists():
            import_roster(db, DEFAULT_SAMPLE_ROSTER_PATH)
