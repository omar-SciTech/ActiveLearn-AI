# Database part

The whole database is written in Python with the built-in `sqlite3` module.

| File | What it is |
|---|---|
| `create_database.py` | Builds the database: `create_tables()` creates the 9 tables (primary keys, foreign keys, CHECK and UNIQUE constraints), `insert_data()` inserts 4 users, the IS201 course, the 6 chapters of the course book and 60 questions (10 per chapter, each with 4 options, the correct answer, difficulty and an explanation), and `check()` prints row counts and tests the relations |
| `simulate_students.py` | Generates **simulated** students and answers for testing (used by `backend/seed.py` and the model) |
| `erd.png` / `erd.svg` / `erd.dot` | Entity Relationship Diagram |

## Build it
```
cd database
python create_database.py
```
This creates `database/activelearn.db` and prints the checks:
row counts, foreign keys, questions per chapter and difficulty, correct answers spread over A–D,
and a CHECK-constraint test (an invalid difficulty is rejected).

Then open `activelearn.db` in **DB Browser for SQLite** → tab **Browse Data** → choose a table to see the rows.

## Build the app's database (with simulated answers so reports have data)
```
cd backend
python seed.py
```
This calls the same `create_tables()` and `insert_data()`, then adds 30 simulated students and simulated answers for everyone.

## Tables
| Table | Purpose | Key |
|---|---|---|
| users | students and instructors (role) | PK user_id, email UNIQUE |
| courses | courses (IS201) | PK course_id, FK instructor_id → users |
| enrollments | student ↔ course (many-to-many) | PK (user_id, course_id) |
| topics | chapters of a course | PK topic_id, FK course_id |
| questions | question bank | PK question_id, FK topic_id |
| quiz_sessions | one practice session (all chapters, or one chapter when topic_id is set) | PK session_id, FK user_id, course_id, topic_id |
| attempts | every answer (chosen option, correct?, time) | PK attempt_id, FK session_id, user_id, question_id |
| topic_mastery | AI prediction per student and chapter | PK (user_id, topic_id) |
| feedback | messages from the Feedback & complaints window (suggestion / problem / complaint, new / resolved); anonymous, so it has no link to users | PK feedback_id |

Every user has a `user_code` (student code or staff code, UNIQUE) used to sign in. The demo users' password is `password123` (local copy only).
