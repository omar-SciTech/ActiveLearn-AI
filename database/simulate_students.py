"""Simulated students for testing (SIMULATED data, not real students).

Why: the app is new, so there are no real IS201 answers yet. To test the reports and to give the
IS201 model something to learn from, we generate students whose answers follow a simple but
realistic rule:

  - every student has a hidden ability per chapter (some chapters strong, some weak)
  - every question has a difficulty: its label (easy < medium < hard) plus its own small offset,
    because two "medium" questions are never exactly equally hard
  - P(correct) = 0.25 (guessing, 4 options) + 0.75 * sigmoid(1.7 * (ability - difficulty))
  - after each attempt on a chapter the ability in that chapter grows a little (learning)

Used by:
  backend/seed.py            -> adds a small simulated history to the demo database
  model/prepare_data.py      -> generates many simulated sequences to train the IS201 model

Run alone:  python simulate_students.py --db ../backend/activelearn.db --students 30
"""
import argparse, math, random, sqlite3
from datetime import datetime, timedelta

DIFFICULTY = {"easy": -1.0, "medium": 0.0, "hard": 1.0}
LEARN_RATE = 0.06          # ability gained per attempt in a chapter


def make_student(rng, chapters):
    general = rng.gauss(0, 0.8)                       # overall level of the student
    return {c: 0.6 * general + 0.8 * rng.gauss(0, 1) for c in chapters}


def question_difficulty(q):
    """Label difficulty + a fixed offset of this question (same every run)."""
    return DIFFICULTY[q["difficulty"]] + random.Random(q["question_id"]).gauss(0, 0.5)


def p_correct(ability, difficulty_value):
    return 0.25 + 0.75 / (1 + math.exp(-1.7 * (ability - difficulty_value)))


def simulate_sequence(rng, questions, n_sessions, per_session):
    """questions: list of dicts with question_id, topic_id, difficulty, correct_option.
    Returns a list of sessions; each session is a list of attempts (dicts)."""
    chapters = sorted({q["topic_id"] for q in questions})
    ability = make_student(rng, chapters)
    by_topic = {c: [q for q in questions if q["topic_id"] == c] for c in chapters}
    sessions = []
    for _ in range(n_sessions):
        # a session focuses on 1-2 chapters (like a student revising specific chapters)
        focus = rng.sample(chapters, k=min(len(chapters), rng.choice([1, 2])))
        pool = [q for c in focus for q in by_topic[c]]
        attempts = []
        for q in rng.sample(pool, k=min(per_session, len(pool))):
            ok = rng.random() < p_correct(ability[q["topic_id"]], question_difficulty(q))
            chosen = q["correct_option"] if ok else rng.choice([o for o in "ABCD" if o != q["correct_option"]])
            base_time = {"easy": 20, "medium": 35, "hard": 50}[q["difficulty"]]
            attempts.append({"question_id": q["question_id"], "topic_id": q["topic_id"], "is_correct": int(ok),
                             "selected_option": chosen,
                             "time_taken_sec": round(max(5, rng.gauss(base_time + (0 if ok else 10), 8)), 1)})
            ability[q["topic_id"]] += LEARN_RATE
        sessions.append(attempts)
    return sessions


def load_questions(conn, course_id=1):
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""SELECT q.question_id, q.topic_id, q.difficulty, q.correct_option
                           FROM questions q JOIN topics t USING(topic_id) WHERE t.course_id=?""", (course_id,)).fetchall()
    return [dict(r) for r in rows]


def add_history(conn, user_ids, seed=7, days=28, course_id=1):
    """Writes simulated sessions + attempts for the given students into the database."""
    rng = random.Random(seed)
    questions = load_questions(conn, course_id)
    now = datetime.now().replace(microsecond=0)
    for uid in user_ids:
        n_sessions = rng.randint(4, 12)
        sessions = simulate_sequence(rng, questions, n_sessions, per_session=rng.randint(6, 10))
        day_offsets = sorted(rng.sample(range(days), k=min(n_sessions, days)), reverse=True)
        for attempts, d in zip(sessions, day_offsets):
            start = now - timedelta(days=d, hours=rng.randint(0, 10), minutes=rng.randint(0, 59))
            cur = conn.execute("INSERT INTO quiz_sessions(user_id,course_id,mode,started_at,ended_at) VALUES(?,?,?,?,?)",
                               (uid, course_id, "adaptive", start.isoformat(sep=" ", timespec="seconds"), None))
            sid = cur.lastrowid
            t = start
            for a in attempts:
                t += timedelta(seconds=a["time_taken_sec"] + 5)
                conn.execute("""INSERT INTO attempts(session_id,user_id,question_id,selected_option,is_correct,time_taken_sec,created_at)
                                VALUES(?,?,?,?,?,?,?)""",
                             (sid, uid, a["question_id"], a["selected_option"], a["is_correct"], a["time_taken_sec"],
                              t.isoformat(sep=" ", timespec="seconds")))
            conn.execute("UPDATE quiz_sessions SET ended_at=? WHERE session_id=?", (t.isoformat(sep=" ", timespec="seconds"), sid))
    conn.commit()


def add_students(conn, n, password_hash, course_id=1):
    """Creates n simulated students (clearly named 'Sim Student ..') and enrolls them."""
    ids = []
    for i in range(1, n + 1):
        cur = conn.execute("INSERT INTO users(full_name,email,password_hash,role) VALUES(?,?,?,'student')",
                           (f"Sim Student {i:02d}", f"sim{i:02d}@demo.local", password_hash))
        ids.append(cur.lastrowid)
        conn.execute("UPDATE users SET user_code=? WHERE user_id=?", (f"2026{cur.lastrowid:04d}", cur.lastrowid))
        conn.execute("INSERT INTO enrollments(user_id,course_id) VALUES(?,?)", (cur.lastrowid, course_id))
    conn.commit()
    return ids


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--students", type=int, default=30)
    a = ap.parse_args()
    con = sqlite3.connect(a.db); con.execute("PRAGMA foreign_keys=ON")
    h = con.execute("SELECT password_hash FROM users WHERE user_id=2").fetchone()[0]
    new_ids = add_students(con, a.students, h)
    add_history(con, new_ids)
    print(f"Added {len(new_ids)} simulated students with history to {a.db}")
