# CDS Classroom Quiz App

Streamlit app for running the classroom causal-inference quiz experiment.

## Local Preview

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

For SQLite development, the app initializes `data/dev.sqlite`, imports the bundled workbook, and loads `data/sample_roster.csv` automatically when the database is empty.

Sample sign-in keys:

- `demo-a`
- `demo-b`
- `demo-c`
- `demo-d` through `demo-i`

Admin pages use the password from `.streamlit/secrets.toml`. If no secrets file is present and SQLite is used, the development password is `admin`.

## Deployment

Use Streamlit Community Cloud with Supabase Postgres for online testing.

1. Create a Supabase project and copy a Postgres connection string.
2. Push this repo to GitHub.
3. In Streamlit Community Cloud, create a new app from the GitHub repo.
4. Use `main` as the branch and `app.py` as the entrypoint.
5. In Advanced settings, choose Python 3.12 and paste secrets in TOML format.

Secrets for Streamlit Community Cloud:

```toml
[app]
admin_password = "replace-me"

[database]
url = "postgresql+psycopg2://postgres:<password>@<host>:5432/postgres"
# Optional Postgres pool caps. These defaults leave headroom under common
# Supabase session-pool limits while allowing classroom bursts.
pool_size = 5
max_overflow = 0
pool_timeout = 10
pool_recycle = 300
```

After first deploy:

1. Open the app.
2. Go to the `Admin` page.
3. Import the bundled workbook if it is not already loaded.
4. Upload the private roster CSV.
5. Open `Live Monitor` while students complete Round 0.

Do not commit `.streamlit/secrets.toml`, `data/dev.sqlite`, or private roster CSVs.

Files that should be committed:

- `app.py`, `pages/`, `src/`, `tests/`
- `requirements.txt`, `pytest.ini`, `.gitignore`
- `.streamlit/secrets.toml.example`
- `data/causal_dag_peer_discussion_question_bank.xlsx`
- `data/sample_roster.csv`
- `README.md`, `instruction.md`, `question_bank_context.md`

## Roster CSV

The roster importer expects:

```csv
student_id,sign_in_key,group_id,round_id,question_set_id
demo_a,demo-a,team_1,Round 1,Student A
demo_a,demo-a,team_1,Round 2,Student A
```

Each `sign_in_key` belongs to exactly one student. Add one row per student and quiz round. `Round 0` is built into the app and should not be included in the roster.

## Workflow

1. Student signs in with a key.
2. Student completes Round 0 answer check.
3. Student chooses an assigned round.
4. Individual phase: six questions, six-minute timer based on database start time.
5. Round 1: student permanently selects one question for discussion.
6. Round 2: app randomly selects one assigned question for discussion.
7. Revision phase: only the selected question is editable.
8. Done phase: all answers are locked.

The backend service layer enforces phase locks; disabled or hidden widgets are not trusted for correctness.
Timestamps recorded by the app use Europe/Amsterdam local time by default.

## Admin And Monitoring

- `Admin` page: import workbook, import roster, export sessions/answers/joined CSVs.
- `Admin` page reset tab: reset one student's sessions and answers while keeping roster assignments.
- `Live Monitor` page: auto-refreshing roster view with sign-in status, Round 0 completion, current phase, answer counts, and last saved time.

## Diagnosing Cloud Performance

- Use `Manage app` in the lower-right corner of the deployed app to inspect Streamlit Cloud logs.
- The individual-phase timer polls every 10 seconds; the saved database start time remains the source of truth.
- Startup table creation and seed checks are cached per Streamlit process, so normal reruns should not repeatedly run setup queries.
- Supabase Postgres connections are capped at five pooled connections with no overflow by default to avoid session-pool `max clients reached` errors while supporting classroom bursts.

## Tests

```bash
pytest
```
