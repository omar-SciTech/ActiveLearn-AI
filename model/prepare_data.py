"""Prepares the answer sequences for the models.

  python prepare_data.py assist   -> real data: ASSISTments 2009-2010 skill builder (corrected, collapsed)
  python prepare_data.py is201    -> IS201: simulated students on our own question bank (database/create_database.py)
  python prepare_data.py is201 --from-export ../analysis/exports/attempts_sequences.csv
                                  -> IS201 from REAL app answers (once students have used the app)

Output (data/processed/):
  <name>_sequences.pkl : {"train": [...], "val": [...], "test": [...]}
                         each item = (user, skills[], corrects[], questions[])
  <name>_meta.json     : skill map, question map, names, statistics, priors
Split is by STUDENT (80% train / 10% validation / 10% test): the model is tested on students it never saw.
Questions seen fewer than 2 times in the training students share one "rare question" index (1).
"""
import argparse, json, os, pickle, random, sqlite3, sys
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "data", "raw", "skill_builder_data_corrected_collapsed.csv")
OUT = os.path.join(HERE, "data", "processed")
DB_DIR = os.path.join(os.path.dirname(HERE), "database")
MIN_LEN = 3            # ignore students with fewer than 3 answers
MIN_Q_COUNT = 2        # rarer questions -> shared index 1


def split_users(seqs, seed=42):
    """seqs: {user: (skills, corrects, raw_question_ids)} -> splits with question ids mapped to indexes."""
    users = sorted(seqs, key=str)
    random.Random(seed).shuffle(users)
    n = len(users)
    a, b = int(0.8 * n), int(0.9 * n)
    parts = {"train": users[:a], "val": users[a:b], "test": users[b:]}
    counts = Counter(str(q) for u in parts["train"] for q in seqs[u][2])
    qmap = {q: i + 2 for i, q in enumerate(sorted((q for q, k in counts.items() if k >= MIN_Q_COUNT), key=lambda x: (len(x), x)))}
    splits = {k: [(u, seqs[u][0], seqs[u][1], [qmap.get(str(q), 1) for q in seqs[u][2]]) for u in us]
              for k, us in parts.items()}
    return splits, qmap


def save(name, splits, qmap, meta):
    os.makedirs(OUT, exist_ok=True)
    pickle.dump(splits, open(os.path.join(OUT, f"{name}_sequences.pkl"), "wb"))
    meta["n_questions"] = len(qmap) + 2
    meta["question_map"] = qmap
    meta["stats"] = {k: len(v) for k, v in splits.items()} | {
        "interactions": sum(len(x[1]) for part in splits.values() for x in part),
        "questions_with_own_embedding": len(qmap)}
    tot, cor = defaultdict(int), defaultdict(int)
    for _, s, c, _ in splits["train"]:
        for k, v in zip(s, c):
            tot[k] += 1; cor[k] += v
    # average correctness per skill in the training students = prediction when there is no history
    meta["prior"] = [round((cor[k] + 1) / (tot[k] + 2), 4) for k in range(meta["n_skills"])]
    json.dump(meta, open(os.path.join(OUT, f"{name}_meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[{name}] skills={meta['n_skills']}  questions={len(qmap)}  students={meta['stats']}")


def prepare_assist():
    import pandas as pd
    df = pd.read_csv(RAW, encoding="ISO-8859-15", low_memory=False)
    print("raw rows:", len(df))
    df = df.dropna(subset=["skill_id"])                       # rows without a skill cannot be traced
    df = df[df["correct"].isin([0, 1])]
    df["skill_id"] = df["skill_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    qcol = "problem_id" if "problem_id" in df else ("assistment_id" if "assistment_id" in df else "skill_id")
    df["qid"] = df[qcol].astype(str).str.replace(r"\.0$", "", regex=True)
    df = df.sort_values(["user_id", "order_id"])               # order_id = the order the answers happened
    skills = sorted(df["skill_id"].unique(), key=lambda s: (len(s), s))
    smap = {s: i for i, s in enumerate(skills)}
    names = df.drop_duplicates("skill_id").set_index("skill_id")["skill_name"].to_dict() if "skill_name" in df else {}
    seqs = {}
    for uid, g in df.groupby("user_id"):
        if len(g) >= MIN_LEN:
            seqs[int(uid)] = ([smap[s] for s in g["skill_id"]], g["correct"].astype(int).tolist(), g["qid"].tolist())
    splits, qmap = split_users(seqs)
    meta = {"dataset": "ASSISTments 2009-2010 skill builder (corrected, collapsed)",
            "source": "https://sites.google.com/site/assistmentsdata/home/2009-2010-assistment-data/skill-builder-data-2009-2010",
            "question_column": qcol, "n_skills": len(skills), "skill_map": smap,
            "skill_names": {str(smap[s]): str(names.get(s, s)) for s in skills}}
    save("assist", splits, qmap, meta)


def prepare_is201(n_students, export_csv=None):
    sys.path.insert(0, DB_DIR)
    from create_database import create_tables, insert_data
    con = sqlite3.connect(":memory:")
    create_tables(con)
    insert_data(con)
    topics = con.execute("SELECT topic_id, chapter_no, name FROM topics WHERE course_id=1 ORDER BY chapter_no").fetchall()
    tmap = {str(t[0]): i for i, t in enumerate(topics)}        # topic_id -> skill index
    qtopic = {str(q): t for q, t in con.execute(
        "SELECT q.question_id, q.topic_id FROM questions q JOIN topics t USING(topic_id) WHERE t.course_id=1")}
    seqs = {}
    if export_csv:                                             # real answers exported from the app
        import csv
        by_user = defaultdict(list)
        for r in csv.DictReader(open(export_csv, encoding="utf-8")):
            by_user[r["user_id"]].append((int(r["seq"]), tmap[r["topic_id"]], int(r["is_correct"]), r["question_id"]))
        for u, lst in by_user.items():
            lst.sort()
            if len(lst) >= MIN_LEN:
                seqs[u] = ([x[1] for x in lst], [x[2] for x in lst], [x[3] for x in lst])
        source = f"real app answers exported to {os.path.basename(export_csv)}"
    else:                                                      # SIMULATED students (see simulate_students.py)
        sys.path.insert(0, DB_DIR)
        from simulate_students import simulate_sequence, load_questions
        questions = load_questions(con)
        rng = random.Random(2026)
        for u in range(n_students):
            flat = [a for s in simulate_sequence(rng, questions, rng.randint(4, 14), rng.randint(6, 10)) for a in s]
            seqs[u] = ([tmap[str(a["topic_id"])] for a in flat], [a["is_correct"] for a in flat],
                       [a["question_id"] for a in flat])
        source = f"SIMULATED: {n_students} simulated students on the 60-question IS201 bank"
    splits, qmap = split_users(seqs)
    meta = {"dataset": "IS201 question bank", "source": source, "n_skills": len(topics), "skill_map": tmap,
            "skill_names": {str(i): f"Ch {t[1]}: {t[2]}" for i, t in enumerate(topics)},
            "question_topic": qtopic}
    save("is201", splits, qmap, meta)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", choices=["assist", "is201"])
    ap.add_argument("--students", type=int, default=3000, help="number of simulated students (is201)")
    ap.add_argument("--from-export", default=None, help="CSV exported by analysis/export_for_ai.py (is201)")
    a = ap.parse_args()
    prepare_assist() if a.dataset == "assist" else prepare_is201(a.students, a.from_export)
