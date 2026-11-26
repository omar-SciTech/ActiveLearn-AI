# Database part

| File | What it is |
|---|---|
| `schema.sql` | Creates the 8 tables (CREATE TABLE with primary keys, foreign keys, CHECK and UNIQUE constraints) |
| `data.sql` | INSERT statements: 4 users, the IS201 course, the 6 chapters of the course book, 60 questions (10 per chapter, each with 4 options, the correct answer, difficulty and an explanation) |
| `check.sql` | Queries to check the database after building it |
| `simulate_students.py` | Generates **simulated** students and answers for testing (used by `backend/seed.py` and the model) |
| `erd.png` / `erd.svg` / `erd.dot` | Entity Relationship Diagram |

## Build it in DB Browser for SQLite (what we show in the discussion)
1. **New Database** → save as `activelearn.db` (cancel the "Edit table" window).
2. Tab **Execute SQL** → open `schema.sql` → **Run** (Ctrl+Enter / F5).
3. Open `data.sql` → **Run**.
4. **Write Changes** (Ctrl+S).
5. Tab **Browse Data** → choose a table to see the rows.
6. Open `check.sql` → run it to see the counts and test the relations.

## Build it with Python (with simulated answers so reports have data)
```
cd backend
python seed.py
```
This runs the same `schema.sql` + `data.sql`, then adds 30 simulated students and simulated answers for everyone.

## Tables
| Table | Purpose | Key |
|---|---|---|
| users | students and instructors (role) | PK user_id, email UNIQUE |
| courses | courses (IS201) | PK course_id, FK instructor_id → users |
| enrollments | student ↔ course (many-to-many) | PK (user_id, course_id) |
| topics | chapters of a course | PK topic_id, FK course_id |
| questions | question bank | PK question_id, FK topic_id |
| quiz_sessions | one practice session | PK session_id, FK user_id, course_id |
| attempts | every answer (chosen option, correct?, time) | PK attempt_id, FK session_id, user_id, question_id |
| topic_mastery | AI prediction per student and chapter | PK (user_id, topic_id) |

All demo users have the password `password123`.
