"""Exports every answer from the database in order, ready for the DKT model.

  python export_for_ai.py                 -> exports/attempts_sequences.csv

Columns: user_id, seq (order of the answer for that student), topic_id, question_id, chapter_no,
         is_correct, difficulty, time_taken_sec, created_at
To retrain the IS201 model on these (real) answers:
  cd ../model
  python prepare_data.py is201 --from-export ../analysis/exports/attempts_sequences.csv
  python train.py is201
"""
import csv, os, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(os.path.dirname(HERE), "backend", "activelearn.db")
OUT = os.path.join(HERE, "exports", "attempts_sequences.csv")

SQL = """SELECT a.user_id,
                ROW_NUMBER() OVER (PARTITION BY a.user_id ORDER BY a.created_at, a.attempt_id) AS seq,
                q.topic_id, a.question_id, t.chapter_no, a.is_correct, q.difficulty, a.time_taken_sec, a.created_at
         FROM attempts a
         JOIN questions q USING (question_id)
         JOIN topics t USING (topic_id)
         ORDER BY a.user_id, seq"""

if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    con = sqlite3.connect(DB)
    cur = con.execute(SQL)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([d[0] for d in cur.description])
        n = 0
        for row in cur:
            w.writerow(row); n += 1
    print(f"Exported {n} answers to {OUT}")
