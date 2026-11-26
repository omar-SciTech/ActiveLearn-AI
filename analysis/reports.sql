-- =====================================================================
-- ActiveLearn AI - reports.sql   (Analysis part)
-- Every report the system produces, written as plain SQL.
-- How to use: open backend/activelearn.db in DB Browser for SQLite,
-- go to "Execute SQL", select ONE query and press Ctrl+Enter (or F5 for all).
-- The same queries are used by the backend API and by make_charts.py.
-- =====================================================================


-- R1. Overview (KPIs): students, questions, answers, overall correct %
SELECT
  (SELECT COUNT(*) FROM users WHERE role = 'student')        AS students,
  (SELECT COUNT(*) FROM questions)                           AS questions,
  (SELECT COUNT(*) FROM attempts)                            AS answers,
  (SELECT ROUND(100.0 * AVG(is_correct), 1) FROM attempts)   AS correct_pct;


-- R2. Correct % per chapter (weakest chapters first)
SELECT t.chapter_no, t.name AS chapter,
       COUNT(a.attempt_id)                  AS answers,
       ROUND(100.0 * AVG(a.is_correct), 1)  AS correct_pct
FROM topics t
JOIN questions q USING (topic_id)
JOIN attempts  a USING (question_id)
GROUP BY t.topic_id
ORDER BY correct_pct ASC;


-- R3. Hardest questions (lowest correct %, at least 5 answers)
SELECT q.question_id, t.chapter_no, q.difficulty, q.body,
       COUNT(a.attempt_id)                  AS answers,
       ROUND(100.0 * AVG(a.is_correct), 1)  AS correct_pct
FROM questions q
JOIN topics   t USING (topic_id)
JOIN attempts a USING (question_id)
GROUP BY q.question_id
HAVING answers >= 5
ORDER BY correct_pct ASC
LIMIT 10;


-- R4. Weakest students (lowest correct %, at least 10 answers)
SELECT u.user_id, u.full_name,
       COUNT(a.attempt_id)                  AS answers,
       ROUND(100.0 * AVG(a.is_correct), 1)  AS correct_pct
FROM users u
JOIN attempts a ON a.user_id = u.user_id
WHERE u.role = 'student'
GROUP BY u.user_id
HAVING answers >= 10
ORDER BY correct_pct ASC
LIMIT 10;


-- R5. Activity per day - last 7 days (answers and active students)
SELECT date(created_at)            AS day,
       COUNT(*)                    AS answers,
       COUNT(DISTINCT user_id)     AS active_students
FROM attempts
WHERE created_at >= datetime('now', '-7 days')
GROUP BY day
ORDER BY day;


-- R6. Activity per week (whole history)
SELECT strftime('%Y-W%W', created_at) AS week,
       COUNT(*)                       AS answers,
       COUNT(DISTINCT user_id)        AS active_students,
       ROUND(100.0 * AVG(is_correct), 1) AS correct_pct
FROM attempts
GROUP BY week
ORDER BY week;


-- R7. Correct % and average time per difficulty (do the labels make sense?)
SELECT q.difficulty,
       COUNT(a.attempt_id)                  AS answers,
       ROUND(100.0 * AVG(a.is_correct), 1)  AS correct_pct,
       ROUND(AVG(a.time_taken_sec), 1)      AS avg_time_sec
FROM questions q
JOIN attempts a USING (question_id)
GROUP BY q.difficulty
ORDER BY CASE q.difficulty WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END;


-- R8. Questions with a wrong difficulty label
--     (an "easy" question most students fail, or a "hard" one almost everyone solves)
SELECT q.question_id, t.chapter_no, q.difficulty, q.body,
       COUNT(a.attempt_id)                  AS answers,
       ROUND(100.0 * AVG(a.is_correct), 1)  AS correct_pct
FROM questions q
JOIN topics   t USING (topic_id)
JOIN attempts a USING (question_id)
GROUP BY q.question_id
HAVING answers >= 5
   AND ((q.difficulty = 'easy' AND correct_pct < 50)
     OR (q.difficulty = 'hard' AND correct_pct > 85));


-- R9. Progress of one student, session by session (change user_id = 2)
SELECT s.session_id, date(s.started_at) AS day,
       COUNT(a.attempt_id)                  AS answered,
       ROUND(100.0 * AVG(a.is_correct), 1)  AS correct_pct
FROM quiz_sessions s
JOIN attempts a USING (session_id)
WHERE s.user_id = 2
GROUP BY s.session_id
ORDER BY s.started_at;


-- R10. AI predictions: probability of a correct answer per student and chapter
--      (written by the DKT model into topic_mastery)
SELECT u.full_name, t.chapter_no, t.name AS chapter,
       ROUND(100.0 * m.p_correct, 1) AS predicted_correct_pct
FROM topic_mastery m
JOIN users  u USING (user_id)
JOIN topics t USING (topic_id)
ORDER BY u.user_id, t.chapter_no;


-- R11. AI recommendation: the chapter each student should review (lowest prediction)
SELECT u.full_name, t.chapter_no, t.name AS review_chapter,
       ROUND(100.0 * m.p_correct, 1) AS predicted_correct_pct
FROM topic_mastery m
JOIN users  u USING (user_id)
JOIN topics t USING (topic_id)
WHERE m.p_correct = (SELECT MIN(p_correct) FROM topic_mastery x WHERE x.user_id = m.user_id)
ORDER BY predicted_correct_pct;


-- R12. Students at risk: predicted below 60% in at least one chapter
SELECT u.full_name,
       SUM(m.p_correct < 0.6)              AS weak_chapters,
       ROUND(100.0 * AVG(m.p_correct), 1)  AS avg_predicted_pct
FROM topic_mastery m
JOIN users u USING (user_id)
GROUP BY u.user_id
HAVING weak_chapters >= 1
ORDER BY weak_chapters DESC, avg_predicted_pct;


-- R13. Search & filter the question bank (example: chapter 2, easy, contains "key")
SELECT q.question_id, t.chapter_no, q.difficulty, q.body
FROM questions q
JOIN topics t USING (topic_id)
WHERE t.chapter_no = 2
  AND q.difficulty = 'easy'
  AND q.body LIKE '%key%';
