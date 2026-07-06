from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamlit as st
from sqlalchemy import func, select

from cds_quizzes.admin_auth import require_admin
from cds_quizzes.bootstrap import import_default_class_data
from cds_quizzes.config import (
    DEFAULT_CLASS_FORM_QUESTIONS_PATH,
    DEFAULT_CLASS_ROSTER_PATH,
    DEFAULT_SAMPLE_ROSTER_PATH,
    DEFAULT_WORKBOOK_PATH,
)
from cds_quizzes.database import get_session_factory
from cds_quizzes.exports import (
    answers_dataframe,
    dataframe_to_csv_bytes,
    joined_long_dataframe,
    round0_monitor_dataframe,
    sessions_dataframe,
)
from cds_quizzes.importers import import_form_questions, import_roster, import_workbook
from cds_quizzes.models import Answer, Assignment, DraftAnswer, FormQuestion, QuizSession, Student
from cds_quizzes.services import WorkflowError, reset_student_state
from cds_quizzes.streamlit_runtime import initialize_streamlit_app_data


def run_import(db, importer, source, message: str) -> None:
    try:
        summary = importer(db, source)
        db.commit()
        st.success(f"{message} {summary}")
    except Exception as exc:
        db.rollback()
        st.error(str(exc))


def run_default_class_import(db) -> None:
    try:
        workbook_summary, form_summary, roster_summary = import_default_class_data(db)
        db.commit()
        st.success(
            "Bundled classroom setup imported. "
            f"Workbook: {workbook_summary}; forms: {form_summary}; roster: {roster_summary}"
        )
    except Exception as exc:
        db.rollback()
        st.error(str(exc))


def export_download(filename: str, df) -> None:
    st.download_button(
        filename,
        dataframe_to_csv_bytes(df),
        file_name=filename,
        mime="text/csv",
        width="stretch",
    )


def count_rows(db, model) -> int:
    return db.execute(select(func.count()).select_from(model)).scalar_one()


def student_ids(db) -> list[str]:
    return list(db.execute(select(Student.student_id).order_by(Student.student_id)).scalars())


def run_student_reset(db, student_id: str, confirmation: str) -> None:
    if confirmation != student_id:
        st.error("Type the exact student_id to confirm the reset.")
        return
    try:
        reset_student_state(db, student_id)
        db.commit()
        st.success(f"Reset session and answer state for {student_id}.")
    except WorkflowError as exc:
        db.rollback()
        st.error(str(exc))
    except Exception as exc:
        db.rollback()
        st.error(f"Reset failed: {exc}")


st.set_page_config(page_title="Admin", page_icon=":material/admin_panel_settings:", layout="wide")
initialize_streamlit_app_data()
require_admin()

st.title("Admin")
db = get_session_factory()()
try:
    tabs = st.tabs(["Setup", "Resets", "Exports", "Status"])
    with tabs[0]:
        st.subheader("Bundled classroom setup")
        if DEFAULT_CLASS_FORM_QUESTIONS_PATH.exists() and DEFAULT_CLASS_ROSTER_PATH.exists():
            st.caption(
                f"Bundled generated forms: `{DEFAULT_CLASS_FORM_QUESTIONS_PATH.relative_to(ROOT)}`; "
                f"bundled roster: `{DEFAULT_CLASS_ROSTER_PATH.relative_to(ROOT)}`"
            )
            if st.button("Import bundled classroom forms and roster", type="primary"):
                run_default_class_import(db)
        else:
            st.warning("Bundled classroom roster files are not present in this deployment.")

        st.subheader("Question bank")
        if DEFAULT_WORKBOOK_PATH.exists():
            st.caption(f"Bundled workbook: `{DEFAULT_WORKBOOK_PATH.relative_to(ROOT)}`")
            if st.button("Import bundled workbook"):
                run_import(db, import_workbook, DEFAULT_WORKBOOK_PATH, "Workbook imported.")
        uploaded_workbook = st.file_uploader("Upload replacement workbook", type=["xlsx"], key="workbook_upload")
        if uploaded_workbook and st.button("Import uploaded workbook"):
            run_import(db, import_workbook, uploaded_workbook, "Workbook imported.")

        st.subheader("Generated team forms")
        st.write("Import the generated form-question CSV before importing its matching roster CSV.")
        uploaded_form_questions = st.file_uploader(
            "Upload generated form-question CSV",
            type=["csv"],
            key="form_questions_upload",
        )
        if uploaded_form_questions and st.button("Import generated form-question CSV"):
            run_import(db, import_form_questions, uploaded_form_questions, "Generated form questions imported.")

        st.subheader("Roster")
        if DEFAULT_SAMPLE_ROSTER_PATH.exists():
            st.caption(f"Sample roster: `{DEFAULT_SAMPLE_ROSTER_PATH.relative_to(ROOT)}`")
            if st.button("Import sample roster"):
                run_import(db, import_roster, DEFAULT_SAMPLE_ROSTER_PATH, "Sample roster imported.")
        uploaded_roster = st.file_uploader("Upload roster CSV", type=["csv"], key="roster_upload")
        if uploaded_roster and st.button("Import roster CSV"):
            run_import(db, import_roster, uploaded_roster, "Roster imported.")

    with tabs[1]:
        st.subheader("Reset one student")
        st.write("This deletes that student's sessions and answers, including Round 0, but keeps the roster and assignments.")
        students = student_ids(db)
        if not students:
            st.info("No students are loaded.")
        else:
            selected_student = st.selectbox("Student", students)
            confirmation = st.text_input("Type the student_id to confirm", key="reset_student_confirmation")
            if st.button("Reset selected student", type="primary"):
                run_student_reset(db, selected_student, confirmation)

    with tabs[2]:
        st.subheader("CSV exports")
        export_download("sessions.csv", sessions_dataframe(db))
        export_download("answers.csv", answers_dataframe(db))
        export_download("joined_long.csv", joined_long_dataframe(db))
        export_download("round0_monitor.csv", round0_monitor_dataframe(db))

    with tabs[3]:
        st.subheader("Database status")
        counts = {
            "students": count_rows(db, Student),
            "assignments": count_rows(db, Assignment),
            "form_questions": count_rows(db, FormQuestion),
            "sessions": count_rows(db, QuizSession),
            "answers": count_rows(db, Answer),
            "draft_answers": count_rows(db, DraftAnswer),
        }
        st.dataframe(
            [{"table": table, "rows": rows} for table, rows in counts.items()],
            width="stretch",
            hide_index=True,
        )
finally:
    db.close()
