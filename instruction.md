Build a Streamlit quiz app for a classroom causal inference experiment.

Core workflow:

1. Student enters student_id, round_id, and optional group_id.
2. App loads exactly 6 assigned questions for that student/round.
3. Individual phase:
    * Student gets 6 minutes total for all 6 questions.
    * All 6 answers are editable during this phase.
    * When time expires or the student clicks submit, save all original answers and lock them.
4. Discussion selection phase:
    * Show the 6 locked questions and original answers.
    * Student selects exactly 1 question to discuss with peers.
    * Once confirmed, this choice is permanent.
    * Student must not be able to go back and choose another question.
5. Revision phase:
    * Only the selected question is editable.
    * The other 5 questions remain locked.
    * Student can submit a revised answer for the selected question.
6. Done phase:
    * Everything is locked.
    * Show a confirmation message.

Technical requirements:

* Use Streamlit for the frontend.
* Use Supabase Postgres or SQLite for storage. Prefer Supabase if deployed online.
* Do not rely only on disabled frontend widgets for locking. Backend validation must enforce that:
    * Original answers can only be written during the individual phase.
    * selected_question_id can only be set once.
    * Revised answers can only be written for the selected question during the revision phase.
* Store timestamps server-side where possible.
* The timer should be based on a saved phase start time, not only a client-side countdown, so refreshes do not reset time.
* Refreshing the page should restore the correct phase and locked/unlocked state.

Suggested database tables:

students

* student_id
* group_id
* created_at

questions

* question_id
* round_id
* question_set_id
* question_order
* question_text
* question_type
* option_a
* option_b
* option_c
* option_d
* correct_answer
* difficulty

assignments

* student_id
* round_id
* question_set_id

sessions

* student_id
* round_id
* phase
* individual_started_at
* individual_submitted_at
* selected_question_id
* selection_confirmed_at
* revision_submitted_at
* done_at

answers

* student_id
* round_id
* question_id
* original_answer
* original_saved_at
* selected_for_discussion
* revised_answer
* revised_saved_at

Phases:

* INDIVIDUAL
* SELECT_DISCUSSION
* REVISION
* DONE

Implementation notes:

* On first visit, create or retrieve a session.
* If no individual_started_at exists, set it.
* Remaining time = 360 seconds - elapsed time since individual_started_at.
* If remaining time <= 0, automatically save current answers if possible and move to SELECT_DISCUSSION.
* Store interim answers in st.session_state, but persist final original answers on phase transition.
* Use database transactions or equivalent checks to avoid overwriting locked values.
* Add an admin/export page protected by a simple password in Streamlit secrets.
* Export CSVs for sessions, answers, and joined long-format data: one row per student_id × round_id × question_id.

Minimal UI:

* Login screen: student ID, round ID.
* Quiz screen: timer at top, six questions below.
* Selection screen: radio button for the one question to discuss, confirm button.
* Revision screen: selected question editable, other answers displayed read-only.
* Done screen: “Submitted — thank you.”

Deployment target:

* GitHub repo.
* Deploy on Streamlit Community Cloud.
* Use Supabase credentials via .streamlit/secrets.toml.
* Do not commit secrets.

Acceptance tests:

1. A student cannot revise non-selected questions.
2. A student cannot change selected discussion question after confirming.
3. Refreshing during the individual phase does not reset the 6-minute timer.
4. Refreshing during revision restores only the selected question as editable.
5. After done, all questions are locked.
6. Export produces one row per student/question with original answer, selected flag, and revised answer.
