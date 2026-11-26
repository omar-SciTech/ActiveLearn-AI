"""Automated test of the whole API on a temporary copy of the database.
Run:  python test_api.py      (prints ALL OK at the end)"""
import os, tempfile
os.environ["DB_PATH"] = os.path.join(tempfile.gettempdir(), "activelearn_test.db")
import seed
seed.main()
from app import app
import mastery

c = app.test_client()
def H(t): return {"Authorization": "Bearer " + t}

print("AI model active:", mastery.MODEL_ACTIVE)
t = c.post("/api/auth/login", json={"email": "ahmed.is201@university.edu", "password": "password123"}).json["token"]
i = c.post("/api/auth/login", json={"role": "instructor", "name": "Dr. Instructor", "password": "password123"}).json["token"]
assert c.post("/api/auth/login", json={"email": "ahmed.is201@university.edu", "password": "x"}).status_code == 401
assert c.post("/api/auth/register", json={"full_name": "New S", "email": "n@u.edu", "password": "secret1"}).status_code == 201
assert c.post("/api/auth/login", json={"role": "student", "name": "Auto", "email": "auto@u.edu", "password": "1234"}).status_code == 201
assert c.post("/api/auth/login", json={"role": "instructor", "name": "Ahmed Mohamed", "password": "password123"}).status_code == 401

s = c.post("/api/quiz/start", json={"course_id": 1}, headers=H(t)).json; sid = s["session_id"]; qn = s["question"]
print("first adaptive question: chapter", qn["chapter_no"], qn["difficulty"])
for _ in range(3):
    a = c.post(f"/api/quiz/{sid}/answer", json={"question_id": qn["question_id"], "selected_option": "A",
               "time_taken_sec": 10}, headers=H(t)).json
    assert a["explanation"]
    qn = a["next_question"]
    print("correct" if a["is_correct"] else "wrong", "-> next: chapter", qn["chapter_no"], qn["difficulty"])
print(c.post(f"/api/quiz/{sid}/end", headers=H(t)).json)

d = c.get("/api/reports/student/dashboard", headers=H(t)).json
print({k: d[k] for k in ("questions_solved", "avg_accuracy_pct", "sessions_this_week", "recommendation")})
assert len(d["knowledge_by_topic"]) == 6
print(len(c.get("/api/questions?chapter=2&difficulty=easy&search=key", headers=H(t)).json), "filtered questions")
for path in ("hardest-questions?min_attempts=2&limit=2", "topic-accuracy", "weak-students", "weekly-activity",
             "difficulty-accuracy", "mislabeled-questions"):
    r = c.get("/api/reports/" + path, headers=H(i))
    assert r.status_code == 200, path
    print(path, "->", r.json[:2])
assert c.get("/api/reports/weak-students", headers=H(t)).status_code == 403
d = c.get("/api/dashboard", headers=H(t)).json; assert len(d["weekly_activity"]) == 7 and len(d["knowledge_by_topic"]) == 6
for p in ("day", "week", "month"):
    assert c.get(f"/api/reports/summary?period={p}", headers=H(i)).status_code == 200
new = c.post("/api/questions", headers=H(i), json={"topic_id": 1, "body": "Q?", "option_a": "a", "option_b": "b",
             "option_c": "c", "option_d": "d", "correct_option": "B", "difficulty": "Easy"}).json["question_id"]
assert c.put(f"/api/questions/{new}", headers=H(i), json={"topic_id": 2, "body": "Q2?", "option_a": "a", "option_b": "b",
             "option_c": "c", "option_d": "d", "correct_option": "C"}).status_code == 200
assert c.delete(f"/api/questions/{new}", headers=H(i)).status_code == 200
assert "correct_option" not in c.get("/api/questions", headers=H(t)).json[0]
assert c.get("/").status_code == 200
print("front-end endpoints OK")
assert c.get("/api/me").status_code == 401
print("ALL OK")
