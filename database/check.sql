-- =====================================================================
-- ActiveLearn AI - check.sql
-- Run after schema.sql + data.sql to check that everything is correct.
-- =====================================================================

-- 1. Number of rows in every table
SELECT 'users' AS table_name, COUNT(*) AS rows FROM users
UNION ALL SELECT 'courses', COUNT(*) FROM courses
UNION ALL SELECT 'enrollments', COUNT(*) FROM enrollments
UNION ALL SELECT 'topics', COUNT(*) FROM topics
UNION ALL SELECT 'questions', COUNT(*) FROM questions
UNION ALL SELECT 'quiz_sessions', COUNT(*) FROM quiz_sessions
UNION ALL SELECT 'attempts', COUNT(*) FROM attempts
UNION ALL SELECT 'topic_mastery', COUNT(*) FROM topic_mastery;

-- 2. Foreign keys: returns NO rows when every relation is valid
PRAGMA foreign_key_check;

-- 3. Questions per chapter and per difficulty
SELECT t.chapter_no, t.name, q.difficulty, COUNT(*) AS questions
FROM topics t JOIN questions q USING (topic_id)
GROUP BY t.chapter_no, q.difficulty
ORDER BY t.chapter_no;

-- 4. The correct answers are spread over A, B, C and D
SELECT correct_option, COUNT(*) AS questions
FROM questions
GROUP BY correct_option;

-- 5. Every question has an explanation (should return 0)
SELECT COUNT(*) AS questions_without_explanation
FROM questions
WHERE explanation IS NULL OR explanation = '';

-- 6. Students enrolled in IS201
SELECT u.full_name, c.code
FROM enrollments e JOIN users u USING (user_id) JOIN courses c USING (course_id);

-- 7. Constraint test: this INSERT must FAIL (difficulty must be easy/medium/hard)
-- INSERT INTO questions (topic_id, body, option_a, option_b, option_c, option_d, correct_option, difficulty)
-- VALUES (1, 'test', 'a', 'b', 'c', 'd', 'A', 'very hard');
