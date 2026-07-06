from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from cds_quizzes.config import DEFAULT_WORKBOOK_PATH
from cds_quizzes.database import seed_round0_question
from cds_quizzes.importers import import_form_questions, import_roster, import_workbook
from cds_quizzes.models import Assignment, Base, FormQuestion, Student


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "generate_roster_materials.py"
CLASS_ROSTER = ROOT / "data" / "class_roster.csv"
CLASS_FORM_QUESTIONS = ROOT / "data" / "class_form_questions.csv"
CLASS_SLIPS_HTML = ROOT / "data" / "class_slips.html"
CLASS_SLIPS_INDEX = ROOT / "data" / "class_slips_index.csv"


def test_roster_material_generator_outputs_valid_default_files(tmp_path: Path):
    subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--out-dir",
            str(tmp_path),
            "--prefix",
            "private_test",
            "--seed",
            "1234",
        ],
        check=True,
    )

    roster_path = tmp_path / "private_test_roster.csv"
    form_questions_path = tmp_path / "private_test_form_questions.csv"
    slips_index_path = tmp_path / "private_test_slips_index.csv"
    slips_html_path = tmp_path / "private_test_slips.html"
    assert roster_path.exists()
    assert form_questions_path.exists()
    assert slips_index_path.exists()
    assert slips_html_path.exists()

    with roster_path.open(newline="", encoding="utf-8") as handle:
        roster_rows = list(csv.DictReader(handle))
    with form_questions_path.open(newline="", encoding="utf-8") as handle:
        form_rows = list(csv.DictReader(handle))
    with slips_index_path.open(newline="", encoding="utf-8") as handle:
        slip_rows = list(csv.DictReader(handle))

    assert len(slip_rows) == 40
    assert len(roster_rows) == 80

    sign_in_keys = {row["sign_in_key"] for row in slip_rows}
    assert len(sign_in_keys) == 40
    assert all(key.isalpha() and key.islower() for key in sign_in_keys)

    real_rows = [row for row in slip_rows if row["kind"] == "real"]
    test_rows = [row for row in slip_rows if row["kind"] == "test"]
    assert len(real_rows) == 28
    assert len(test_rows) == 12

    real_group_sizes = {
        group_id: sum(1 for row in real_rows if row["group_id"] == group_id)
        for group_id in sorted({row["group_id"] for row in real_rows})
    }
    assert real_group_sizes == {
        "teama": 3,
        "teamb": 3,
        "teamc": 3,
        "teamd": 3,
        "teame": 3,
        "teamf": 3,
        "teamg": 3,
        "teamh": 3,
        "teami": 4,
    }

    assert {row["sign_in_key"] for row in test_rows} == {
        "testaa",
        "testab",
        "testac",
        "testba",
        "testbb",
        "testbc",
        "testca",
        "testcb",
        "testcc",
        "testda",
        "testdb",
        "testdc",
    }

    roster_key_rounds = {(row["sign_in_key"], row["round_id"]) for row in roster_rows}
    assert all((key, "Round 1") in roster_key_rounds and (key, "Round 2") in roster_key_rounds for key in sign_in_keys)

    assert len(form_rows) == 480
    form_keys = {(row["round_id"], row["question_set_id"]) for row in form_rows}
    assert len(form_keys) == 80
    for form_key in form_keys:
        rows = [row for row in form_rows if (row["round_id"], row["question_set_id"]) == form_key]
        assert len(rows) == 6
        assert sorted(row["stratum"] for row in rows) == ["easier", "easier", "harder", "harder", "hardest", "hardest"]
        assert sorted(int(row["question_order"]) for row in rows) == [1, 2, 3, 4, 5, 6]

    first_group_questions: set[str] | None = None
    for group_id in sorted({row["group_id"] for row in form_rows}):
        group_questions = {row["question_id"] for row in form_rows if row["group_id"] == group_id}
        assert len(group_questions) == 36
        if first_group_questions is None:
            first_group_questions = group_questions
        else:
            assert group_questions == first_group_questions

    for group_id, role in {(row["group_id"], row["role"]) for row in form_rows}:
        role_questions = [row["question_id"] for row in form_rows if row["group_id"] == group_id and row["role"] == role]
        assert len(role_questions) == 12
        assert len(set(role_questions)) == 12

    roster_forms = {(row["round_id"], row["question_set_id"]) for row in roster_rows}
    assert roster_forms == form_keys
    assert "testaa" in slips_html_path.read_text(encoding="utf-8")

    engine = create_engine(f"sqlite:///{tmp_path / 'generated_roster.sqlite'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    session = Session()
    try:
        seed_round0_question(session)
        import_workbook(session, DEFAULT_WORKBOOK_PATH)
        import_form_questions(session, form_questions_path)
        import_roster(session, roster_path)
        session.commit()

        student_count = session.execute(select(func.count()).select_from(Student)).scalar_one()
        assignment_count = session.execute(select(func.count()).select_from(Assignment)).scalar_one()
        form_question_count = session.execute(select(func.count()).select_from(FormQuestion)).scalar_one()
    finally:
        session.close()
        engine.dispose()

    assert student_count == 40
    assert assignment_count == 80
    assert form_question_count == 516


def test_bundled_class_roster_imports_cleanly(tmp_path: Path):
    assert CLASS_ROSTER.exists()
    assert CLASS_FORM_QUESTIONS.exists()
    assert CLASS_SLIPS_HTML.exists()
    assert CLASS_SLIPS_INDEX.exists()

    with CLASS_FORM_QUESTIONS.open(newline="", encoding="utf-8") as handle:
        form_rows = list(csv.DictReader(handle))
    with CLASS_ROSTER.open(newline="", encoding="utf-8") as handle:
        roster_rows = list(csv.DictReader(handle))

    assert len(roster_rows) == 80
    assert len(form_rows) == 480
    assert {row["sign_in_key"] for row in roster_rows if row["sign_in_key"].startswith("test")} == {
        "testaa",
        "testab",
        "testac",
        "testba",
        "testbb",
        "testbc",
        "testca",
        "testcb",
        "testcc",
        "testda",
        "testdb",
        "testdc",
    }

    for form_key in {(row["round_id"], row["question_set_id"]) for row in form_rows}:
        rows = [row for row in form_rows if (row["round_id"], row["question_set_id"]) == form_key]
        assert sorted(row["stratum"] for row in rows) == ["easier", "easier", "harder", "harder", "hardest", "hardest"]

    first_group_questions: set[str] | None = None
    for group_id in sorted({row["group_id"] for row in form_rows}):
        group_questions = {row["question_id"] for row in form_rows if row["group_id"] == group_id}
        assert len(group_questions) == 36
        if first_group_questions is None:
            first_group_questions = group_questions
        else:
            assert group_questions == first_group_questions

    engine = create_engine(f"sqlite:///{tmp_path / 'bundled_roster.sqlite'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    session = Session()
    try:
        seed_round0_question(session)
        import_workbook(session, DEFAULT_WORKBOOK_PATH)
        import_form_questions(session, CLASS_FORM_QUESTIONS)
        import_roster(session, CLASS_ROSTER)
        session.commit()

        student_count = session.execute(select(func.count()).select_from(Student)).scalar_one()
        assignment_count = session.execute(select(func.count()).select_from(Assignment)).scalar_one()
    finally:
        session.close()
        engine.dispose()

    assert student_count == 40
    assert assignment_count == 80
