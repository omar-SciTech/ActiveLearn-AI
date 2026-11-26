# Analysis part (reports, charts, data for the AI)

| File | What it does |
|---|---|
| `reports.sql` | 13 reports written in SQL (run them in DB Browser on `backend/activelearn.db`) |
| `make_charts.py` | Draws the charts below from the database into `charts/` |
| `export_for_ai.py` | Exports every answer in order to `exports/attempts_sequences.csv` (input for the model) |

## Reports (reports.sql)
| # | Report | Who uses it |
|---|---|---|
| R1 | Overview: students, questions, answers, correct % | instructor |
| R2 | Correct % per chapter | instructor |
| R3 | Hardest questions | instructor |
| R4 | Weakest students | instructor |
| R5 | Activity per day (last 7 days) | instructor / student |
| R6 | Activity and correct % per week | instructor |
| R7 | Correct % and average time per difficulty | instructor |
| R8 | Questions with a wrong difficulty label | instructor |
| R9 | One student's progress session by session | student |
| R10 | AI predicted knowledge per student and chapter | student / instructor |
| R11 | AI recommendation: chapter to review | student |
| R12 | Students at risk (predicted < 60% in a chapter) | instructor |
| R13 | Search and filter the question bank | everyone |

## Charts (charts/)
1. `1_correct_by_chapter.png` (R2)
2. `2_activity_last_7_days.png` (R5)
3. `3_difficulty.png` (R7)
4. `4_hardest_questions.png` (R3)
5. `5_weekly_trend.png` (R6)
6. `6_ai_predictions.png` (R10)

## Run
```
cd backend && python seed.py          # build the database (if not built yet)
cd ../model && python predict_all.py  # AI predictions into the database
cd ../analysis
python make_charts.py
python export_for_ai.py
```
Note: the current answers are **simulated** (see `database/simulate_students.py`); the same reports work unchanged on real answers.
