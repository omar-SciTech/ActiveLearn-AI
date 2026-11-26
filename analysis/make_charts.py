"""Draws the report charts from the database (PNG files in analysis/charts/).

  python make_charts.py

Charts (each one comes from a query in reports.sql):
  1_correct_by_chapter.png      R2  correct % per chapter
  2_activity_last_7_days.png    R5  answers per day
  3_difficulty.png              R7  correct % and average time per difficulty
  4_hardest_questions.png       R3  hardest questions
  5_weekly_trend.png            R6  correct % week by week
  6_ai_predictions.png          R10 the model's predicted knowledge per student and chapter
"""
import os, sqlite3, textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(os.path.dirname(HERE), "backend", "activelearn.db")
OUT = os.path.join(HERE, "charts")

BLUE, TEXT, MUTED, GRID = "#257de0", "#191919", "#666666", "#e6e6e6"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.titleweight": "bold", "axes.titlesize": 12, "axes.titlecolor": TEXT})


def q(con, sql):
    return con.execute(sql).fetchall()


def finish(fig, ax, name, note=None):
    for a in (ax if isinstance(ax, (list, tuple)) else [ax]):
        a.spines[["top", "right", "left"]].set_visible(False)
        a.set_axisbelow(True)
    if note:
        fig.text(0.01, 0.01, note, fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.03 if note else 0, 1, 1))
    fig.savefig(os.path.join(OUT, name), dpi=150)
    plt.close(fig)
    print("saved", name)


def hbar(ax, labels, values, fmt="{:.0f}%"):
    y = range(len(labels))
    ax.barh(list(y), values, color=BLUE, height=0.6)
    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()
    ax.xaxis.grid(True, color=GRID)
    for i, v in enumerate(values):
        ax.text(v + max(values) * 0.01, i, fmt.format(v), va="center", color=TEXT, fontsize=9)


def main():
    os.makedirs(OUT, exist_ok=True)
    con = sqlite3.connect(DB)
    note = "Data: ActiveLearn demo database (simulated students)"

    # 1. correct % per chapter
    r = q(con, """SELECT t.chapter_no, t.name, ROUND(100.0*AVG(a.is_correct),1) FROM topics t
                  JOIN questions q USING(topic_id) JOIN attempts a USING(question_id)
                  GROUP BY t.topic_id ORDER BY t.chapter_no""")
    fig, ax = plt.subplots(figsize=(8, 3.6))
    hbar(ax, [f"Ch {c}: {textwrap.shorten(n, 38)}" for c, n, _ in r], [v for *_, v in r])
    ax.set_xlim(0, 100); ax.set_xlabel("correct answers (%)")
    ax.set_title("Correct answers per chapter", loc="left")
    finish(fig, ax, "1_correct_by_chapter.png", note)

    # 2. activity, last 7 days
    r = q(con, """SELECT date(created_at) d, COUNT(*) FROM attempts
                  WHERE created_at >= datetime('now','-7 days') GROUP BY d ORDER BY d""")
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.bar([d[5:] for d, _ in r], [n for _, n in r], color=BLUE, width=0.6)
    ax.yaxis.grid(True, color=GRID)
    for i, (_, n) in enumerate(r):
        ax.text(i, n, str(n), ha="center", va="bottom", color=TEXT, fontsize=9)
    ax.set_ylabel("answers"); ax.set_title("Answers per day - last 7 days", loc="left")
    finish(fig, ax, "2_activity_last_7_days.png", note)

    # 3. difficulty: two small charts (two different units -> two axes, never one dual axis)
    r = q(con, """SELECT q.difficulty, ROUND(100.0*AVG(a.is_correct),1), ROUND(AVG(a.time_taken_sec),1)
                  FROM questions q JOIN attempts a USING(question_id) GROUP BY q.difficulty
                  ORDER BY CASE q.difficulty WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END""")
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4))
    labels = [d for d, *_ in r]
    for a, vals, title, unit in ((ax[0], [x[1] for x in r], "Correct answers (%)", "%"),
                                 (ax[1], [x[2] for x in r], "Average time (seconds)", "s")):
        a.bar(labels, vals, color=BLUE, width=0.55)
        a.yaxis.grid(True, color=GRID); a.set_title(title, loc="left")
        for i, v in enumerate(vals):
            a.text(i, v, f"{v:.0f}{unit}", ha="center", va="bottom", color=TEXT, fontsize=9)
    ax[0].set_ylim(0, 100)
    finish(fig, [ax[0], ax[1]], "3_difficulty.png", note)

    # 4. hardest questions
    r = q(con, """SELECT q.question_id, q.body, ROUND(100.0*AVG(a.is_correct),1) p, COUNT(*) n
                  FROM questions q JOIN attempts a USING(question_id)
                  GROUP BY q.question_id HAVING n>=5 ORDER BY p LIMIT 8""")
    fig, ax = plt.subplots(figsize=(9, 4.2))
    hbar(ax, [f"Q{i}: {textwrap.shorten(b, 55)}" for i, b, *_ in r], [p for _, _, p, _ in r])
    ax.set_xlim(0, 100); ax.set_xlabel("correct answers (%)")
    ax.set_title("Hardest questions (lowest correct %)", loc="left")
    finish(fig, ax, "4_hardest_questions.png", note)

    # 5. weekly trend
    r = q(con, """SELECT strftime('%Y-W%W', created_at) w, ROUND(100.0*AVG(is_correct),1)
                  FROM attempts GROUP BY w ORDER BY w""")
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.plot([w for w, _ in r], [v for _, v in r], color=BLUE, linewidth=2, marker="o", markersize=7)
    ax.yaxis.grid(True, color=GRID); ax.set_ylim(0, 100)
    ax.text(len(r) - 1, r[-1][1] + 3, f"{r[-1][1]:.0f}%", ha="center", color=TEXT, fontsize=9)
    ax.set_ylabel("correct answers (%)"); ax.set_title("Correct answers week by week", loc="left")
    finish(fig, ax, "5_weekly_trend.png", note)

    # 6. AI predictions heatmap (named demo students + the 7 weakest simulated ones)
    users = q(con, """SELECT u.user_id, u.full_name FROM users u JOIN topic_mastery m USING(user_id)
                      GROUP BY u.user_id ORDER BY (u.full_name LIKE 'Sim%'), AVG(m.p_correct) LIMIT 10""")
    chapters = q(con, "SELECT topic_id, chapter_no FROM topics ORDER BY chapter_no")
    grid = [[con.execute("SELECT p_correct FROM topic_mastery WHERE user_id=? AND topic_id=?", (u, t)).fetchone()[0] * 100
             for t, _ in chapters] for u, _ in users]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    im = ax.imshow(grid, cmap="Blues", vmin=30, vmax=100, aspect="auto")
    ax.set_xticks(range(len(chapters)), [f"Ch {c}" for _, c in chapters])
    ax.set_yticks(range(len(users)), [n for _, n in users])
    for i, row in enumerate(grid):
        for j, v in enumerate(row):
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8, color="white" if v > 75 else TEXT)
    cb = fig.colorbar(im, ax=ax, fraction=0.03); cb.set_label("predicted P(correct) %")
    ax.set_title("AI predicted knowledge per chapter", loc="left")
    for s in ax.spines.values(): s.set_visible(False)
    fig.text(0.01, 0.01, note + " - predictions from the active IS201 model (model/saved/active_is201.json)", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(os.path.join(OUT, "6_ai_predictions.png"), dpi=150); plt.close(fig)
    print("saved 6_ai_predictions.png")


if __name__ == "__main__":
    main()
