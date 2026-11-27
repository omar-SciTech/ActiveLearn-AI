"""Builds the demo database (backend/activelearn.db) in 3 steps:

  1) database/create_database.py: create_tables() -> the 9 tables
  2) database/create_database.py: insert_data()   -> users, course, 6 chapters, 60 questions
  3) simulated history    -> 30 simulated students + answers for everyone, so reports and the
                             model have data to show (clearly marked as simulated)
Then it fills topic_mastery with the model's predictions for every student.

Run:  python seed.py
"""
import os, sqlite3, sys
from app import DB_PATH, BASE, DB_DIR, update_mastery_for_user

sys.path.insert(0, DB_DIR)
from simulate_students import add_students, add_history   # noqa: E402
from create_database import create_tables, insert_data    # noqa: E402

N_SIM_STUDENTS = 30


def main(reset=True):
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys=ON")
    create_tables(con)
    insert_data(con)
    pw_hash = con.execute("SELECT password_hash FROM users WHERE user_id=2").fetchone()[0]
    sim_ids = add_students(con, N_SIM_STUDENTS, pw_hash)
    students = [r[0] for r in con.execute("SELECT user_id FROM users WHERE role='student' ORDER BY user_id")]
    add_history(con, students)
    con.close()

    # predicted knowledge per chapter for every student (uses the trained model if it exists)
    from app import app
    with app.app_context():
        for uid in students:
            update_mastery_for_user(uid, course_id=1)
    print(f"Seeded: {DB_PATH}  ({len(students)} students, {len(sim_ids)} of them simulated)")


if __name__ == "__main__":
    main()
