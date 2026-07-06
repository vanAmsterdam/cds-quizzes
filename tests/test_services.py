from __future__ import annotations

import pytest

from cds_quizzes.exports import joined_long_dataframe
from cds_quizzes.models import PHASE_DONE, PHASE_REVISION, QuizSession
from cds_quizzes.services import (
    WorkflowError,
    complete_individual_phase,
    get_assigned_questions,
    get_or_create_real_session,
    monitor_rows,
    remaining_seconds,
    select_discussion_question,
    submit_revision,
    submit_round0,
)


def answer_all(db, student_id: str, round_id: str) -> list[str]:
    questions = get_assigned_questions(db, student_id, round_id)
    answers = {item.question.question_id: "A" for item in questions}
    complete_individual_phase(db, student_id, round_id, answers)
    db.flush()
    return [item.question.question_id for item in questions]


def test_round0_answer_is_saved_and_visible_in_monitor(db):
    submit_round0(db, "demo_a", "A")
    db.flush()

    row = next(row for row in monitor_rows(db) if row["student_id"] == "demo_a")
    assert row["round0_done"] is True
    assert row["round0_answer"] == "A"
    assert row["round0_saved_at"] is not None


def test_student_cannot_revise_non_selected_question(db):
    question_ids = answer_all(db, "demo_a", "Round 1")
    select_discussion_question(db, "demo_a", "Round 1", question_ids[0])
    db.flush()

    with pytest.raises(WorkflowError, match="Only the selected"):
        submit_revision(db, "demo_a", "Round 1", question_ids[1], "B")


def test_student_cannot_change_selected_discussion_question(db):
    question_ids = answer_all(db, "demo_a", "Round 1")
    select_discussion_question(db, "demo_a", "Round 1", question_ids[0])
    db.flush()

    with pytest.raises(WorkflowError, match="not available|already"):
        select_discussion_question(db, "demo_a", "Round 1", question_ids[1])


def test_refresh_does_not_reset_individual_timer(db):
    first = get_or_create_real_session(db, "demo_a", "Round 1")
    started_at = first.individual_started_at
    db.flush()

    second = get_or_create_real_session(db, "demo_a", "Round 1")
    assert second.individual_started_at == started_at
    assert 0 <= remaining_seconds(second) <= 360


def test_round2_skips_selection_and_randomly_assigns_one_question(db):
    answer_all(db, "demo_a", "Round 2")
    session = db.get(QuizSession, {"student_id": "demo_a", "round_id": "Round 2"})

    assigned_ids = {item.question.question_id for item in get_assigned_questions(db, "demo_a", "Round 2")}
    assert session.phase == PHASE_REVISION
    assert session.selected_question_id in assigned_ids


def test_done_phase_rejects_answer_edits(db):
    question_ids = answer_all(db, "demo_a", "Round 1")
    select_discussion_question(db, "demo_a", "Round 1", question_ids[0])
    submit_revision(db, "demo_a", "Round 1", question_ids[0], "B")
    db.flush()

    session = db.get(QuizSession, {"student_id": "demo_a", "round_id": "Round 1"})
    assert session.phase == PHASE_DONE
    with pytest.raises(WorkflowError):
        complete_individual_phase(db, "demo_a", "Round 1", {qid: "C" for qid in question_ids})
    with pytest.raises(WorkflowError):
        submit_revision(db, "demo_a", "Round 1", question_ids[0], "C")


def test_joined_export_has_one_row_per_student_round_question(db):
    df = joined_long_dataframe(db)

    assert len(df) == 36
    assert {
        "student_id",
        "round_id",
        "question_id",
        "original_answer",
        "selected_for_discussion",
        "revised_answer",
    }.issubset(df.columns)
