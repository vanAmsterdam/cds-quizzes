Question-bank context

Use the provided workbook:

causal_dag_peer_discussion_question_bank.xlsx

Relevant sheets:

1. "Core 36 forms"
   - Student-facing question allocation.
   - Use this as the default quiz source.
   - Columns:
     round_id = Round
     question_set_id = Student form
     question_order = Slot
     question_id = ID
     difficulty = Difficulty
     question_type = Type
     question_text = Question
     option_a = Option A
     option_b = Option B
     option_c = Option C
     option_d = Option D
   - Each round × student form contains exactly 6 questions.
   - Each 6-question form is balanced by difficulty:
     one difficulty 1, one difficulty 2, two difficulty 3, one difficulty 4, one difficulty 5.

2. "Deterministic bank"
   - Full instructor/answer-key version.
   - Includes all 48 deterministic questions.
   - Includes Correct answer, grading rationale, and instructor notes.
   - Do not expose correct_answer or rationale to students during the experiment.
   - Use this sheet only for admin/export/scoring.

3. "Open prompts"
   - Contains 12 additional open questions.
   - Do not include these in the main timed quiz unless explicitly enabled later.

4. "Sources & notes"
   - Describes alignment with the course material.

Import strategy

On app setup, load questions from the Excel workbook into the database.

Recommended mapping from workbook to questions table:

questions.question_id        <- ID
questions.round_id          <- Round
questions.question_set_id   <- Student form
questions.question_order    <- Slot
questions.question_text     <- Question
questions.question_type     <- Type
questions.option_a          <- Option A
questions.option_b          <- Option B
questions.option_c          <- Option C
questions.option_d          <- Option D
questions.correct_answer    <- Correct answer
questions.difficulty        <- Difficulty

Assignment logic

For this experiment, question_set_id corresponds to the student form, not a random question bank.

Use assignment table:

student_id, round_id, question_set_id

When a student logs in:
- require student_id
- require round_id
- ask for or assign question_set_id
- load exactly the six questions where:
  questions.round_id = round_id
  questions.question_set_id = assigned question_set_id
- order by question_order

Suggested default assignment:
- If group_id is provided and there are 3 students per group, map students within each group to forms A/B/C or 1/2/3.
- Keep the same student on their assigned form for that round.
- Round 1 is self-selection of the discussion question.
- Round 2 is random assignment of the discussion question; therefore in Round 2 the app should skip free self-selection and instead assign one eligible question randomly, save selected_question_id once, and proceed to revision.

Important: the answer key exists for scoring, but students should never see correct_answer, rationale, or instructor notes.
