"""Runs the app's IS201 model on every student in the database and organizes its predictions.

  python predict_all.py

1) updates the topic_mastery table (what the dashboard and reports read)
2) writes results/is201_student_predictions.csv:
     student, chapter, answers in that chapter, actual correct %, predicted P(correct) %,
     level (weak / medium / strong) and whether it is the chapter to review
3) writes results/is201_question_predictions.csv: predicted P(correct) for every student x question
"""
import csv, os, sqlite3
from datetime import datetime
from predictor import Predictor

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(os.path.dirname(HERE), "backend", "activelearn.db")
OUT = os.path.join(HERE, "results", "is201_student_predictions.csv")
OUT_Q = os.path.join(HERE, "results", "is201_question_predictions.csv")


def level(p):
    return "weak" if p < 0.6 else "medium" if p < 0.8 else "strong"


def main():
    pred = Predictor()
    print("model used:", pred.name)
    con = sqlite3.connect(DB)
    topics = con.execute("SELECT topic_id, chapter_no, name FROM topics WHERE course_id=1 ORDER BY chapter_no").fetchall()
    students = con.execute("SELECT user_id, full_name FROM users WHERE role='student' ORDER BY user_id").fetchall()
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    rows, qrows = [], []
    for uid, name in students:
        hist = con.execute("""SELECT q.topic_id, a.is_correct, a.question_id FROM attempts a JOIN questions q USING(question_id)
                              WHERE a.user_id=? ORDER BY a.created_at, a.attempt_id""", (uid,)).fetchall()
        mastery = pred.topic_mastery(hist)
        weakest = min(mastery, key=mastery.get)
        for t, ch, tname in topics:
            done = [ok for tt, ok, _ in hist if tt == t]
            con.execute("""INSERT INTO topic_mastery(user_id,topic_id,p_correct,updated_at) VALUES(?,?,?,?)
                           ON CONFLICT(user_id,topic_id) DO UPDATE SET p_correct=excluded.p_correct,
                           updated_at=excluded.updated_at""", (uid, t, mastery[t], now))
            rows.append([uid, name, ch, tname, len(done), round(100 * sum(done) / len(done), 1) if done else "",
                         round(100 * mastery[t], 1), level(mastery[t]), "yes" if t == weakest else ""])
        for qid, p in pred.question_probs(hist).items():
            qrows.append([uid, name, qid, round(100 * p, 1)])
    con.commit()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "student", "chapter_no", "chapter", "answers_in_chapter", "actual_correct_pct",
                    "predicted_correct_pct", "level", "review_this_chapter"])
        w.writerows(rows)
    with open(OUT_Q, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "student", "question_id", "predicted_correct_pct"])
        w.writerows(qrows)
    print(f"Predictions for {len(students)} students -> topic_mastery, {os.path.basename(OUT)}, {os.path.basename(OUT_Q)}")


if __name__ == "__main__":
    main()
