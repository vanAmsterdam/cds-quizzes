from __future__ import annotations

import csv

from sqlalchemy import func, select

from .config import (
    DEFAULT_CLASS_FORM_QUESTIONS_PATH,
    DEFAULT_CLASS_ROSTER_PATH,
    DEFAULT_SAMPLE_ROSTER_PATH,
    DEFAULT_WORKBOOK_PATH,
    get_settings,
)
from .database import init_database, session_scope
from .importers import ImportSummary, import_form_questions, import_roster, import_workbook
from .models import Assignment, FormQuestion, Student


def import_default_class_data(db) -> tuple[ImportSummary | None, ImportSummary | None, ImportSummary | None]:
    workbook_summary = None
    form_summary = None
    roster_summary = None
    if DEFAULT_WORKBOOK_PATH.exists():
        workbook_summary = import_workbook(db, DEFAULT_WORKBOOK_PATH)
    if DEFAULT_CLASS_FORM_QUESTIONS_PATH.exists():
        form_summary = import_form_questions(db, DEFAULT_CLASS_FORM_QUESTIONS_PATH)
    if DEFAULT_CLASS_ROSTER_PATH.exists():
        roster_summary = import_roster(db, DEFAULT_CLASS_ROSTER_PATH)
    return workbook_summary, form_summary, roster_summary


def initialize_app_data() -> None:
    init_database()
    settings = get_settings()
    with session_scope() as db:
        form_count = db.execute(select(func.count()).select_from(FormQuestion)).scalar_one()
        if form_count == 0 and DEFAULT_WORKBOOK_PATH.exists():
            import_workbook(db, DEFAULT_WORKBOOK_PATH)

        student_count = db.execute(select(func.count()).select_from(Student)).scalar_one()
        if DEFAULT_CLASS_FORM_QUESTIONS_PATH.exists() and not _default_form_questions_loaded(db):
            import_form_questions(db, DEFAULT_CLASS_FORM_QUESTIONS_PATH)

        if DEFAULT_CLASS_ROSTER_PATH.exists() and not _default_roster_loaded(db):
            import_roster(db, DEFAULT_CLASS_ROSTER_PATH)
        elif settings.is_sqlite and student_count == 0 and DEFAULT_SAMPLE_ROSTER_PATH.exists():
            import_roster(db, DEFAULT_SAMPLE_ROSTER_PATH)


def _default_form_questions_loaded(db) -> bool:
    question_set_ids = {
        row["question_set_id"].strip()
        for row in _csv_rows(DEFAULT_CLASS_FORM_QUESTIONS_PATH)
        if row.get("question_set_id", "").strip()
    }
    if not question_set_ids:
        return False
    counts = dict(
        db.execute(
            select(FormQuestion.question_set_id, func.count())
            .where(FormQuestion.question_set_id.in_(question_set_ids))
            .group_by(FormQuestion.question_set_id)
        ).all()
    )
    return all(counts.get(question_set_id) == 6 for question_set_id in question_set_ids)


def _default_roster_loaded(db) -> bool:
    student_ids = {
        row["student_id"].strip()
        for row in _csv_rows(DEFAULT_CLASS_ROSTER_PATH)
        if row.get("student_id", "").strip()
    }
    if not student_ids:
        return False
    student_count = (
        db.execute(select(func.count()).select_from(Student).where(Student.student_id.in_(student_ids))).scalar_one()
    )
    assignment_count = (
        db.execute(
            select(func.count()).select_from(Assignment).where(Assignment.student_id.in_(student_ids))
        ).scalar_one()
    )
    return student_count == len(student_ids) and assignment_count >= len(student_ids) * 2


def _csv_rows(path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
