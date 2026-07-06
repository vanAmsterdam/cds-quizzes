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
3. Click `Import bundled classroom forms and roster`.
4. Open `Live Monitor` while students complete Round 0.

Do not commit `.streamlit/secrets.toml`, `data/dev.sqlite`, or ad hoc private roster CSVs.

Files that should be committed:

- `app.py`, `pages/`, `src/`, `tests/`
- `requirements.txt`, `pytest.ini`, `.gitignore`
- `.streamlit/secrets.toml.example`
- `data/causal_dag_peer_discussion_question_bank.xlsx`
- `data/class_form_questions.csv`, `data/class_roster.csv`, `data/class_slips.html`, `data/class_slips_index.csv`
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

## Private Classroom Roster And Slips

The current classroom roster and generated assignments are bundled in the repo:

- `data/class_roster.csv`: production roster used by the Admin bundled setup button.
- `data/class_form_questions.csv`: team-specific generated form assignments used by the Admin bundled setup button.
- `data/class_slips.html`: print/cut login slips.
- `data/class_slips_index.csv`: instructor-only index of groups, roles, login IDs, and assigned forms.

To generate an alternative private roster, run:

```bash
python tools/generate_roster_materials.py
```

This writes:

- `data/private_class_roster.csv`: upload this in the Admin page as the production roster.
- `data/private_class_form_questions.csv`: upload this in the Admin page after the workbook and before the roster.
- `data/private_class_slips.html`: open in a browser and print/cut the grouped login slips.
- `data/private_class_slips_index.csv`: instructor-only index of groups, roles, login IDs, and assigned question forms.

The generated form-question CSV gives every team the same 36-question pool. Within each team, the questions are randomly reassigned into participant-round batches. Each 6-question batch has two easier questions, two harder questions, and two hardest questions. In a 4-person team, the fourth role receives a stratified duplicate subset from that team's 36-question pool, so no extra questions are introduced into that team.

The real student IDs are random lowercase letters only. The default layout is eight 3-person teams plus one flexible final team: use all four `teami` slips for 28 students, leave the final `teami` role `d` slip unused for 27 students, and leave roles `c` and `d` unused for 26 students. Test IDs are predictable and separated into `testa` through `testd` groups, with IDs like `testaa`, `testab`, and `testac`.

These `data/private...` files are ignored by git. Do not commit them to a public repository; upload the roster CSV through the Admin page instead.

## Workflow

1. Student signs in with a key.
2. Student completes Round 0 answer check.
3. Student sees the next unlocked assigned round only.
4. Student clicks `Start round 1 now` or `Start round 2 now`; this starts that round's 6-minute timer.
5. Individual phase: six questions, six-minute timer based on database start time.
6. Round 1: student permanently selects one question for discussion.
7. Discussion phase: student clicks `Start discussion phase now`; this starts the 2-minute discussion timer.
8. Revision phase: only the selected question is editable after the discussion timer starts.
9. Round 2 remains locked until Round 1 revision is submitted; then the app randomly selects one assigned question for discussion and uses the same discussion/revision flow.
10. Done phase: all answers are locked.

The backend service layer enforces phase locks; disabled or hidden widgets are not trusted for correctness.
During the individual phase, answer changes are saved as drafts and finalized automatically when the timer expires.
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
