import os, sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, g, jsonify, request, send_from_directory
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash, check_password_hash
from mastery import predict_mastery

BASE = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(os.path.dirname(BASE), "database")        # schema.sql, data.sql live here
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE, "activelearn.db"))
FRONTEND = os.path.join(os.path.dirname(BASE), "frontend")
SECRET = os.environ.get("SECRET_KEY", "change-me-in-production")
TOKEN_MAX_AGE = 60 * 60 * 24 * 7

app = Flask(__name__)

@app.after_request
def cors(r):  # lets the front-end (opened from file:// or another port) call the API
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    r.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return r

@app.route("/api/<path:_>", methods=["OPTIONS"])
def preflight(_): return "", 204
ser = URLSafeTimedSerializer(SECRET)

# ---------- db helpers ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d: d.close()

def init_db():
    """Creates the tables if they do not exist (database/schema.sql). Run seed.py for the demo data."""
    with sqlite3.connect(DB_PATH) as c:
        c.executescript(open(os.path.join(DB_DIR, "schema.sql"), encoding="utf-8").read())

def q(sql, args=(), one=False):
    rows = db().execute(sql, args).fetchall()
    rows = [dict(r) for r in rows]
    return (rows[0] if rows else None) if one else rows

def run(sql, args=()):
    cur = db().execute(sql, args); db().commit(); return cur.lastrowid

def err(msg, code=400): return jsonify(error=msg), code

# ---------- auth ----------
def make_token(u): return ser.dumps({"uid": u["user_id"], "role": u["role"]})

def auth(role=None):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            h = request.headers.get("Authorization", "")
            if not h.startswith("Bearer "): return err("Missing token", 401)
            try: data = ser.loads(h[7:], max_age=TOKEN_MAX_AGE)
            except SignatureExpired: return err("Token expired", 401)
            except BadSignature: return err("Invalid token", 401)
            g.uid, g.role = data["uid"], data["role"]
            if role and g.role != role: return err("Forbidden", 403)
            return f(*a, **k)
        return w
    return deco

import re
CODE_RE = re.compile(r"^[A-Za-z0-9._-]{3,20}$")
INSTRUCTOR_KEY = os.environ.get("INSTRUCTOR_SIGNUP_KEY")   # set on the hosted site; unset = local/dev


def ensure_schema():
    """Upgrades an older database in place: adds users.user_code (sign-in code) and fills it for old rows."""
    if not os.path.exists(DB_PATH):
        return
    with sqlite3.connect(DB_PATH) as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(users)")]
        if not cols:
            return
        if "user_code" not in cols:
            c.execute("ALTER TABLE users ADD COLUMN user_code TEXT")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_code ON users(user_code)")
        for uid, role in c.execute("SELECT user_id, role FROM users WHERE user_code IS NULL").fetchall():
            code = f"DR{uid:03d}" if role == "instructor" else f"2026{uid:04d}"
            c.execute("UPDATE users SET user_code=? WHERE user_id=?", (code, uid))


ensure_schema()


@app.post("/api/auth/login")
def login():
    """Sign in with a student/staff code (or e-mail) + password. The chosen role must match the account."""
    d = request.get_json(force=True)
    role = d.get("role", "student")
    ident = (d.get("login") or d.get("code") or d.get("email") or d.get("name") or "").strip()
    pw = d.get("password") or ""
    if not ident or not pw: return err("Enter your code and password")
    u = q("SELECT * FROM users WHERE lower(user_code)=lower(?) OR email=lower(?)", (ident, ident), one=True)
    if not u or not check_password_hash(u["password_hash"], pw):
        return err("Wrong code or password", 401)
    if u["role"] != role:
        return err("This account is not a " + role + " account", 403)
    return jsonify(token=make_token(u), user=pub_user(u))


@app.get("/api/public/courses")
def public_courses():  # for the instructor sign-up form
    return jsonify(q("SELECT code, title FROM courses ORDER BY code"))


@app.post("/api/auth/signup")
@app.post("/api/auth/register")
def signup():
    """Student: name + university e-mail + student code + password -> enrolled in IS201.
    Instructor: name + staff code + course + password (+ the instructor key when the site sets one)."""
    d = request.get_json(force=True)
    role = d.get("role", "student")
    name = (d.get("full_name") or d.get("name") or "").strip()
    code = (d.get("user_code") or d.get("code") or "").strip()
    pw = d.get("password") or ""
    if role not in ("student", "instructor"): return err("Invalid role")
    if len(name) < 3: return err("Please enter your full name")
    if not CODE_RE.match(code): return err("The code must be 3-20 letters or digits")
    if len(pw) < 6: return err("The password must be at least 6 characters")
    if q("SELECT 1 FROM users WHERE lower(user_code)=lower(?)", (code,), one=True):
        return err("This code is already registered — sign in instead", 409)
    if role == "student":
        email = (d.get("email") or "").strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email): return err("Please enter a valid university e-mail")
        if q("SELECT 1 FROM users WHERE email=?", (email,), one=True):
            return err("This e-mail is already registered — sign in instead", 409)
        uid = run("INSERT INTO users(full_name,email,user_code,password_hash,role) VALUES(?,?,?,?,'student')",
                  (name, email, code, generate_password_hash(pw)))
        run("INSERT OR IGNORE INTO enrollments(user_id,course_id) SELECT ?, course_id FROM courses WHERE code='IS201'", (uid,))
    else:
        if INSTRUCTOR_KEY and d.get("instructor_key") != INSTRUCTOR_KEY:
            return err("Wrong instructor key — ask the course administrator for it", 403)
        course = q("SELECT * FROM courses WHERE upper(code)=upper(?)", ((d.get("course") or "").strip(),), one=True)
        if not course: return err("Please choose your course")
        email = f"{code.lower()}@staff.activelearn"   # instructors sign in with their staff code
        uid = run("INSERT INTO users(full_name,email,user_code,password_hash,role) VALUES(?,?,?,?,'instructor')",
                  (name, email, code, generate_password_hash(pw)))
        run("UPDATE courses SET instructor_id=? WHERE course_id=? AND instructor_id IS NULL", (uid, course["course_id"]))
    u = q("SELECT * FROM users WHERE user_id=?", (uid,), one=True)
    return jsonify(token=make_token(u), user=pub_user(u), created=True), 201

def pub_user(u): return {k: u.get(k) for k in ("user_id", "full_name", "email", "user_code", "role")}

@app.get("/api/me")
@auth()
def me(): return jsonify(pub_user(q("SELECT * FROM users WHERE user_id=?", (g.uid,), one=True)))

# ---------- courses / topics ----------
@app.get("/api/courses")
@auth()
def courses():
    return jsonify(q("SELECT course_id,code,title FROM courses ORDER BY code"))

@app.post("/api/courses/<int:cid>/enroll")
@auth("student")
def enroll(cid):
    if not q("SELECT 1 FROM courses WHERE course_id=?", (cid,), one=True): return err("Course not found", 404)
    run("INSERT OR IGNORE INTO enrollments(user_id,course_id) VALUES(?,?)", (g.uid, cid))
    return jsonify(ok=True)

@app.get("/api/courses/<int:cid>/topics")
@auth()
def topics(cid):
    return jsonify(q("SELECT topic_id,chapter_no,name FROM topics WHERE course_id=? ORDER BY chapter_no", (cid,)))

# ---------- question bank: search + filter ----------
@app.get("/api/questions")
@auth()
def questions():
    sql = """SELECT qu.question_id, qu.topic_id, qu.body, qu.option_a, qu.option_b, qu.option_c, qu.option_d,
             qu.correct_option, qu.explanation, qu.difficulty, t.chapter_no, t.name AS topic, c.code AS course
             FROM questions qu JOIN topics t USING(topic_id) JOIN courses c USING(course_id) WHERE qu.is_active=1"""
    a = []
    if request.args.get("course_id"):  sql += " AND c.course_id=?";   a.append(request.args["course_id"])
    if request.args.get("chapter"):    sql += " AND t.chapter_no=?";  a.append(request.args["chapter"])
    if request.args.get("topic_id"):   sql += " AND t.topic_id=?";    a.append(request.args["topic_id"])
    if request.args.get("difficulty"): sql += " AND qu.difficulty=?"; a.append(request.args["difficulty"].lower())
    if request.args.get("search"):     sql += " AND qu.body LIKE ?";  a.append(f"%{request.args['search']}%")
    sql += " ORDER BY t.chapter_no, qu.question_id LIMIT ? OFFSET ?"
    a += [min(int(request.args.get("limit", 50)), 500), int(request.args.get("offset", 0))]
    rows = q(sql, a)
    if g.role != "instructor":                      # students never receive the answers
        for r in rows: r.pop("correct_option"); r.pop("explanation")
    return jsonify(rows)

def question_payload(d):
    need = ["topic_id", "body", "option_a", "option_b", "option_c", "option_d", "correct_option"]
    if any(not str(d.get(k) or "").strip() for k in need): return None, "Missing fields: " + ", ".join(need)
    diff = (d.get("difficulty") or "medium").lower()
    if diff not in ("easy", "medium", "hard"): return None, "Invalid difficulty"
    if str(d["correct_option"]).upper() not in ("A", "B", "C", "D"): return None, "Invalid correct option"
    if not q("SELECT 1 FROM topics WHERE topic_id=?", (d["topic_id"],), one=True): return None, "Topic not found"
    return (d["topic_id"], d["body"].strip(), d["option_a"].strip(), d["option_b"].strip(), d["option_c"].strip(),
            d["option_d"].strip(), str(d["correct_option"]).upper(), diff, (d.get("explanation") or "").strip() or None), None

@app.post("/api/questions")
@auth("instructor")
def add_question():
    vals, e = question_payload(request.get_json(force=True))
    if e: return err(e)
    qid = run("""INSERT INTO questions(topic_id,body,option_a,option_b,option_c,option_d,correct_option,difficulty,explanation)
                 VALUES(?,?,?,?,?,?,?,?,?)""", vals)
    return jsonify(question_id=qid), 201

@app.put("/api/questions/<int:qid>")
@auth("instructor")
def edit_question(qid):
    if not q("SELECT 1 FROM questions WHERE question_id=? AND is_active=1", (qid,), one=True): return err("Question not found", 404)
    vals, e = question_payload(request.get_json(force=True))
    if e: return err(e)
    run("""UPDATE questions SET topic_id=?, body=?, option_a=?, option_b=?, option_c=?, option_d=?,
           correct_option=?, difficulty=?, explanation=? WHERE question_id=?""", vals + (qid,))
    return jsonify(ok=True)

@app.delete("/api/questions/<int:qid>")
@auth("instructor")
def delete_question(qid):
    """Soft delete: the question disappears from the bank and quizzes, students' past answers are kept."""
    if not q("SELECT 1 FROM questions WHERE question_id=? AND is_active=1", (qid,), one=True): return err("Question not found", 404)
    run("UPDATE questions SET is_active=0 WHERE question_id=?", (qid,))
    return jsonify(ok=True)

# ---------- quiz flow ----------
def public_q(r):
    return {"question_id": r["question_id"], "body": r["body"], "difficulty": r["difficulty"],
            "topic_id": r["topic_id"], "chapter_no": r.get("chapter_no"), "topic": r.get("topic"),
            "options": {"A": r["option_a"], "B": r["option_b"], "C": r["option_c"], "D": r["option_d"]}}

def update_mastery_for_user(uid, course_id):
    """Runs the knowledge-tracing model on the student's full answer history and saves
    the predicted P(correct) per chapter in topic_mastery. Returns {topic_id: p}."""
    tids = [t["topic_id"] for t in q("SELECT topic_id FROM topics WHERE course_id=?", (course_id,))]
    hist = [(r["topic_id"], r["is_correct"], r["question_id"]) for r in q(
        """SELECT qu.topic_id, a.is_correct, a.question_id FROM attempts a JOIN questions qu USING(question_id)
           WHERE a.user_id=? ORDER BY a.created_at, a.attempt_id""", (uid,))]
    m = predict_mastery(hist, tids)
    now = datetime.utcnow().isoformat(sep=" ")
    for t, p in m.items():
        run("""INSERT INTO topic_mastery(user_id,topic_id,p_correct,updated_at) VALUES(?,?,?,?)
               ON CONFLICT(user_id,topic_id) DO UPDATE SET p_correct=excluded.p_correct, updated_at=excluded.updated_at""",
            (uid, t, p, now))
    return m

def pick_next(uid, course_id, session_id, mode):
    """Adaptive: pick a chapter at random with weight (1 - predicted)^2, so weak chapters come up most often
    but every chapter is still practised; never more than 3 questions in a row from one chapter;
    difficulty drawn with weights easy (1-p)^2, medium 2p(1-p), hard p^2; no question repeats in a session."""
    tps = q("SELECT topic_id FROM topics WHERE course_id=?", (course_id,))
    tids = [t["topic_id"] for t in tps]
    seen = {r["question_id"] for r in q("SELECT question_id FROM attempts WHERE session_id=?", (session_id,))}
    cand = q("""SELECT qu.*, t.chapter_no, t.name AS topic FROM questions qu JOIN topics t USING(topic_id)
                WHERE t.course_id=? AND qu.is_active=1""", (course_id,))
    cand = [c for c in cand if c["question_id"] not in seen]
    if not cand: return None
    if mode == "random":
        import random; return random.choice(cand)
    import random
    m = update_mastery_for_user(uid, course_id)
    avail = [t for t in m if any(c["topic_id"] == t for c in cand)]
    # weaker chapter -> more questions, but every chapter keeps a chance (weight = (1 - p)^2)
    recent = [r["topic_id"] for r in q("""SELECT qu.topic_id FROM attempts a JOIN questions qu USING(question_id)
                                           WHERE a.session_id=? ORDER BY a.attempt_id DESC LIMIT 3""", (session_id,))]
    if len(recent) == 3 and len(set(recent)) == 1 and len(avail) > 1:
        avail = [t for t in avail if t != recent[0]]        # 3 in a row from one chapter -> switch chapter
    topic = random.choices(avail, weights=[(1 - m[t]) ** 2 + 1e-6 for t in avail])[0]
    # difficulty is also a weighted draw: low level -> mostly easy, high level -> mostly hard
    #   easy = (1-p)^2 , medium = 2p(1-p) , hard = p^2      (they add up to 1)
    p = m[topic]
    pool = [c for c in cand if c["topic_id"] == topic]
    weights = {"easy": (1 - p) ** 2, "medium": 2 * p * (1 - p), "hard": p ** 2}
    levels = [d for d in weights if any(c["difficulty"] == d for c in pool)]
    want = random.choices(levels, weights=[weights[d] + 1e-6 for d in levels])[0]
    return random.choice([c for c in pool if c["difficulty"] == want])

@app.post("/api/quiz/start")
@auth("student")
def quiz_start():
    d = request.get_json(force=True)
    cid, mode = d.get("course_id"), d.get("mode", "adaptive")
    if mode not in ("adaptive", "random"): return err("Invalid mode")
    if not q("SELECT 1 FROM courses WHERE course_id=?", (cid,), one=True): return err("Course not found", 404)
    run("INSERT OR IGNORE INTO enrollments(user_id,course_id) VALUES(?,?)", (g.uid, cid))
    sid = run("INSERT INTO quiz_sessions(user_id,course_id,mode) VALUES(?,?,?)", (g.uid, cid, mode))
    nq = pick_next(g.uid, cid, sid, mode)
    return jsonify(session_id=sid, question=public_q(nq) if nq else None), 201

def own_session(sid):
    s = q("SELECT * FROM quiz_sessions WHERE session_id=? AND user_id=?", (sid, g.uid), one=True)
    return s

@app.get("/api/quiz/<int:sid>/next")
@auth("student")
def quiz_next(sid):
    s = own_session(sid)
    if not s: return err("Session not found", 404)
    nq = pick_next(g.uid, s["course_id"], sid, s["mode"])
    return jsonify(question=public_q(nq) if nq else None)

@app.post("/api/quiz/<int:sid>/answer")
@auth("student")
def quiz_answer(sid):
    s = own_session(sid)
    if not s: return err("Session not found", 404)
    if s["ended_at"]: return err("Session already ended")
    d = request.get_json(force=True)
    opt = (d.get("selected_option") or "").upper()
    ques = q("SELECT * FROM questions WHERE question_id=? AND is_active=1", (d.get("question_id"),), one=True)
    if not ques or opt not in "ABCD" or not opt: return err("Invalid question or option")
    if q("SELECT 1 FROM attempts WHERE session_id=? AND question_id=?", (sid, ques["question_id"]), one=True):
        return err("Already answered", 409)
    ok = int(opt == ques["correct_option"])
    run("INSERT INTO attempts(session_id,user_id,question_id,selected_option,is_correct,time_taken_sec) VALUES(?,?,?,?,?,?)",
        (sid, g.uid, ques["question_id"], opt, ok, d.get("time_taken_sec")))
    nq = pick_next(g.uid, s["course_id"], sid, s["mode"])
    m = q("SELECT ROUND(100.0*p_correct,1) p FROM topic_mastery WHERE user_id=? AND topic_id=?", (g.uid, ques["topic_id"]), one=True)
    return jsonify(is_correct=bool(ok), correct_option=ques["correct_option"], explanation=ques["explanation"],
                   topic_predicted_pct=m["p"] if m else None, next_question=public_q(nq) if nq else None)

@app.post("/api/quiz/<int:sid>/end")
@auth("student")
def quiz_end(sid):
    s = own_session(sid)
    if not s: return err("Session not found", 404)
    run("UPDATE quiz_sessions SET ended_at=COALESCE(ended_at, CURRENT_TIMESTAMP) WHERE session_id=?", (sid,))
    r = q("SELECT COUNT(*) n, COALESCE(SUM(is_correct),0) c FROM attempts WHERE session_id=?", (sid,), one=True)
    return jsonify(answered=r["n"], correct=r["c"], accuracy_pct=round(100 * r["c"] / r["n"], 1) if r["n"] else 0)

# ---------- student reports (dashboard) ----------
@app.get("/api/reports/student/dashboard")
@auth("student")
def student_dashboard():
    uid = g.uid
    tot = q("SELECT COUNT(*) n, COALESCE(AVG(is_correct),0) acc FROM attempts WHERE user_id=?", (uid,), one=True)
    sessions_week = q("""SELECT COUNT(*) n FROM quiz_sessions WHERE user_id=? AND started_at >= datetime('now','-7 days')""",
                      (uid,), one=True)["n"]
    topics_acc = q("""SELECT t.topic_id, t.chapter_no, t.name, COUNT(a.attempt_id) attempts,
                      ROUND(100.0*AVG(a.is_correct),1) accuracy_pct,
                      ROUND(100.0*COALESCE(m.p_correct,0.5),1) predicted_pct
                      FROM topics t
                      LEFT JOIN questions qu ON qu.topic_id=t.topic_id
                      LEFT JOIN attempts a ON a.question_id=qu.question_id AND a.user_id=?
                      LEFT JOIN topic_mastery m ON m.topic_id=t.topic_id AND m.user_id=?
                      WHERE t.course_id IN (SELECT course_id FROM enrollments WHERE user_id=?)
                      GROUP BY t.topic_id ORDER BY t.chapter_no""", (uid, uid, uid))
    daily = q("""SELECT date(created_at) day, COUNT(*) questions FROM attempts
                 WHERE user_id=? AND created_at >= datetime('now','-6 days') GROUP BY day ORDER BY day""", (uid,))
    rec = None
    played = [t for t in topics_acc if t["attempts"] > 0]
    if played:
        w = min(played, key=lambda t: t["predicted_pct"])
        rec = {"topic_id": w["topic_id"], "chapter_no": w["chapter_no"], "topic": w["name"],
               "predicted_pass_pct": w["predicted_pct"],
               "message": f"Review Chapter {w['chapter_no']}: {w['name']} (predicted {w['predicted_pct']}% correct)"}
    return jsonify(questions_solved=tot["n"], avg_accuracy_pct=round(100 * tot["acc"], 1),
                   sessions_this_week=sessions_week, knowledge_by_topic=topics_acc,
                   weekly_activity=daily, recommendation=rec)

@app.get("/api/reports/student/history")
@auth("student")
def student_history():
    return jsonify(q("""SELECT s.session_id, s.mode, s.started_at, s.ended_at, c.code,
                        COUNT(a.attempt_id) answered, COALESCE(SUM(a.is_correct),0) correct
                        FROM quiz_sessions s JOIN courses c USING(course_id)
                        LEFT JOIN attempts a USING(session_id)
                        WHERE s.user_id=? GROUP BY s.session_id ORDER BY s.started_at DESC LIMIT 50""", (g.uid,)))

# ---------- instructor reports ----------
@app.get("/api/reports/hardest-questions")
@auth("instructor")
def hardest_questions():
    limit = int(request.args.get("limit", 10)); min_att = int(request.args.get("min_attempts", 3))
    sql = """SELECT qu.question_id, qu.body, qu.difficulty, t.chapter_no, t.name topic,
             COUNT(a.attempt_id) attempts, ROUND(100.0*AVG(a.is_correct),1) correct_pct
             FROM questions qu JOIN topics t USING(topic_id) JOIN attempts a USING(question_id)
             WHERE 1=1 """
    args = []
    if request.args.get("chapter"): sql += " AND t.chapter_no=?"; args.append(request.args["chapter"])
    if request.args.get("difficulty"): sql += " AND qu.difficulty=?"; args.append(request.args["difficulty"])
    sql += " GROUP BY qu.question_id HAVING attempts>=? ORDER BY correct_pct ASC LIMIT ?"
    return jsonify(q(sql, args + [min_att, limit]))

@app.get("/api/reports/topic-accuracy")
@auth("instructor")
def topic_accuracy():
    return jsonify(q("""SELECT t.chapter_no, t.name topic, COUNT(a.attempt_id) attempts,
                        ROUND(100.0*AVG(a.is_correct),1) correct_pct
                        FROM topics t LEFT JOIN questions qu USING(topic_id) LEFT JOIN attempts a USING(question_id)
                        GROUP BY t.topic_id ORDER BY correct_pct ASC"""))

@app.get("/api/reports/weak-students")
@auth("instructor")
def weak_students():
    return jsonify(q("""SELECT u.user_id, u.full_name, COUNT(a.attempt_id) attempts,
                        ROUND(100.0*AVG(a.is_correct),1) accuracy_pct
                        FROM users u JOIN attempts a ON a.user_id=u.user_id
                        WHERE u.role='student' GROUP BY u.user_id HAVING attempts>=5
                        ORDER BY accuracy_pct ASC LIMIT ?""", (int(request.args.get("limit", 10)),)))

@app.get("/api/reports/weekly-activity")
@auth("instructor")
def weekly_activity():
    return jsonify(q("""SELECT date(created_at) day, COUNT(*) attempts, COUNT(DISTINCT user_id) active_students
                        FROM attempts WHERE created_at >= datetime('now','-7 days') GROUP BY day ORDER BY day"""))

@app.get("/api/reports/difficulty-accuracy")
@auth("instructor")
def difficulty_accuracy():
    """Correct % and average answer time per difficulty level (checks that the levels make sense)."""
    return jsonify(q("""SELECT qu.difficulty, COUNT(a.attempt_id) attempts,
                        ROUND(100.0*AVG(a.is_correct),1) correct_pct, ROUND(AVG(a.time_taken_sec),1) avg_time_sec
                        FROM attempts a JOIN questions qu USING(question_id)
                        GROUP BY qu.difficulty
                        ORDER BY CASE qu.difficulty WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END"""))

@app.get("/api/reports/mislabeled-questions")
@auth("instructor")
def mislabeled_questions():
    """Questions whose difficulty label does not match the students' results."""
    min_att = int(request.args.get("min_attempts", 5))
    return jsonify(q("""SELECT qu.question_id, qu.body, qu.difficulty, t.chapter_no,
                        COUNT(a.attempt_id) attempts, ROUND(100.0*AVG(a.is_correct),1) correct_pct,
                        CASE WHEN qu.difficulty='easy' THEN 'looks harder than easy'
                             ELSE 'looks easier than hard' END AS note
                        FROM questions qu JOIN topics t USING(topic_id) JOIN attempts a USING(question_id)
                        GROUP BY qu.question_id HAVING attempts>=?
                           AND ((qu.difficulty='easy' AND correct_pct<50) OR (qu.difficulty='hard' AND correct_pct>85))
                        ORDER BY correct_pct""", (min_att,)))

# ---------- endpoints used by the front end (frontend/index.html) ----------
def last_7_days(rows):
    by_day = {r["day"]: r["questions"] for r in rows}
    today = datetime.now().date()
    return [{"day": str(today - timedelta(days=i)), "questions": by_day.get(str(today - timedelta(days=i)), 0)}
            for i in range(6, -1, -1)]

@app.get("/api/dashboard")
@auth()
def dashboard():
    """Student: his own numbers and AI predictions. Instructor: the same numbers for the whole class."""
    if g.role == "student":
        who, args = "a.user_id=?", (g.uid,)
        mastery = q("""SELECT t.topic_id, t.chapter_no, t.name, ROUND(100.0*COALESCE(m.p_correct,0.5),1) predicted_pct
                       FROM topics t LEFT JOIN topic_mastery m ON m.topic_id=t.topic_id AND m.user_id=?
                       WHERE t.course_id=1 ORDER BY t.chapter_no""", (g.uid,))
        sessions = q("SELECT COUNT(*) n FROM quiz_sessions WHERE user_id=? AND started_at >= datetime('now','-7 days')", (g.uid,), one=True)["n"]
    else:
        who, args = "1=1", ()
        mastery = q("""SELECT t.topic_id, t.chapter_no, t.name, ROUND(100.0*COALESCE(AVG(m.p_correct),0.5),1) predicted_pct
                       FROM topics t LEFT JOIN topic_mastery m ON m.topic_id=t.topic_id
                       WHERE t.course_id=1 GROUP BY t.topic_id ORDER BY t.chapter_no""")
        sessions = q("SELECT COUNT(*) n FROM quiz_sessions WHERE started_at >= datetime('now','-7 days')", one=True)["n"]
    tot = q(f"SELECT COUNT(*) n, COALESCE(AVG(is_correct),0) acc FROM attempts a WHERE {who}", args, one=True)
    acc = {r["topic_id"]: r for r in q(f"""SELECT qu.topic_id, COUNT(*) attempts, ROUND(100.0*AVG(a.is_correct),1) accuracy_pct
                                           FROM attempts a JOIN questions qu USING(question_id) WHERE {who}
                                           GROUP BY qu.topic_id""", args)}
    for t in mastery:
        t["attempts"] = acc.get(t["topic_id"], {}).get("attempts", 0)
        t["accuracy_pct"] = acc.get(t["topic_id"], {}).get("accuracy_pct")
    daily = q(f"""SELECT date(created_at) day, COUNT(*) questions FROM attempts a
                  WHERE {who} AND date(created_at) >= date('now','localtime','-6 days') GROUP BY day""", args)
    weakest = min(mastery, key=lambda t: t["predicted_pct"]) if mastery else None
    return jsonify(role=g.role, questions_solved=tot["n"], accuracy_pct=round(100 * tot["acc"], 1),
                   avg_mastery_pct=round(sum(t["predicted_pct"] for t in mastery) / len(mastery), 1) if mastery else 0,
                   sessions_this_week=sessions, knowledge_by_topic=mastery, weekly_activity=last_7_days(daily),
                   recommendation=weakest)

@app.get("/api/reports/summary")
@auth()
def reports_summary():
    """Reports page: most-missed questions and weakest chapters for today / this week / this month.
    Student = his own answers, instructor = all students."""
    days = {"day": 1, "week": 7, "month": 30}.get(request.args.get("period", "week"), 7)
    who, args = ("a.user_id=?", [g.uid]) if g.role == "student" else ("1=1", [])
    since = f"datetime('now','-{days} days')"
    hard = q(f"""SELECT qu.question_id, qu.body, t.chapter_no, t.name topic, COUNT(*) attempts,
                 SUM(1-a.is_correct) errors, ROUND(100.0*(1-AVG(a.is_correct)),1) error_pct
                 FROM attempts a JOIN questions qu USING(question_id) JOIN topics t USING(topic_id)
                 WHERE {who} AND a.created_at >= {since}
                 GROUP BY qu.question_id HAVING errors > 0 ORDER BY errors DESC, error_pct DESC LIMIT 5""", args)
    weak = q(f"""SELECT t.topic_id, t.chapter_no, t.name, COUNT(*) attempts, ROUND(100.0*AVG(a.is_correct),1) accuracy_pct
                 FROM attempts a JOIN questions qu USING(question_id) JOIN topics t USING(topic_id)
                 WHERE {who} AND a.created_at >= {since}
                 GROUP BY t.topic_id ORDER BY accuracy_pct ASC""", args)
    tot = q(f"SELECT COUNT(*) n, COUNT(DISTINCT a.user_id) students FROM attempts a WHERE {who} AND a.created_at >= {since}", args, one=True)
    return jsonify(period=request.args.get("period", "week"), answers=tot["n"], students=tot["students"],
                   hard_questions=hard, weak_topics=weak)

@app.get("/")
def index():
    return send_from_directory(FRONTEND, "index.html")

@app.get("/api/health")
def health():
    import mastery
    labels = {"dktq-gru": "DKT-Q (GRU)", "dktq-lstm": "DKT-Q (LSTM)", "dkt-gru": "DKT (GRU)", "dkt-lstm": "DKT (LSTM)", "sakt": "SAKT"}
    return jsonify(status="ok", ai_model=mastery.MODEL_NAME, ai_model_label=labels.get(mastery.MODEL_NAME, mastery.MODEL_NAME),
                   instructor_key_required=bool(INSTRUCTOR_KEY))

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):           # first run: build the demo database automatically
        import seed; seed.main()
    init_db()
    print("\n  ActiveLearn AI is running ->  open http://localhost:5000  in your browser\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
