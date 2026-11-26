PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name     TEXT NOT NULL,
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student','instructor')),
  created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS courses (
  course_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  code          TEXT NOT NULL UNIQUE,
  title         TEXT NOT NULL,
  instructor_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS enrollments (
  user_id     INTEGER NOT NULL REFERENCES users(user_id)     ON DELETE CASCADE,
  course_id   INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
  enrolled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, course_id)
);

CREATE TABLE IF NOT EXISTS topics (
  topic_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  course_id   INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
  chapter_no  INTEGER NOT NULL,
  name        TEXT NOT NULL,
  UNIQUE (course_id, chapter_no)
);

CREATE TABLE IF NOT EXISTS questions (
  question_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  topic_id      INTEGER NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
  body          TEXT NOT NULL,
  option_a      TEXT NOT NULL,
  option_b      TEXT NOT NULL,
  option_c      TEXT NOT NULL,
  option_d      TEXT NOT NULL,
  correct_option TEXT NOT NULL CHECK (correct_option IN ('A','B','C','D')),
  difficulty    TEXT NOT NULL DEFAULT 'medium' CHECK (difficulty IN ('easy','medium','hard')),
  explanation   TEXT,
  is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))   -- 0 = deleted by the instructor (answers are kept)
);

CREATE TABLE IF NOT EXISTS quiz_sessions (
  session_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL REFERENCES users(user_id)     ON DELETE CASCADE,
  course_id   INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
  mode        TEXT NOT NULL DEFAULT 'adaptive' CHECK (mode IN ('adaptive','random')),
  started_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ended_at    TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
  attempt_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id      INTEGER NOT NULL REFERENCES quiz_sessions(session_id) ON DELETE CASCADE,
  user_id         INTEGER NOT NULL REFERENCES users(user_id)            ON DELETE CASCADE,
  question_id     INTEGER NOT NULL REFERENCES questions(question_id)    ON DELETE CASCADE,
  selected_option TEXT NOT NULL CHECK (selected_option IN ('A','B','C','D')),
  is_correct      INTEGER NOT NULL CHECK (is_correct IN (0,1)),
  time_taken_sec  REAL,
  created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Predicted probability of answering correctly per student/topic (written by the DKT model or the fallback)
CREATE TABLE IF NOT EXISTS topic_mastery (
  user_id    INTEGER NOT NULL REFERENCES users(user_id)   ON DELETE CASCADE,
  topic_id   INTEGER NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
  p_correct  REAL NOT NULL CHECK (p_correct BETWEEN 0 AND 1),
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, topic_id)
);

CREATE INDEX IF NOT EXISTS idx_attempts_user     ON attempts(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_attempts_question ON attempts(question_id);
CREATE INDEX IF NOT EXISTS idx_questions_topic   ON questions(topic_id, difficulty);
