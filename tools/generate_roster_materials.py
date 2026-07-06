from __future__ import annotations

import argparse
import csv
import html
import random
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


ROUNDS = ("Round 1", "Round 2")
ROUND_SUFFIX = {"Round 1": "r1", "Round 2": "r2"}
REAL_GROUPS = ("teama", "teamb", "teamc", "teamd", "teame", "teamf", "teamg", "teamh", "teami")
TEST_GROUPS = ("testa", "testb", "testc", "testd")
CORE_ROLES = ("a", "b", "c")
EXTRA_ROLES = ("d",)
ID_ALPHABET = "abcdefghjkmnpqrstuvwxyz"
WORKBOOK_PATH = Path("data/causal_dag_peer_discussion_question_bank.xlsx")
CORE_SHEET = "Core 36 forms"
STRATA = ("easier", "harder", "hardest")
STRATUM_BY_DIFFICULTY = {
    1: "easier",
    2: "easier",
    3: "harder",
    4: "hardest",
    5: "hardest",
}


@dataclass(frozen=True)
class Participant:
    kind: str
    group_id: str
    role: str
    student_id: str
    sign_in_key: str


@dataclass(frozen=True)
class QuestionInfo:
    question_id: str
    difficulty: int
    stratum: str


@dataclass(frozen=True)
class FormQuestionAssignment:
    group_id: str
    role: str
    round_id: str
    question_set_id: str
    question_order: int
    question: QuestionInfo


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate private classroom roster CSV and printable login slips.")
    parser.add_argument("--out-dir", type=Path, default=Path("data"), help="Directory for generated private files.")
    parser.add_argument("--prefix", default="private_class", help="Filename prefix for generated outputs.")
    parser.add_argument("--workbook", type=Path, default=WORKBOOK_PATH, help="Question-bank workbook path.")
    parser.add_argument("--real-count", type=int, default=28, choices=(26, 27, 28), help="Number of real student slips.")
    parser.add_argument("--test-groups", type=int, default=4, choices=range(0, len(TEST_GROUPS) + 1))
    parser.add_argument("--id-length", type=int, default=6)
    parser.add_argument("--seed", type=int, default=None, help="Optional seed for reproducible real IDs and forms.")
    args = parser.parse_args()

    rng: random.Random | secrets.SystemRandom
    rng = random.Random(args.seed) if args.seed is not None else secrets.SystemRandom()
    question_pool = load_question_pool(args.workbook)
    participants = build_participants(
        real_count=args.real_count,
        test_group_count=args.test_groups,
        id_length=args.id_length,
        rng=rng,
    )
    form_questions = build_form_question_assignments(participants, question_pool, rng)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    roster_path = args.out_dir / f"{args.prefix}_roster.csv"
    form_questions_path = args.out_dir / f"{args.prefix}_form_questions.csv"
    slips_index_path = args.out_dir / f"{args.prefix}_slips_index.csv"
    slips_html_path = args.out_dir / f"{args.prefix}_slips.html"

    write_roster_csv(roster_path, participants)
    write_form_questions_csv(form_questions_path, form_questions)
    write_slips_index_csv(slips_index_path, participants)
    write_slips_html(slips_html_path, participants, real_count=args.real_count)

    print(f"Wrote {roster_path}")
    print(f"Wrote {form_questions_path}")
    print(f"Wrote {slips_index_path}")
    print(f"Wrote {slips_html_path}")


def load_question_pool(workbook_path: Path) -> dict[str, list[QuestionInfo]]:
    core = pd.read_excel(workbook_path, sheet_name=CORE_SHEET).dropna(how="all")
    missing = {"ID", "Difficulty"} - set(core.columns)
    if missing:
        raise ValueError(f"{CORE_SHEET} is missing columns: {', '.join(sorted(missing))}")

    questions_by_id: dict[str, QuestionInfo] = {}
    for _, row in core.iterrows():
        question_id = str(row["ID"]).strip()
        if not question_id:
            continue
        difficulty = int(row["Difficulty"])
        stratum = STRATUM_BY_DIFFICULTY.get(difficulty)
        if stratum is None:
            raise ValueError(f"Question {question_id} has unsupported difficulty {difficulty}.")
        existing = questions_by_id.get(question_id)
        question = QuestionInfo(question_id=question_id, difficulty=difficulty, stratum=stratum)
        if existing is not None and existing != question:
            raise ValueError(f"Question {question_id} appears with inconsistent difficulty.")
        questions_by_id[question_id] = question

    if len(questions_by_id) != 36:
        raise ValueError(f"Expected 36 unique core questions, found {len(questions_by_id)}.")

    pool = {stratum: [] for stratum in STRATA}
    for question in sorted(questions_by_id.values(), key=lambda item: item.question_id):
        pool[question.stratum].append(question)

    bad_counts = {stratum: len(questions) for stratum, questions in pool.items() if len(questions) != 12}
    if bad_counts:
        raise ValueError(f"Expected 12 questions per stratum, found {bad_counts}.")
    return pool


def build_participants(
    real_count: int,
    test_group_count: int,
    id_length: int,
    rng: random.Random | secrets.SystemRandom,
) -> list[Participant]:
    if real_count not in (26, 27, 28):
        raise ValueError("real_count must be 26, 27, or 28.")
    if not 0 <= test_group_count <= len(TEST_GROUPS):
        raise ValueError(f"test_group_count must be between 0 and {len(TEST_GROUPS)}.")
    if id_length < 5:
        raise ValueError("id_length must be at least 5.")

    reserved = predictable_test_ids(test_group_count)
    participants: list[Participant] = []
    used_ids: set[str] = set(reserved)

    for group_id, roles in real_group_roles(real_count):
        for role in roles:
            sign_in_key = random_id(rng, used_ids, id_length)
            participants.append(
                Participant(
                    kind="real",
                    group_id=group_id,
                    role=role,
                    student_id=sign_in_key,
                    sign_in_key=sign_in_key,
                )
            )

    for group_id in TEST_GROUPS[:test_group_count]:
        group_letter = group_id.removeprefix("test")
        for role in CORE_ROLES:
            sign_in_key = f"test{group_letter}{role}"
            participants.append(
                Participant(
                    kind="test",
                    group_id=group_id,
                    role=role,
                    student_id=sign_in_key,
                    sign_in_key=sign_in_key,
                )
            )

    return participants


def build_form_question_assignments(
    participants: list[Participant],
    question_pool: dict[str, list[QuestionInfo]],
    rng: random.Random | secrets.SystemRandom,
) -> list[FormQuestionAssignment]:
    rows: list[FormQuestionAssignment] = []
    for group_id in sorted({participant.group_id for participant in participants}):
        group_participants = [participant for participant in participants if participant.group_id == group_id]
        core_batches = build_core_role_batches(question_pool, rng)
        extra_batches = {role: build_extra_role_batches(question_pool, rng) for role in EXTRA_ROLES}
        for participant in group_participants:
            if participant.role in CORE_ROLES:
                batches = core_batches[participant.role]
            else:
                batches = extra_batches[participant.role]
            for round_id in ROUNDS:
                for order, question in enumerate(batches[round_id], start=1):
                    rows.append(
                        FormQuestionAssignment(
                            group_id=participant.group_id,
                            role=participant.role,
                            round_id=round_id,
                            question_set_id=question_set_id(participant.group_id, participant.role, round_id),
                            question_order=order,
                            question=question,
                        )
                    )
    return rows


def build_core_role_batches(
    question_pool: dict[str, list[QuestionInfo]],
    rng: random.Random | secrets.SystemRandom,
) -> dict[str, dict[str, list[QuestionInfo]]]:
    batch_keys = [(role, round_id) for role in CORE_ROLES for round_id in ROUNDS]
    batches = {role: {round_id: [] for round_id in ROUNDS} for role in CORE_ROLES}
    for stratum in STRATA:
        questions = shuffled(question_pool[stratum], rng)
        for index, (role, round_id) in enumerate(batch_keys):
            batches[role][round_id].extend(questions[index * 2 : index * 2 + 2])
    for role, round_id in batch_keys:
        rng.shuffle(batches[role][round_id])
    return batches


def build_extra_role_batches(
    question_pool: dict[str, list[QuestionInfo]],
    rng: random.Random | secrets.SystemRandom,
) -> dict[str, list[QuestionInfo]]:
    batches = {round_id: [] for round_id in ROUNDS}
    for stratum in STRATA:
        questions = shuffled(question_pool[stratum], rng)[:4]
        batches["Round 1"].extend(questions[:2])
        batches["Round 2"].extend(questions[2:])
    for round_id in ROUNDS:
        rng.shuffle(batches[round_id])
    return batches


def real_group_roles(real_count: int) -> Iterable[tuple[str, tuple[str, ...]]]:
    remaining = real_count
    for group_id in REAL_GROUPS:
        if remaining <= 0:
            return
        if group_id == REAL_GROUPS[-1]:
            size = remaining
        else:
            size = min(3, remaining)
        if size < 1 or size > 4:
            raise ValueError(f"Cannot assign {real_count} students into supported group sizes.")
        yield group_id, tuple(("a", "b", "c", "d")[:size])
        remaining -= size


def predictable_test_ids(test_group_count: int) -> set[str]:
    ids: set[str] = set()
    for group_id in TEST_GROUPS[:test_group_count]:
        group_letter = group_id.removeprefix("test")
        ids.update(f"test{group_letter}{role}" for role in CORE_ROLES)
    return ids


def random_id(rng: random.Random | secrets.SystemRandom, used_ids: set[str], length: int) -> str:
    while True:
        value = "".join(rng.choice(ID_ALPHABET) for _ in range(length))
        if value not in used_ids and not value.startswith("test"):
            used_ids.add(value)
            return value


def question_set_id(group_id: str, role: str, round_id: str) -> str:
    return f"{group_id}_{role}_{ROUND_SUFFIX[round_id]}"


def shuffled(items: Iterable[QuestionInfo], rng: random.Random | secrets.SystemRandom) -> list[QuestionInfo]:
    values = list(items)
    rng.shuffle(values)
    return values


def write_roster_csv(path: Path, participants: Iterable[Participant]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("student_id", "sign_in_key", "group_id", "round_id", "question_set_id"),
        )
        writer.writeheader()
        for participant in participants:
            for round_id in ROUNDS:
                writer.writerow(
                    {
                        "student_id": participant.student_id,
                        "sign_in_key": participant.sign_in_key,
                        "group_id": participant.group_id,
                        "round_id": round_id,
                        "question_set_id": question_set_id(participant.group_id, participant.role, round_id),
                    }
                )


def write_form_questions_csv(path: Path, assignments: Iterable[FormQuestionAssignment]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "round_id",
                "question_set_id",
                "question_order",
                "question_id",
                "group_id",
                "role",
                "difficulty",
                "stratum",
            ),
        )
        writer.writeheader()
        for assignment in assignments:
            writer.writerow(
                {
                    "round_id": assignment.round_id,
                    "question_set_id": assignment.question_set_id,
                    "question_order": assignment.question_order,
                    "question_id": assignment.question.question_id,
                    "group_id": assignment.group_id,
                    "role": assignment.role,
                    "difficulty": assignment.question.difficulty,
                    "stratum": assignment.question.stratum,
                }
            )


def write_slips_index_csv(path: Path, participants: Iterable[Participant]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "kind",
                "group_id",
                "role",
                "sign_in_key",
                "round_1_question_set_id",
                "round_2_question_set_id",
            ),
        )
        writer.writeheader()
        for participant in participants:
            writer.writerow(
                {
                    "kind": participant.kind,
                    "group_id": participant.group_id,
                    "role": participant.role,
                    "sign_in_key": participant.sign_in_key,
                    "round_1_question_set_id": question_set_id(participant.group_id, participant.role, "Round 1"),
                    "round_2_question_set_id": question_set_id(participant.group_id, participant.role, "Round 2"),
                }
            )


def write_slips_html(path: Path, participants: list[Participant], real_count: int) -> None:
    real = [participant for participant in participants if participant.kind == "real"]
    tests = [participant for participant in participants if participant.kind == "test"]
    body = "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            "<title>Classroom quiz login slips</title>",
            "<style>",
            CSS,
            "</style>",
            "</head>",
            "<body>",
            "<h1>Classroom quiz login slips</h1>",
            f"<p class=\"note\">Real student slips: {real_count}. Cut along the dashed borders. "
            "For 26 or 27 attending students, leave the final teami slips unused from the end.</p>",
            render_section("Real student groups", real),
            '<section class="test-section">',
            "<h1>Test groups</h1>",
            '<p class="note">Use these predictable IDs for production-mode testing only.</p>',
            render_section("Test groups", tests),
            "</section>",
            "</body>",
            "</html>",
        ]
    )
    path.write_text(body, encoding="utf-8")


def render_section(title: str, participants: list[Participant]) -> str:
    if not participants:
        return ""
    groups = sorted({participant.group_id for participant in participants})
    chunks = [f"<h2>{html.escape(title)}</h2>"]
    for group_id in groups:
        group_participants = [participant for participant in participants if participant.group_id == group_id]
        chunks.append(f'<section class="group"><h3>{html.escape(group_id)}</h3><div class="slips">')
        for participant in group_participants:
            chunks.append(render_slip(participant))
        chunks.append("</div></section>")
    return "\n".join(chunks)


def render_slip(participant: Participant) -> str:
    label = "test login id" if participant.kind == "test" else "login id"
    return "\n".join(
        [
            '<article class="slip">',
            f'<div class="group-label">{html.escape(participant.group_id)} - role {html.escape(participant.role)}</div>',
            f'<div class="label">{label}</div>',
            f'<div class="login">{html.escape(participant.sign_in_key)}</div>',
            '<div class="small">Keep this slip until the quiz is finished.</div>',
            "</article>",
        ]
    )


CSS = """
@page {
  size: A4;
  margin: 12mm;
}

* {
  box-sizing: border-box;
}

body {
  color: #111;
  font-family: Arial, Helvetica, sans-serif;
  font-size: 11pt;
  line-height: 1.3;
  margin: 0;
}

h1 {
  font-size: 18pt;
  margin: 0 0 4mm;
}

h2 {
  border-bottom: 1px solid #111;
  font-size: 14pt;
  margin: 7mm 0 3mm;
  padding-bottom: 1mm;
}

h3 {
  font-size: 11pt;
  margin: 0 0 2mm;
  text-transform: uppercase;
}

.note {
  margin: 0 0 5mm;
}

.group {
  break-inside: avoid;
  margin-bottom: 5mm;
}

.slips {
  display: grid;
  gap: 4mm;
  grid-template-columns: repeat(3, 1fr);
}

.slip {
  border: 1px dashed #333;
  min-height: 38mm;
  padding: 5mm;
}

.group-label {
  font-size: 9pt;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.label {
  font-size: 9pt;
  margin-top: 4mm;
  text-transform: uppercase;
}

.login {
  font-size: 23pt;
  font-weight: 700;
  letter-spacing: 0.08em;
  margin-top: 1mm;
}

.small {
  font-size: 8.5pt;
  margin-top: 3mm;
}

.test-section {
  break-before: page;
}
"""


if __name__ == "__main__":
    main()
