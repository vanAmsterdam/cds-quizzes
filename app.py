from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # pragma: no cover - optional UI fallback
    st_autorefresh = None

from cds_quizzes.database import get_session_factory
from cds_quizzes.models import (
    PHASE_DONE,
    PHASE_INDIVIDUAL,
    PHASE_REVISION,
    PHASE_SELECT_DISCUSSION,
    QuizSession,
    ROUND0_QUESTION_ID,
)
from cds_quizzes.services import (
    WorkflowError,
    answer_label,
    authenticate_student,
    complete_individual_phase,
    get_answers,
    get_assigned_questions,
    get_individual_drafts,
    get_or_create_real_session,
    get_question,
    get_student,
    is_round0_complete,
    next_unfinished_assignment,
    question_options,
    remaining_seconds,
    save_individual_drafts,
    select_discussion_question,
    submit_revision,
    submit_round0,
)
from cds_quizzes.streamlit_runtime import initialize_streamlit_app_data
from cds_quizzes.timezone import amsterdam_now


TIMER_REFRESH_INTERVAL_MS = 10_000

st.set_page_config(page_title="Classroom Quiz", page_icon=":material/school:", layout="centered")
initialize_streamlit_app_data()


def main() -> None:
    db = get_session_factory()()
    try:
        render_app(db)
    finally:
        db.close()


def render_app(db) -> None:
    if "student_id" not in st.session_state:
        render_login(db)
        return

    student = get_student(db, st.session_state["student_id"])
    if student is None:
        st.session_state.pop("student_id", None)
        st.error("Your session no longer matches a rostered student. Please sign in again.")
        render_login(db)
        return

    with st.sidebar:
        st.caption("Signed in as")
        st.write(f"**{student.student_id}**")
        if student.group_id:
            st.write(f"Group: `{student.group_id}`")
        if st.button("Sign out"):
            for key in list(st.session_state):
                if key.startswith(("orig:", "rev:", "round0:")) or key == "student_id":
                    st.session_state.pop(key, None)
            st.rerun()

    st.title("Classroom Quiz")
    if not is_round0_complete(db, student.student_id):
        render_round0(db, student.student_id)
        return

    render_current_round(db, student.student_id)


def render_login(db) -> None:
    st.title("Classroom Quiz")
    st.write("Enter your sign-in key to begin.")
    with st.form("login_form"):
        key = st.text_input("Sign-in key")
        submitted = st.form_submit_button("Sign in", type="primary")
    if not submitted:
        return
    try:
        student = authenticate_student(db, key)
    except ValueError as exc:
        st.error(str(exc))
        return
    if student is None:
        st.error("Sign-in key not found.")
        return
    db.commit()
    st.session_state["student_id"] = student.student_id
    st.rerun()


def render_round0(db, student_id: str) -> None:
    st.subheader("Round 0: answer check")
    st.write("Submit this practice question before starting the quiz rounds.")
    question = get_question(db, ROUND0_QUESTION_ID)
    if question is None:
        st.error("Round 0 question is not configured.")
        return

    st.markdown(f"**{question.question_text}**")
    value = render_answer_widget(question, f"round0:{student_id}:{question.question_id}", default=None)
    if st.button("Submit Round 0 check", type="primary"):
        try:
            submit_round0(db, student_id, value or "")
            db.commit()
            st.success("Round 0 submitted.")
            st.rerun()
        except WorkflowError as exc:
            db.rollback()
            st.error(str(exc))


def render_current_round(db, student_id: str) -> None:
    assignment = next_unfinished_assignment(db, student_id)
    if assignment is None:
        st.success("All assigned rounds are submitted. Thank you.")
        return
    render_real_round(db, student_id, assignment.round_id)


def render_real_round(db, student_id: str, round_id: str) -> None:
    session = db.get(QuizSession, {"student_id": student_id, "round_id": round_id})
    if session is None:
        render_round_start(db, student_id, round_id)
        return

    if session.phase == PHASE_INDIVIDUAL:
        render_individual_phase(db, student_id, round_id, session)
    elif session.phase == PHASE_SELECT_DISCUSSION:
        render_selection_phase(db, student_id, round_id)
    elif session.phase == PHASE_REVISION:
        render_revision_phase(db, student_id, round_id, session)
    elif session.phase == PHASE_DONE:
        render_done_phase(db, student_id, round_id)
    else:
        st.error(f"Unknown session phase: {session.phase}")


def render_round_start(db, student_id: str, round_id: str) -> None:
    st.subheader(f"{round_id}: ready")
    st.write("The 6 minute timer starts only after you press the button below.")
    st.warning("Do not press start until the instructor tells you to begin.")
    if st.button(start_button_label(round_id), type="primary"):
        try:
            get_or_create_real_session(db, student_id, round_id)
            db.commit()
            st.rerun()
        except WorkflowError as exc:
            db.rollback()
            st.error(str(exc))


def start_button_label(round_id: str) -> str:
    normalized = round_id.strip().lower()
    if normalized == "round 2":
        return "Start round 2 now"
    if normalized == "round 1":
        return "Start round 1 now"
    return f"Start {round_id} now"


def render_individual_phase(db, student_id: str, round_id: str, session) -> None:
    questions = get_assigned_questions(db, student_id, round_id)
    drafts = get_individual_drafts(db, student_id, round_id)
    now = amsterdam_now()
    remaining = remaining_seconds(session, now)

    st.subheader(f"{round_id}: individual phase")
    if remaining > 0:
        mins, secs = divmod(remaining, 60)
        st.metric("Time remaining", f"{mins}:{secs:02d}")
        st.progress(remaining / 360)
        if st_autorefresh is not None:
            st_autorefresh(interval=TIMER_REFRESH_INTERVAL_MS, key=f"timer:{student_id}:{round_id}")
    else:
        st.warning("Time is up. Saving the answers currently on this page.")
        submit_individual_from_widgets(db, student_id, round_id, questions)
        return

    st.write("Answer all six questions. Answers are auto-saved until you submit or time expires.")
    for item in questions:
        render_question_block(item.order, item.question)
        render_answer_widget(
            item.question,
            original_widget_key(student_id, round_id, item.question.question_id),
            default=drafts.get(item.question.question_id, ""),
        )

    current_answers = collect_individual_answers_from_widgets(student_id, round_id, questions)
    if not persist_individual_drafts_if_changed(db, student_id, round_id, current_answers):
        return

    if st.button("Submit original answers", type="primary"):
        submit_individual_from_widgets(db, student_id, round_id, questions)


def submit_individual_from_widgets(db, student_id: str, round_id: str, questions) -> None:
    answers = collect_individual_answers_from_widgets(student_id, round_id, questions)
    try:
        complete_individual_phase(db, student_id, round_id, answers)
        db.commit()
        clear_widget_prefix(f"orig:{student_id}:{round_id}:")
        st.rerun()
    except WorkflowError as exc:
        db.rollback()
        st.error(str(exc))


def collect_individual_answers_from_widgets(student_id: str, round_id: str, questions) -> dict[str, str | None]:
    answers: dict[str, str | None] = {}
    for item in questions:
        key = original_widget_key(student_id, round_id, item.question.question_id)
        answers[item.question.question_id] = st.session_state[key] if key in st.session_state else None
    return answers


def persist_individual_drafts_if_changed(
    db,
    student_id: str,
    round_id: str,
    answers: dict[str, str | None],
) -> bool:
    if all(value is None for value in answers.values()):
        return True

    snapshot_key = f"draft_snapshot:{student_id}:{round_id}"
    snapshot = tuple(sorted(answers.items()))
    if st.session_state.get(snapshot_key) == snapshot:
        return True

    try:
        save_individual_drafts(db, student_id, round_id, answers)
        db.commit()
        st.session_state[snapshot_key] = snapshot
        return True
    except WorkflowError as exc:
        db.rollback()
        st.error(str(exc))
        return False


def render_selection_phase(db, student_id: str, round_id: str) -> None:
    st.subheader(f"{round_id}: choose one discussion question")
    questions = get_assigned_questions(db, student_id, round_id)
    answers = get_answers(db, student_id, round_id)

    for item in questions:
        answer = answers.get(item.question.question_id)
        with st.container(border=True):
            render_question_block(item.order, item.question)
            st.caption(f"Original answer: {answer_label(item.question, answer.original_answer if answer else '')}")

    options = [item.question.question_id for item in questions]
    label_by_id = {item.question.question_id: f"Q{item.order}: {item.question.question_text}" for item in questions}
    selected = st.radio(
        "Question to discuss",
        options,
        index=None,
        format_func=lambda qid: label_by_id[qid],
    )
    if st.button("Confirm discussion question", type="primary"):
        if selected is None:
            st.error("Select exactly one question.")
            return
        try:
            select_discussion_question(db, student_id, round_id, selected)
            db.commit()
            st.rerun()
        except WorkflowError as exc:
            db.rollback()
            st.error(str(exc))


def render_revision_phase(db, student_id: str, round_id: str, session) -> None:
    st.subheader(f"{round_id}: revision phase")
    questions = get_assigned_questions(db, student_id, round_id)
    answers = get_answers(db, student_id, round_id)
    selected_id = session.selected_question_id
    if not selected_id:
        st.error("No discussion question is selected.")
        return

    st.write("Only the selected discussion question can be revised.")
    revised_value = ""
    for item in questions:
        answer = answers.get(item.question.question_id)
        is_selected = item.question.question_id == selected_id
        with st.container(border=True):
            render_question_block(item.order, item.question)
            st.caption(f"Original answer: {answer_label(item.question, answer.original_answer if answer else '')}")
            if is_selected:
                st.info("Selected for discussion")
                revised_value = render_answer_widget(
                    item.question,
                    revision_widget_key(student_id, round_id, item.question.question_id),
                    default=answer.original_answer if answer else "",
                )
            else:
                st.caption("Locked")

    if st.button("Submit revised answer", type="primary"):
        try:
            submit_revision(db, student_id, round_id, selected_id, revised_value)
            db.commit()
            clear_widget_prefix(f"rev:{student_id}:{round_id}:")
            st.rerun()
        except WorkflowError as exc:
            db.rollback()
            st.error(str(exc))


def render_done_phase(db, student_id: str, round_id: str) -> None:
    st.subheader(f"{round_id}: submitted")
    st.success("Submitted - thank you.")
    questions = get_assigned_questions(db, student_id, round_id)
    answers = get_answers(db, student_id, round_id)
    for item in questions:
        answer = answers.get(item.question.question_id)
        with st.container(border=True):
            render_question_block(item.order, item.question)
            st.caption(f"Original answer: {answer_label(item.question, answer.original_answer if answer else '')}")
            if answer and answer.selected_for_discussion:
                st.caption(f"Revised answer: {answer_label(item.question, answer.revised_answer)}")


def render_question_block(order: int, question) -> None:
    st.markdown(f"**Question {order}**")
    st.write(question.question_text)


def render_answer_widget(question, key: str, default: str | None) -> str:
    options = question_options(question)
    if options:
        if key not in st.session_state and default in options:
            st.session_state[key] = default
        selected = st.radio(
            "Answer",
            list(options),
            index=None,
            format_func=lambda letter: f"{letter}. {options[letter]}",
            key=key,
        )
        return selected or ""
    if key not in st.session_state and default is not None:
        st.session_state[key] = default
    if question.question_type.lower() == "numeric":
        return st.text_input(
            "Numeric answer",
            key=key,
            placeholder="Use a period as the decimal sign, e.g. 0.25",
            help="Use a period as the decimal sign. Do not use a comma for decimals.",
        )
    return st.text_input("Answer", key=key)


def original_widget_key(student_id: str, round_id: str, question_id: str) -> str:
    return f"orig:{student_id}:{round_id}:{question_id}"


def revision_widget_key(student_id: str, round_id: str, question_id: str) -> str:
    return f"rev:{student_id}:{round_id}:{question_id}"


def clear_widget_prefix(prefix: str) -> None:
    for key in list(st.session_state):
        if key.startswith(prefix):
            st.session_state.pop(key, None)


if __name__ == "__main__":
    main()
