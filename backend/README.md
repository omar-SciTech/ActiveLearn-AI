# ActiveLearn AI – Backend (Flask API)

## 1. What the system does
A study platform that adapts to the student. Instead of random questions, the system records every answer, estimates how likely the student is to answer each chapter correctly (knowledge tracing), picks the next question from the weakest chapter, and tells the student things like "Review Chapter 2". Instructors get reports about hard questions, weak topics, weak students and weekly activity.

## 2. Tech stack
- Python 3 + Flask (REST API, JSON)
- SQLite database (`activelearn.db`, one file, created by `../database/create_database.py`)
- Passwords hashed (werkzeug), login returns a signed token (itsdangerous)

## 3. Database (8 tables – see ../database/README.md)
| Table | Purpose |
|---|---|
| users | students and instructors (role column) |
| courses | courses, e.g. IS201 |
| enrollments | which student is in which course (many-to-many junction) |
| topics | chapters of a course |
| questions | question bank: 4 options, correct answer, difficulty, explanation |
| quiz_sessions | each practice session (adaptive or random; topic_id set = one-chapter practice) |
| attempts | every answer: chosen option, correct or not, time taken |
| topic_mastery | predicted probability of a correct answer per student per topic (written by the AI model) |

Relationships: course 1–N topics, topic 1–N questions, user N–M course (via enrollments), user 1–N sessions, session 1–N attempts, question 1–N attempts, user N–M topic (via topic_mastery). See `../database/erd.png`.

## 4. AI part (`mastery.py`)
`predict_mastery(history, topic_ids)` loads the IS201 model named in `../model/saved/active_is201.json` (the trained model with the best validation AUC: DKT, DKT-Q or SAKT) once when the server starts. It predicts P(correct) for every question from the student's full answer history and averages them per chapter → `{topic_id: probability}`. If PyTorch or the model files are missing it falls back to a recency-weighted accuracy, so the app always works. After every answer the predictions are saved in `topic_mastery`. `GET /api/health` shows which model is active.

Next-question rule: pick a chapter at random with weight (1 − predicted)² → weak chapters come up most often but every chapter is still practised; never more than 3 questions in a row from one chapter; difficulty is also drawn at random with weights easy (1−p)², medium 2p(1−p), hard p² (p = predicted level in that chapter), so a weak student gets mostly easy questions but still sees harder ones; no repeats in a session.

## 5. Run it
```
pip install -r requirements.txt
python seed.py        # builds activelearn.db with ../database/create_database.py + simulated answers
python app.py         # app + API on http://localhost:5000 (builds the DB on first run)
python test_api.py    # automated test of every endpoint on a temporary copy (prints ALL OK)
```
Demo student: code `20260002`, password `password123`. Instructors create their own account from Sign up.

## 6. API (send `Authorization: Bearer <token>` except register/login)
| Method & path | Who | What |
|---|---|---|
| POST /api/auth/login | all | `{role, login, password}` – `login` is the student/staff code (or the e-mail) → token |
| POST /api/auth/signup | all | student: `{role:'student', full_name, email, user_code, password}` → enrolled in IS201; instructor: `{role:'instructor', full_name, user_code, course, password, instructor_key}` (key needed only when the server sets `INSTRUCTOR_SIGNUP_KEY`) |
| GET /api/public/courses | public | course list for the sign-up form |
| GET /api/me | all | current user |
| GET /api/courses, GET /api/courses/:id/topics | all | courses and chapters |
| POST /api/courses/:id/enroll | student | join course |
| GET /api/questions?search=&chapter=&difficulty=&course_id= | all | **search and filter** the question bank |
| POST /api/questions | instructor | add a question |
| POST /api/quiz/start `{course_id, mode, topic_id?}` | student | start session, returns first question; with `topic_id` every question comes from that chapter |
| POST /api/quiz/:sid/answer `{question_id, selected_option, time_taken_sec}` | student | saves attempt, returns correct/wrong + explanation + next question |
| GET /api/quiz/:sid/next, POST /api/quiz/:sid/end | student | next question / finish and get score |
| GET /api/reports/student/dashboard | student | questions solved, average accuracy, sessions this week, knowledge per chapter, weekly activity, "review chapter" recommendation |
| GET /api/reports/student/history | student | past sessions |
| GET /api/reports/hardest-questions | instructor | lowest correct % (filter by chapter/difficulty) |
| GET /api/reports/topic-accuracy | instructor | correct % per chapter |
| GET /api/reports/weak-students | instructor | lowest accuracy students |
| GET /api/reports/weekly-activity | instructor | attempts and active students per day |
| GET /api/dashboard | any | dashboard of the front end: student = own numbers, instructor = whole class |
| GET /api/reports/summary?period=day\|week\|month | any | most-missed questions + weakest chapters in the period (student = own) |
| PUT /api/questions/{id} | instructor | edit a question |
| DELETE /api/questions/{id} | instructor | delete a question (soft delete: past answers are kept) |
| GET / | – | serves `../frontend/index.html` |
| GET /api/reports/difficulty-accuracy | instructor | correct % and average time per difficulty |
| GET /api/reports/mislabeled-questions | instructor | questions whose difficulty label does not match the results |

## 7. Front end
The front end (`../frontend/index.html`) is served by this app at http://localhost:5000 and calls the endpoints above with `fetch`. If it is opened directly as a file it still works and calls `http://localhost:5000` (CORS is enabled).
