from __future__ import annotations

import pytest
from sqlalchemy import func, select

from cds_quizzes.models import FormQuestion
from cds_quizzes.services import get_assigned_questions


def test_workbook_import_has_six_questions_per_round_form(db):
    counts = db.execute(
        select(FormQuestion.round_id, FormQuestion.question_set_id, func.count())
        .group_by(FormQuestion.round_id, FormQuestion.question_set_id)
        .order_by(FormQuestion.round_id, FormQuestion.question_set_id)
    ).all()

    assert len(counts) == 6
    assert all(count == 6 for _, _, count in counts)


def test_sample_roster_assignments_load_expected_questions(db):
    questions = get_assigned_questions(db, "demo_a", "Round 1")

    assert len(questions) == 6
    assert [item.order for item in questions] == [1, 2, 3, 4, 5, 6]


def test_sample_roster_includes_three_demo_groups(db):
    for student_id in ("demo_a", "demo_d", "demo_g"):
        assert len(get_assigned_questions(db, student_id, "Round 1")) == 6
