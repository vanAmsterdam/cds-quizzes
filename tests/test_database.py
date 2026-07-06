from sqlalchemy import create_engine, inspect, text

from cds_quizzes.database import _migrate_schema


def test_migrate_schema_adds_discussion_columns_to_existing_sessions_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.sqlite'}", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE sessions (
                    student_id VARCHAR(128) NOT NULL,
                    round_id VARCHAR(64) NOT NULL,
                    phase VARCHAR(32) NOT NULL,
                    individual_started_at DATETIME,
                    individual_submitted_at DATETIME,
                    selected_question_id VARCHAR(64),
                    selection_confirmed_at DATETIME,
                    revision_submitted_at DATETIME,
                    done_at DATETIME,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (student_id, round_id)
                )
                """
            )
        )

    _migrate_schema(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("sessions")}
    assert "discussion_started_at" in columns
    assert "discussion_ended_at" in columns
