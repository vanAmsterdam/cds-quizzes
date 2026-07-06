from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .database import database_now
from .models import (
    PHASE_DONE,
    PHASE_INDIVIDUAL,
    PHASE_REVISION,
    PHASE_SELECT_DISCUSSION,
    ROUND0_ID,
    ROUND0_QUESTION_ID,
    Answer,
    Assignment,
    DraftAnswer,
    FormQuestion,
    Question,
    QuizSession,
    Student,
)
from .security import hash_sign_in_key
from .timezone import amsterdam_now

INDIVIDUAL_DURATION_SECONDS = 360
ROUND2_ID = "Round 2"


class WorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class AssignedQuestion:
    order: int
    question: Question


def authenticate_student(db: Session, raw_key: str) -> Student | None:
    key_hash = hash_sign_in_key(raw_key)
    student = db.execute(select(Student).where(Student.sign_in_key_hash == key_hash)).scalar_one_or_none()
    if student is not None:
        student.last_seen_at = database_now(db)
    return student


def get_student(db: Session, student_id: str) -> Student | None:
    return db.get(Student, student_id)


def list_student_assignments(db: Session, student_id: str) -> list[Assignment]:
    rows = db.execute(select(Assignment).where(Assignment.student_id == student_id)).scalars().all()
    return sorted(rows, key=lambda row: round_sort_key(row.round_id))


def next_unfinished_assignment(db: Session, student_id: str) -> Assignment | None:
    for assignment in list_student_assignments(db, student_id):
        session = db.get(QuizSession, {"student_id": student_id, "round_id": assignment.round_id})
        if session is None or session.phase != PHASE_DONE:
            return assignment
    return None


def get_assignment(db: Session, student_id: str, round_id: str) -> Assignment:
    assignment = db.get(Assignment, {"student_id": student_id, "round_id": round_id})
    if assignment is None:
        raise WorkflowError("No assignment exists for this student and round.")
    return assignment


def get_assigned_questions(db: Session, student_id: str, round_id: str) -> list[AssignedQuestion]:
    assignment = get_assignment(db, student_id, round_id)
    rows = db.execute(
        select(FormQuestion.question_order, Question)
        .join(Question, Question.question_id == FormQuestion.question_id)
        .where(
            FormQuestion.round_id == round_id,
            FormQuestion.question_set_id == assignment.question_set_id,
        )
        .order_by(FormQuestion.question_order)
    ).all()
    questions = [AssignedQuestion(order=order, question=question) for order, question in rows]
    if len(questions) != 6:
        raise WorkflowError("This assignment does not have exactly six questions.")
    return questions


def get_or_create_real_session(db: Session, student_id: str, round_id: str) -> QuizSession:
    get_assignment(db, student_id, round_id)
    now = database_now(db)
    session = db.get(QuizSession, {"student_id": student_id, "round_id": round_id})
    if session is None:
        session = QuizSession(
            student_id=student_id,
            round_id=round_id,
            phase=PHASE_INDIVIDUAL,
            individual_started_at=now,
            updated_at=now,
        )
        db.add(session)
        db.flush()
    elif session.individual_started_at is None and session.phase == PHASE_INDIVIDUAL:
        session.individual_started_at = now
        session.updated_at = now
    return session


def get_round0_session(db: Session, student_id: str) -> QuizSession | None:
    return db.get(QuizSession, {"student_id": student_id, "round_id": ROUND0_ID})


def is_round0_complete(db: Session, student_id: str) -> bool:
    session = get_round0_session(db, student_id)
    return bool(session and session.phase == PHASE_DONE and session.done_at is not None)


def submit_round0(db: Session, student_id: str, answer_value: str) -> None:
    if not answer_value:
        raise WorkflowError("Choose an answer before submitting the Round 0 check.")
    if db.get(Student, student_id) is None:
        raise WorkflowError("Unknown student.")
    now = database_now(db)
    session = get_round0_session(db, student_id)
    if session is None:
        session = QuizSession(
            student_id=student_id,
            round_id=ROUND0_ID,
            phase=PHASE_DONE,
            individual_started_at=now,
            individual_submitted_at=now,
            done_at=now,
            updated_at=now,
        )
        db.add(session)
    elif session.phase == PHASE_DONE:
        raise WorkflowError("Round 0 has already been submitted.")
    else:
        session.phase = PHASE_DONE
        session.individual_submitted_at = now
        session.done_at = now
        session.updated_at = now

    answer = db.get(
        Answer,
        {"student_id": student_id, "round_id": ROUND0_ID, "question_id": ROUND0_QUESTION_ID},
    ) or Answer(student_id=student_id, round_id=ROUND0_ID, question_id=ROUND0_QUESTION_ID)
    if answer.original_saved_at is not None:
        raise WorkflowError("Round 0 answer has already been saved.")
    answer.original_answer = answer_value
    answer.original_saved_at = now
    db.merge(answer)


def remaining_seconds(session: QuizSession, now: datetime | None = None) -> int:
    if session.individual_started_at is None:
        return INDIVIDUAL_DURATION_SECONDS
    now = now or amsterdam_now()
    elapsed = int((now - session.individual_started_at).total_seconds())
    return max(0, INDIVIDUAL_DURATION_SECONDS - elapsed)


def complete_individual_phase(db: Session, student_id: str, round_id: str, answers: dict[str, str | None]) -> None:
    session = get_or_create_real_session(db, student_id, round_id)
    if session.phase != PHASE_INDIVIDUAL:
        raise WorkflowError("Original answers are locked for this session.")

    assigned = get_assigned_questions(db, student_id, round_id)
    question_ids = [item.question.question_id for item in assigned]
    drafts = get_individual_drafts(db, student_id, round_id)
    now = database_now(db)
    for question_id in question_ids:
        answer = db.get(Answer, {"student_id": student_id, "round_id": round_id, "question_id": question_id})
        if answer is None:
            answer = Answer(student_id=student_id, round_id=round_id, question_id=question_id)
        if answer.original_saved_at is not None:
            raise WorkflowError("Original answers have already been saved.")
        submitted_answer = answers.get(question_id)
        if submitted_answer is None:
            submitted_answer = drafts.get(question_id, "")
        answer.original_answer = normalize_answer_value(submitted_answer)
        answer.original_saved_at = now
        db.merge(answer)

    db.flush()
    session.individual_submitted_at = now
    if round_id == ROUND2_ID:
        selected_question_id = _choose_round2_question(question_ids)
        _set_selected_question(db, session, selected_question_id, now)
        session.phase = PHASE_REVISION
    else:
        session.phase = PHASE_SELECT_DISCUSSION
    session.updated_at = now
    db.execute(delete(DraftAnswer).where(DraftAnswer.student_id == student_id, DraftAnswer.round_id == round_id))


def select_discussion_question(db: Session, student_id: str, round_id: str, question_id: str) -> None:
    session = db.get(QuizSession, {"student_id": student_id, "round_id": round_id})
    if session is None or session.phase != PHASE_SELECT_DISCUSSION:
        raise WorkflowError("Discussion selection is not available for this session.")
    if session.selected_question_id is not None:
        raise WorkflowError("Discussion question has already been selected.")

    assigned_ids = {item.question.question_id for item in get_assigned_questions(db, student_id, round_id)}
    if question_id not in assigned_ids:
        raise WorkflowError("Selected question is not assigned to this student.")
    now = database_now(db)
    _set_selected_question(db, session, question_id, now)
    session.phase = PHASE_REVISION
    session.updated_at = now


def submit_revision(db: Session, student_id: str, round_id: str, question_id: str, revised_answer: str) -> None:
    session = db.get(QuizSession, {"student_id": student_id, "round_id": round_id})
    if session is None or session.phase != PHASE_REVISION:
        raise WorkflowError("Revision is not available for this session.")
    if session.selected_question_id != question_id:
        raise WorkflowError("Only the selected discussion question can be revised.")
    answer = db.get(Answer, {"student_id": student_id, "round_id": round_id, "question_id": question_id})
    if answer is None or answer.original_saved_at is None:
        raise WorkflowError("Original answer must exist before revision.")
    if answer.revised_saved_at is not None:
        raise WorkflowError("Revision has already been submitted.")

    now = database_now(db)
    answer.revised_answer = normalize_answer_value(revised_answer)
    answer.revised_saved_at = now
    session.revision_submitted_at = now
    session.done_at = now
    session.phase = PHASE_DONE
    session.updated_at = now


def get_answers(db: Session, student_id: str, round_id: str) -> dict[str, Answer]:
    answers = db.execute(
        select(Answer).where(Answer.student_id == student_id, Answer.round_id == round_id)
    ).scalars()
    return {answer.question_id: answer for answer in answers}


def get_individual_drafts(db: Session, student_id: str, round_id: str) -> dict[str, str]:
    drafts = db.execute(
        select(DraftAnswer).where(DraftAnswer.student_id == student_id, DraftAnswer.round_id == round_id)
    ).scalars()
    return {draft.question_id: draft.draft_answer or "" for draft in drafts}


def save_individual_drafts(db: Session, student_id: str, round_id: str, answers: dict[str, str | None]) -> bool:
    session = get_or_create_real_session(db, student_id, round_id)
    if session.phase != PHASE_INDIVIDUAL:
        raise WorkflowError("Draft answers can only be saved during the individual phase.")

    assigned_ids = {item.question.question_id for item in get_assigned_questions(db, student_id, round_id)}
    unknown_ids = set(answers) - assigned_ids
    if unknown_ids:
        raise WorkflowError("Draft answers include questions that are not assigned to this student.")

    existing = {
        draft.question_id: draft
        for draft in db.execute(
            select(DraftAnswer).where(DraftAnswer.student_id == student_id, DraftAnswer.round_id == round_id)
        ).scalars()
    }
    now = None
    changed = False
    for question_id, value in answers.items():
        if value is None:
            continue
        normalized = normalize_answer_value(value)
        draft = existing.get(question_id)
        if draft is None:
            draft = DraftAnswer(student_id=student_id, round_id=round_id, question_id=question_id)
            db.add(draft)
        if draft.draft_answer != normalized:
            if now is None:
                now = database_now(db)
            draft.draft_answer = normalized
            draft.draft_saved_at = now
            changed = True
    return changed


def get_question(db: Session, question_id: str) -> Question | None:
    return db.get(Question, question_id)


def answer_label(question: Question, answer_value: str | None) -> str:
    if not answer_value:
        return "(blank)"
    options = question_options(question)
    if answer_value in options:
        return f"{answer_value}. {options[answer_value]}"
    return answer_value


def question_options(question: Question) -> dict[str, str]:
    values = {
        "A": question.option_a,
        "B": question.option_b,
        "C": question.option_c,
        "D": question.option_d,
    }
    return {letter: text for letter, text in values.items() if text}


def normalize_answer_value(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def reset_student_state(db: Session, student_id: str) -> None:
    student = db.get(Student, student_id)
    if student is None:
        raise WorkflowError("Unknown student.")
    db.execute(delete(Answer).where(Answer.student_id == student_id))
    db.execute(delete(DraftAnswer).where(DraftAnswer.student_id == student_id))
    db.execute(delete(QuizSession).where(QuizSession.student_id == student_id))
    student.last_seen_at = None


def monitor_rows(db: Session) -> list[dict[str, object]]:
    students = db.execute(select(Student).order_by(Student.group_id, Student.student_id)).scalars().all()
    rows: list[dict[str, object]] = []
    for student in students:
        round0 = db.get(QuizSession, {"student_id": student.student_id, "round_id": ROUND0_ID})
        round0_answer = db.get(
            Answer,
            {"student_id": student.student_id, "round_id": ROUND0_ID, "question_id": ROUND0_QUESTION_ID},
        )
        current = _latest_real_session(db, student.student_id)
        answer_stats = _answer_stats(db, student.student_id)
        rows.append(
            {
                "student_id": student.student_id,
                "group_id": student.group_id or "",
                "signed_in": student.last_seen_at is not None,
                "last_seen_at": student.last_seen_at,
                "round0_done": bool(round0 and round0.phase == PHASE_DONE),
                "round0_answer": round0_answer.original_answer if round0_answer else "",
                "round0_saved_at": round0_answer.original_saved_at if round0_answer else None,
                "current_round": current.round_id if current else "",
                "current_phase": current.phase if current else "",
                "original_answers": answer_stats["original_answers"],
                "revised_answers": answer_stats["revised_answers"],
                "last_answer_saved_at": answer_stats["last_answer_saved_at"],
            }
        )
    return rows


def round_sort_key(round_id: str) -> tuple[int, str]:
    match = re.search(r"\d+", round_id)
    if match:
        return (int(match.group()), round_id)
    return (999, round_id)


def _set_selected_question(db: Session, session: QuizSession, question_id: str, now: datetime) -> None:
    if session.selected_question_id is not None:
        raise WorkflowError("Discussion question has already been selected.")
    answer = db.get(
        Answer,
        {"student_id": session.student_id, "round_id": session.round_id, "question_id": question_id},
    )
    if answer is None:
        raise WorkflowError("Selected answer row does not exist.")
    session.selected_question_id = question_id
    session.selection_confirmed_at = now
    answer.selected_for_discussion = True


def _choose_round2_question(question_ids: Iterable[str]) -> str:
    ordered = list(question_ids)
    if not ordered:
        raise WorkflowError("Cannot randomly select from an empty question set.")
    return random.SystemRandom().choice(ordered)


def _latest_real_session(db: Session, student_id: str) -> QuizSession | None:
    return db.execute(
        select(QuizSession)
        .where(QuizSession.student_id == student_id, QuizSession.round_id != ROUND0_ID)
        .order_by(QuizSession.updated_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _answer_stats(db: Session, student_id: str) -> dict[str, object]:
    answers = db.execute(select(Answer).where(Answer.student_id == student_id)).scalars().all()
    original_count = sum(1 for answer in answers if answer.round_id != ROUND0_ID and answer.original_saved_at)
    revised_count = sum(1 for answer in answers if answer.round_id != ROUND0_ID and answer.revised_saved_at)
    saved_times = [
        ts
        for answer in answers
        for ts in (answer.original_saved_at, answer.revised_saved_at)
        if ts is not None
    ]
    return {
        "original_answers": original_count,
        "revised_answers": revised_count,
        "last_answer_saved_at": max(saved_times) if saved_times else None,
    }
