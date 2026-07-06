from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ROUND0_ID, Answer, Assignment, FormQuestion, Question, QuizSession, Student
from .services import monitor_rows


def sessions_dataframe(db: Session) -> pd.DataFrame:
    sessions = db.execute(select(QuizSession).order_by(QuizSession.student_id, QuizSession.round_id)).scalars()
    return pd.DataFrame(
        [
            {
                "student_id": row.student_id,
                "round_id": row.round_id,
                "phase": row.phase,
                "individual_started_at": row.individual_started_at,
                "individual_submitted_at": row.individual_submitted_at,
                "selected_question_id": row.selected_question_id,
                "selection_confirmed_at": row.selection_confirmed_at,
                "revision_submitted_at": row.revision_submitted_at,
                "done_at": row.done_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in sessions
        ]
    )


def answers_dataframe(db: Session, include_round0: bool = True) -> pd.DataFrame:
    stmt = select(Answer).order_by(Answer.student_id, Answer.round_id, Answer.question_id)
    answers = db.execute(stmt).scalars()
    rows = []
    for row in answers:
        if not include_round0 and row.round_id == ROUND0_ID:
            continue
        rows.append(
            {
                "student_id": row.student_id,
                "round_id": row.round_id,
                "question_id": row.question_id,
                "original_answer": row.original_answer,
                "original_saved_at": row.original_saved_at,
                "selected_for_discussion": row.selected_for_discussion,
                "revised_answer": row.revised_answer,
                "revised_saved_at": row.revised_saved_at,
            }
        )
    return pd.DataFrame(rows)


def joined_long_dataframe(db: Session) -> pd.DataFrame:
    rows = db.execute(
        select(Student, Assignment, FormQuestion, Question, Answer)
        .join(Assignment, Assignment.student_id == Student.student_id)
        .join(
            FormQuestion,
            (FormQuestion.round_id == Assignment.round_id)
            & (FormQuestion.question_set_id == Assignment.question_set_id),
        )
        .join(Question, Question.question_id == FormQuestion.question_id)
        .outerjoin(
            Answer,
            (Answer.student_id == Student.student_id)
            & (Answer.round_id == Assignment.round_id)
            & (Answer.question_id == Question.question_id),
        )
        .order_by(Student.student_id, Assignment.round_id, FormQuestion.question_order)
    ).all()
    return pd.DataFrame(
        [
            {
                "student_id": student.student_id,
                "group_id": student.group_id,
                "round_id": assignment.round_id,
                "question_set_id": assignment.question_set_id,
                "question_order": form_question.question_order,
                "question_id": question.question_id,
                "difficulty": question.difficulty,
                "topic": question.topic,
                "question_type": question.question_type,
                "question_text": question.question_text,
                "original_answer": answer.original_answer if answer else None,
                "original_saved_at": answer.original_saved_at if answer else None,
                "selected_for_discussion": bool(answer.selected_for_discussion) if answer else False,
                "revised_answer": answer.revised_answer if answer else None,
                "revised_saved_at": answer.revised_saved_at if answer else None,
                "correct_answer": question.correct_answer,
                "rationale": question.rationale,
            }
            for student, assignment, form_question, question, answer in rows
        ]
    )


def round0_monitor_dataframe(db: Session) -> pd.DataFrame:
    return pd.DataFrame(monitor_rows(db))


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")
