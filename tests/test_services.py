from __future__ import annotations

from datetime import timedelta

import pytest

from cds_quizzes.exports import joined_long_dataframe
from cds_quizzes.models import PHASE_DISCUSSION, PHASE_DONE, PHASE_REVISION, DraftAnswer, QuizSession
from cds_quizzes.services import (
    DISCUSSION_DURATION_SECONDS,
    WorkflowError,
    complete_individual_phase,
    finish_discussion_phase,
    get_answers,
    get_assigned_questions,
    get_individual_drafts,
    get_or_create_real_session,
    monitor_rows,
    next_unfinished_assignment,
    remaining_seconds,
    remaining_discussion_seconds,
    reset_student_state,
    save_individual_drafts,
    select_discussion_question,
    start_discussion_phase,
    submit_revision,
    submit_round0,
)
from cds_quizzes.timezone import amsterdam_now


def answer_all(db, student_id: str, round_id: str) -> list[str]:
    questions = get_assigned_questions(db, student_id, round_id)
    answers = {item.question.question_id: "A" for item in questions}
    complete_individual_phase(db, student_id, round_id, answers)
    db.flush()
    return [item.question.question_id for item in questions]


def finish_discussion(db, student_id: str, round_id: str) -> None:
    start_discussion_phase(db, student_id, round_id)
    session = db.get(QuizSession, {"student_id": student_id, "round_id": round_id})
    session.discussion_started_at = amsterdam_now() - timedelta(seconds=DISCUSSION_DURATION_SECONDS + 1)
    finish_discussion_phase(db, student_id, round_id)
    db.flush()


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
    finish_discussion(db, "demo_a", "Round 1")
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


def test_real_round_session_is_created_only_when_explicitly_started(db):
    assert db.get(QuizSession, {"student_id": "demo_a", "round_id": "Round 1"}) is None

    session = get_or_create_real_session(db, "demo_a", "Round 1")

    assert session.individual_started_at is not None


def test_next_unfinished_assignment_locks_round2_until_round1_done(db):
    assert next_unfinished_assignment(db, "demo_a").round_id == "Round 1"

    question_ids = answer_all(db, "demo_a", "Round 1")
    assert next_unfinished_assignment(db, "demo_a").round_id == "Round 1"

    select_discussion_question(db, "demo_a", "Round 1", question_ids[0])
    assert next_unfinished_assignment(db, "demo_a").round_id == "Round 1"

    finish_discussion(db, "demo_a", "Round 1")
    submit_revision(db, "demo_a", "Round 1", question_ids[0], "B")
    db.flush()
    assert next_unfinished_assignment(db, "demo_a").round_id == "Round 2"


def test_next_unfinished_assignment_returns_none_after_all_rounds_done(db):
    question_ids = answer_all(db, "demo_a", "Round 1")
    select_discussion_question(db, "demo_a", "Round 1", question_ids[0])
    finish_discussion(db, "demo_a", "Round 1")
    submit_revision(db, "demo_a", "Round 1", question_ids[0], "B")

    answer_all(db, "demo_a", "Round 2")
    session = db.get(QuizSession, {"student_id": "demo_a", "round_id": "Round 2"})
    finish_discussion(db, "demo_a", "Round 2")
    submit_revision(db, "demo_a", "Round 2", session.selected_question_id, "B")
    db.flush()

    assert next_unfinished_assignment(db, "demo_a") is None


def test_saved_drafts_are_finalized_when_individual_phase_completes(db):
    questions = get_assigned_questions(db, "demo_a", "Round 1")
    first_id = questions[0].question.question_id
    second_id = questions[1].question.question_id
    save_individual_drafts(db, "demo_a", "Round 1", {first_id: "B", second_id: "A"})
    db.flush()

    complete_individual_phase(db, "demo_a", "Round 1", {item.question.question_id: None for item in questions})
    db.flush()

    answers = get_answers(db, "demo_a", "Round 1")
    assert answers[first_id].original_answer == "B"
    assert answers[second_id].original_answer == "A"
    assert answers[first_id].original_saved_at is not None
    assert get_individual_drafts(db, "demo_a", "Round 1") == {}


def test_current_widget_values_override_saved_drafts_on_submit(db):
    questions = get_assigned_questions(db, "demo_a", "Round 1")
    first_id = questions[0].question.question_id
    save_individual_drafts(db, "demo_a", "Round 1", {first_id: "B"})

    complete_individual_phase(db, "demo_a", "Round 1", {first_id: "C"})
    db.flush()

    answers = get_answers(db, "demo_a", "Round 1")
    assert answers[first_id].original_answer == "C"


def test_round2_skips_selection_and_randomly_assigns_one_question(db):
    answer_all(db, "demo_a", "Round 2")
    session = db.get(QuizSession, {"student_id": "demo_a", "round_id": "Round 2"})

    assigned_ids = {item.question.question_id for item in get_assigned_questions(db, "demo_a", "Round 2")}
    assert session.phase == PHASE_DISCUSSION
    assert session.selected_question_id in assigned_ids
    assert session.discussion_started_at is None


def test_discussion_phase_must_run_before_revision_opens(db):
    question_ids = answer_all(db, "demo_a", "Round 1")
    select_discussion_question(db, "demo_a", "Round 1", question_ids[0])
    session = db.get(QuizSession, {"student_id": "demo_a", "round_id": "Round 1"})
    assert session.phase == PHASE_DISCUSSION

    with pytest.raises(WorkflowError, match="Revision is not available"):
        submit_revision(db, "demo_a", "Round 1", question_ids[0], "B")

    start_discussion_phase(db, "demo_a", "Round 1")
    assert 0 <= remaining_discussion_seconds(session) <= DISCUSSION_DURATION_SECONDS
    with pytest.raises(WorkflowError, match="still in progress"):
        finish_discussion_phase(db, "demo_a", "Round 1")

    session.discussion_started_at = amsterdam_now() - timedelta(seconds=DISCUSSION_DURATION_SECONDS + 1)
    finish_discussion_phase(db, "demo_a", "Round 1")
    assert session.phase == PHASE_REVISION


def test_done_phase_rejects_answer_edits(db):
    question_ids = answer_all(db, "demo_a", "Round 1")
    select_discussion_question(db, "demo_a", "Round 1", question_ids[0])
    finish_discussion(db, "demo_a", "Round 1")
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

    assert len(df) == 108
    assert {
        "student_id",
        "round_id",
        "question_id",
        "original_answer",
        "selected_for_discussion",
        "revised_answer",
    }.issubset(df.columns)


def test_reset_student_state_removes_sessions_and_answers_only_for_that_student(db):
    submit_round0(db, "demo_a", "A")
    draft_question = get_assigned_questions(db, "demo_a", "Round 2")[0].question
    save_individual_drafts(db, "demo_a", "Round 2", {draft_question.question_id: "A"})
    question_ids = answer_all(db, "demo_a", "Round 1")
    select_discussion_question(db, "demo_a", "Round 1", question_ids[0])
    finish_discussion(db, "demo_a", "Round 1")
    submit_revision(db, "demo_a", "Round 1", question_ids[0], "B")

    submit_round0(db, "demo_b", "A")
    db.flush()

    reset_student_state(db, "demo_a")
    db.flush()

    demo_a = next(row for row in monitor_rows(db) if row["student_id"] == "demo_a")
    demo_b = next(row for row in monitor_rows(db) if row["student_id"] == "demo_b")
    assert demo_a["signed_in"] is False
    assert demo_a["round0_done"] is False
    assert demo_a["original_answers"] == 0
    assert demo_a["revised_answers"] == 0
    assert len(get_assigned_questions(db, "demo_a", "Round 1")) == 6
    assert demo_b["round0_done"] is True
    assert db.query(DraftAnswer).filter_by(student_id="demo_a").count() == 0
