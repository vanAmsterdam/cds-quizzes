from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Assignment, FormQuestion, Question, Student
from .security import hash_sign_in_key


CORE_SHEET = "Core 36 forms"
KEY_SHEET = "Deterministic bank"

CORE_COLUMNS = {
    "Round",
    "Student form",
    "Slot",
    "ID",
    "Difficulty",
    "Band",
    "Topic",
    "Type",
    "Question",
    "Option A",
    "Option B",
    "Option C",
    "Option D",
}

KEY_COLUMNS = {
    "ID",
    "Difficulty",
    "Band",
    "Topic",
    "Type",
    "Question",
    "Option A",
    "Option B",
    "Option C",
    "Option D",
    "Correct answer",
    "Brief rationale / grading note",
    "Instructor note",
}

ROSTER_COLUMNS = {"student_id", "sign_in_key", "group_id", "round_id", "question_set_id"}


@dataclass(frozen=True)
class ImportSummary:
    questions: int = 0
    form_questions: int = 0
    students: int = 0
    assignments: int = 0


def clean_cell(value: object) -> object | None:
    if pd.isna(value):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {', '.join(missing)}")


def import_workbook(db: Session, source: str | Path | BinaryIO) -> ImportSummary:
    workbook = pd.ExcelFile(source)
    core = pd.read_excel(workbook, sheet_name=CORE_SHEET)
    key = pd.read_excel(workbook, sheet_name=KEY_SHEET)
    require_columns(core, CORE_COLUMNS, CORE_SHEET)
    require_columns(key, KEY_COLUMNS, KEY_SHEET)

    key = key.dropna(how="all")
    core = core.dropna(how="all")
    key_by_id = {str(row["ID"]).strip(): row for _, row in key.iterrows() if clean_cell(row["ID"])}

    question_count = 0
    for question_id, row in key_by_id.items():
        question = db.get(Question, question_id) or Question(question_id=question_id)
        question.difficulty = _as_int(clean_cell(row["Difficulty"]))
        question.band = _as_str(clean_cell(row["Band"]))
        question.topic = _as_str(clean_cell(row["Topic"]))
        question.question_type = _as_str(clean_cell(row["Type"])) or "MCQ"
        question.question_text = _as_str(clean_cell(row["Question"])) or ""
        question.option_a = _as_str(clean_cell(row["Option A"]))
        question.option_b = _as_str(clean_cell(row["Option B"]))
        question.option_c = _as_str(clean_cell(row["Option C"]))
        question.option_d = _as_str(clean_cell(row["Option D"]))
        question.correct_answer = _as_str(clean_cell(row["Correct answer"]))
        question.rationale = _as_str(clean_cell(row["Brief rationale / grading note"]))
        question.instructor_note = _as_str(clean_cell(row["Instructor note"]))
        db.merge(question)
        question_count += 1

    # Postgres checks the form_questions FK immediately, so make sure the
    # referenced questions exist before inserting form mappings.
    db.flush()

    form_count = 0
    seen_slots: set[tuple[str, str, int]] = set()
    for _, row in core.iterrows():
        round_id = _as_str(clean_cell(row["Round"]))
        question_set_id = _as_str(clean_cell(row["Student form"]))
        question_order = _as_int(clean_cell(row["Slot"]))
        question_id = _as_str(clean_cell(row["ID"]))
        if not (round_id and question_set_id and question_order and question_id):
            continue
        if question_id not in key_by_id:
            raise ValueError(f"Core form question {question_id} is missing from deterministic bank.")
        slot_key = (round_id, question_set_id, question_order)
        if slot_key in seen_slots:
            raise ValueError(f"Duplicate form slot: {round_id} / {question_set_id} / {question_order}")
        seen_slots.add(slot_key)
        db.merge(
            FormQuestion(
                round_id=round_id,
                question_set_id=question_set_id,
                question_order=question_order,
                question_id=question_id,
            )
        )
        form_count += 1

    db.flush()
    _validate_form_sizes(db)
    return ImportSummary(questions=question_count, form_questions=form_count)


def import_roster(db: Session, source: str | Path | BinaryIO) -> ImportSummary:
    roster = pd.read_csv(source, dtype=str).fillna("")
    require_columns(roster, ROSTER_COLUMNS, "Roster CSV")
    roster = roster.dropna(how="all")

    students_by_key: dict[str, str] = {}
    student_groups: dict[str, str] = {}
    for _, row in roster.iterrows():
        student_id = row["student_id"].strip()
        sign_in_key = row["sign_in_key"].strip()
        group_id = row["group_id"].strip() or None
        if not student_id or not sign_in_key:
            raise ValueError("Roster rows must include student_id and sign_in_key.")
        key_hash = hash_sign_in_key(sign_in_key)
        if key_hash in students_by_key and students_by_key[key_hash] != student_id:
            raise ValueError("The same sign-in key is assigned to multiple students.")
        if student_id in student_groups and student_groups[student_id] != (group_id or ""):
            raise ValueError(f"Student {student_id} has inconsistent group_id values.")
        students_by_key[key_hash] = student_id
        student_groups[student_id] = group_id or ""

    for key_hash, student_id in students_by_key.items():
        student = db.get(Student, student_id) or Student(student_id=student_id, sign_in_key_hash=key_hash)
        student.sign_in_key_hash = key_hash
        student.group_id = student_groups[student_id] or None
        db.merge(student)

    db.flush()
    assignment_count = 0
    for _, row in roster.iterrows():
        student_id = row["student_id"].strip()
        round_id = row["round_id"].strip()
        question_set_id = row["question_set_id"].strip()
        if not round_id or not question_set_id:
            raise ValueError(f"Roster row for {student_id} must include round_id and question_set_id.")
        if not _form_exists(db, round_id, question_set_id):
            raise ValueError(f"Unknown round/form assignment: {round_id} / {question_set_id}")
        db.merge(
            Assignment(
                student_id=student_id,
                round_id=round_id,
                question_set_id=question_set_id,
            )
        )
        assignment_count += 1

    return ImportSummary(students=len(students_by_key), assignments=assignment_count)


def _validate_form_sizes(db: Session) -> None:
    counts = db.execute(
        select(FormQuestion.round_id, FormQuestion.question_set_id, func.count())
        .group_by(FormQuestion.round_id, FormQuestion.question_set_id)
    ).all()
    bad = [(round_id, form_id, count) for round_id, form_id, count in counts if count != 6]
    if bad:
        details = ", ".join(f"{r}/{f} has {c}" for r, f, c in bad)
        raise ValueError(f"Every imported round/form must contain exactly 6 questions; {details}.")


def _form_exists(db: Session, round_id: str, question_set_id: str) -> bool:
    return (
        db.execute(
            select(func.count())
            .select_from(FormQuestion)
            .where(FormQuestion.round_id == round_id, FormQuestion.question_set_id == question_set_id)
        ).scalar_one()
        == 6
    )


def _as_int(value: object | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _as_str(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value).strip()
