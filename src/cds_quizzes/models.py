from __future__ import annotations

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


ROUND0_ID = "Round 0"
ROUND0_QUESTION_ID = "ROUND0_CHECK"

PHASE_INDIVIDUAL = "INDIVIDUAL"
PHASE_SELECT_DISCUSSION = "SELECT_DISCUSSION"
PHASE_REVISION = "REVISION"
PHASE_DONE = "DONE"

ALL_PHASES = {
    PHASE_INDIVIDUAL,
    PHASE_SELECT_DISCUSSION,
    PHASE_REVISION,
    PHASE_DONE,
}


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    student_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sign_in_key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    group_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    last_seen_at: Mapped[object | None] = mapped_column(DateTime)


class Question(Base):
    __tablename__ = "questions"

    question_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    difficulty: Mapped[int | None] = mapped_column(Integer)
    band: Mapped[str | None] = mapped_column(String(128))
    topic: Mapped[str | None] = mapped_column(String(256))
    question_type: Mapped[str] = mapped_column(String(64), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    option_a: Mapped[str | None] = mapped_column(Text)
    option_b: Mapped[str | None] = mapped_column(Text)
    option_c: Mapped[str | None] = mapped_column(Text)
    option_d: Mapped[str | None] = mapped_column(Text)
    correct_answer: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    instructor_note: Mapped[str | None] = mapped_column(Text)


class FormQuestion(Base):
    __tablename__ = "form_questions"

    round_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    question_set_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    question_order: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.question_id"), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("round_id", "question_set_id", "question_id", name="uq_form_question_question"),
    )


class Assignment(Base):
    __tablename__ = "assignments"

    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"), primary_key=True)
    round_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    question_set_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class QuizSession(Base):
    __tablename__ = "sessions"

    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"), primary_key=True)
    round_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default=PHASE_INDIVIDUAL)
    individual_started_at: Mapped[object | None] = mapped_column(DateTime)
    individual_submitted_at: Mapped[object | None] = mapped_column(DateTime)
    selected_question_id: Mapped[str | None] = mapped_column(String(64))
    selection_confirmed_at: Mapped[object | None] = mapped_column(DateTime)
    revision_submitted_at: Mapped[object | None] = mapped_column(DateTime)
    done_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Answer(Base):
    __tablename__ = "answers"

    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"), primary_key=True)
    round_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.question_id"), primary_key=True)
    original_answer: Mapped[str | None] = mapped_column(Text)
    original_saved_at: Mapped[object | None] = mapped_column(DateTime)
    selected_for_discussion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revised_answer: Mapped[str | None] = mapped_column(Text)
    revised_saved_at: Mapped[object | None] = mapped_column(DateTime)
