"""
ActiveLearn AI - the database, written in Python (sqlite3).

This one file builds the whole database:
  1) create_tables()  -> the 8 tables, with primary keys, foreign keys, CHECK and UNIQUE constraints
  2) insert_data()    -> 4 users, the IS201 course, its 6 chapters and the question bank (60 questions)
  3) check()          -> prints row counts and tests the relations and constraints

Run it:
    python create_database.py
It creates database/activelearn.db. Open that file in DB Browser for SQLite to browse the tables.

All demo users have the password: password123
(the database only stores its salted hash, never the plain password)
"""
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(HERE, "activelearn.db")


# =====================================================================
# 1. Tables
# =====================================================================
TABLES = {
    "users": """
        CREATE TABLE IF NOT EXISTS users (
          user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
          full_name     TEXT NOT NULL,
          email         TEXT NOT NULL UNIQUE,
          user_code     TEXT UNIQUE,                    -- student code / staff code, used to sign in
          password_hash TEXT NOT NULL,
          role          TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student','instructor')),
          created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",

    "courses": """
        CREATE TABLE IF NOT EXISTS courses (
          course_id     INTEGER PRIMARY KEY AUTOINCREMENT,
          code          TEXT NOT NULL UNIQUE,
          title         TEXT NOT NULL,
          instructor_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL
        )""",

    "enrollments": """
        CREATE TABLE IF NOT EXISTS enrollments (
          user_id     INTEGER NOT NULL REFERENCES users(user_id)     ON DELETE CASCADE,
          course_id   INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
          enrolled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (user_id, course_id)
        )""",

    "topics": """
        CREATE TABLE IF NOT EXISTS topics (
          topic_id    INTEGER PRIMARY KEY AUTOINCREMENT,
          course_id   INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
          chapter_no  INTEGER NOT NULL,
          name        TEXT NOT NULL,
          UNIQUE (course_id, chapter_no)
        )""",

    "questions": """
        CREATE TABLE IF NOT EXISTS questions (
          question_id    INTEGER PRIMARY KEY AUTOINCREMENT,
          topic_id       INTEGER NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
          body           TEXT NOT NULL,
          option_a       TEXT NOT NULL,
          option_b       TEXT NOT NULL,
          option_c       TEXT NOT NULL,
          option_d       TEXT NOT NULL,
          correct_option TEXT NOT NULL CHECK (correct_option IN ('A','B','C','D')),
          difficulty     TEXT NOT NULL DEFAULT 'medium' CHECK (difficulty IN ('easy','medium','hard')),
          explanation    TEXT,
          is_active      INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))  -- 0 = deleted by the instructor (answers are kept)
        )""",

    "quiz_sessions": """
        CREATE TABLE IF NOT EXISTS quiz_sessions (
          session_id  INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id     INTEGER NOT NULL REFERENCES users(user_id)     ON DELETE CASCADE,
          course_id   INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
          mode        TEXT NOT NULL DEFAULT 'adaptive' CHECK (mode IN ('adaptive','random')),
          started_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          ended_at    TEXT
        )""",

    "attempts": """
        CREATE TABLE IF NOT EXISTS attempts (
          attempt_id      INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id      INTEGER NOT NULL REFERENCES quiz_sessions(session_id) ON DELETE CASCADE,
          user_id         INTEGER NOT NULL REFERENCES users(user_id)            ON DELETE CASCADE,
          question_id     INTEGER NOT NULL REFERENCES questions(question_id)    ON DELETE CASCADE,
          selected_option TEXT NOT NULL CHECK (selected_option IN ('A','B','C','D')),
          is_correct      INTEGER NOT NULL CHECK (is_correct IN (0,1)),
          time_taken_sec  REAL,
          created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",

    # predicted probability of answering correctly, per student and chapter (written by the AI model)
    "topic_mastery": """
        CREATE TABLE IF NOT EXISTS topic_mastery (
          user_id    INTEGER NOT NULL REFERENCES users(user_id)   ON DELETE CASCADE,
          topic_id   INTEGER NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
          p_correct  REAL NOT NULL CHECK (p_correct BETWEEN 0 AND 1),
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (user_id, topic_id)
        )""",
}

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_attempts_user     ON attempts(user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_attempts_question ON attempts(question_id)",
    "CREATE INDEX IF NOT EXISTS idx_questions_topic   ON questions(topic_id, difficulty)",
]


def create_tables(con):
    """Creates the 8 tables and their indexes (safe to run again: IF NOT EXISTS)."""
    con.execute("PRAGMA foreign_keys = ON")
    for sql in TABLES.values():
        con.execute(sql)
    for sql in INDEXES:
        con.execute(sql)
    con.commit()


# =====================================================================
# 2. Data
# =====================================================================
DEMO_PASSWORD_HASH = "scrypt:32768:8:1$eaF19sCzfOSWX6H3$eb567d06309f27b9a146f0a6be416d06ae9d7c0d3fbd77d48fe1655eab64d84e73f37950874174a2d69d1ba30e7726e460b0a3a31bc42d25ce595eaf5544499e"   # hash of: password123

USERS = [   # (user_id, full_name, email, user_code, role)
    (1, "Dr. Instructor", "instructor@university.edu", "DR001", "instructor"),
    (2, "Ahmed Mohamed", "ahmed.is201@university.edu", "20260002", "student"),
    (3, "Sara Ali", "sara@university.edu", "20260003", "student"),
    (4, "Omar Khaled", "omar@university.edu", "20260004", "student"),
]

COURSES = [   # (course_id, code, title, instructor_id)
    (1, "IS201", "Introduction to Information Systems", 1),
]

ENROLLMENTS = [   # (user_id, course_id): the 3 students are in IS201
    (2, 1), (3, 1), (4, 1),
]

TOPICS = [   # (topic_id, course_id, chapter_no, name): the 6 chapters of the course book
    (1, 1, 1, "Information Systems Principles"),
    (2, 1, 2, "Data, Databases, and Business Intelligence"),
    (3, 1, 3, "Telecommunications & Networking"),
    (4, 1, 4, "The Systems Development Life Cycle"),
    (5, 1, 5, "Intelligent Information Systems Principles"),
    (6, 1, 6, "Decision Support Systems"),
]

# (question_id, topic_id, body, option_a, option_b, option_c, option_d, correct_option, difficulty, explanation)
QUESTIONS = [
    # ---- Chapter 1: Information Systems Principles ----
    (1, 1, "What is an information system?",
     "A set of interrelated components that collect, process, store and distribute information", "A computer program that only stores files",
     "A network of printers", "A single database table",
     "A", "easy", "An IS combines components that work together to turn data into information that supports decisions."),
    (2, 1, "Data that has been processed so that it is meaningful and useful is called:",
     "Noise", "Raw data",
     "Hardware", "Information",
     "D", "easy", "Raw facts become information after they are organized and processed for a purpose."),
    (3, 1, "Which of these is a component of an information system?",
     "Office furniture", "People",
     "Weather", "Electricity prices",
     "B", "easy", "The components of an IS are hardware, software, data, networks, procedures and people."),
    (4, 1, "A point-of-sale checkout system in a supermarket is an example of a:",
     "Decision Support System (DSS)", "Expert System",
     "Executive Information System (EIS)", "Transaction Processing System (TPS)",
     "D", "easy", "A TPS records the daily routine transactions of the business, such as sales."),
    (5, 1, "Transaction processing systems belong to which category of information systems?",
     "Entertainment systems", "Operations support systems",
     "Management support systems", "Strategic games",
     "B", "medium", "Operations support systems process data from daily operations; TPS is the main example."),
    (6, 1, "Which system gives senior managers summarized, critical information for strategic decisions?",
     "Process Control System", "Payroll system",
     "Transaction Processing System (TPS)", "Executive Information System (EIS)",
     "D", "medium", "EIS is a management support system designed for top executives."),
    (7, 1, "In system concepts, the stage that transforms inputs into outputs is:",
     "Feedback", "Storage",
     "Processing", "Control",
     "C", "medium", "A system has input, processing and output; processing converts input into output."),
    (8, 1, "Data about the performance of a system that is used to adjust it is called:",
     "Feedback", "Input",
     "Hardware", "Output",
     "A", "medium", "Feedback reports on performance, and control uses it to make adjustments."),
    (9, 1, "Which list contains the main information system activities?",
     "Input, processing, output, storage and control", "Design, color and layout",
     "Typing, printing and scanning", "Buying, selling and hiring",
     "A", "hard", "An IS performs input of data, processing into information, output, storage of data and control of performance."),
    (10, 1, "Which of the following is a trend shaping modern information systems?",
     "Storing all data on floppy disks", "Replacing computers with paper files",
     "Cloud computing and artificial intelligence", "Removing networks from organizations",
     "C", "hard", "Cloud computing, AI, mobile and big data are major trends changing how IS are built and used."),
    # ---- Chapter 2: Data, Databases, and Business Intelligence ----
    (11, 2, "A primary key must be:",
     "Repeated in every row", "Always a text value",
     "Optional", "Unique and not null",
     "D", "easy", "The primary key identifies each record, so it cannot repeat and cannot be empty."),
    (12, 2, "A foreign key is a field that:",
     "Deletes rows automatically", "Is always unique in its own table",
     "Encrypts the data", "References the primary key of another table",
     "D", "easy", "Foreign keys create relationships between tables by pointing to a primary key."),
    (13, 2, "A collection of related fields that describes one entity (e.g. one student) is a:",
     "Database", "Character",
     "Record", "Byte",
     "C", "easy", "Data hierarchy: character, field, record, file (table), database."),
    (14, 2, "In a relational database, data is organized into:",
     "Paper folders", "Tables of rows and columns",
     "Trees only", "Images",
     "B", "easy", "The relational model stores data in two-dimensional tables (relations)."),
    (15, 2, "Which relationship type needs a junction (linking) table?",
     "No relationship", "Many-to-many",
     "One-to-many", "One-to-one",
     "B", "medium", "A many-to-many relationship is split into two one-to-many relationships through a junction table."),
    (16, 2, "In an ERD, a rectangle usually represents:",
     "A relationship", "A user interface",
     "A foreign key value", "An entity",
     "D", "medium", "Entities are drawn as rectangles; relationships connect them."),
    (17, 2, "The process of organizing tables to reduce redundancy is called:",
     "Compilation", "Encryption",
     "Normalization", "Formatting",
     "C", "medium", "Normalization divides data into well-structured tables to avoid duplicated data and anomalies."),
    (18, 2, "Which database structure organizes records in a parent-child tree?",
     "Relational", "Hierarchical",
     "Spreadsheet", "Flat text",
     "B", "medium", "The hierarchical structure is a tree where each child has only one parent."),
    (19, 2, "Which is one of the classical characteristics of a data warehouse?",
     "Used only for single transactions", "Stored on one laptop",
     "Non-volatile", "Deleted daily",
     "C", "hard", "A data warehouse is subject-oriented, integrated, time-variant and non-volatile."),
    (20, 2, "OLAP systems are mainly used for:",
     "Controlling network cables", "Analyzing large amounts of historical data",
     "Printing invoices", "Recording each sale as it happens",
     "B", "hard", "OLTP handles daily transactions, while OLAP supports analysis and business intelligence."),
    # ---- Chapter 3: Telecommunications & Networking ----
    (21, 3, "A network that connects computers in one building or campus is a:",
     "WAN", "LAN",
     "Satellite only", "The Internet",
     "B", "easy", "A Local Area Network covers a small area such as an office, building or campus."),
    (22, 3, "A network that covers a large geographic area such as a country is a:",
     "WAN", "PAN",
     "Bluetooth", "LAN",
     "A", "easy", "A Wide Area Network spans large distances, like cities or countries."),
    (23, 3, "Which is a benefit of computer networks?",
     "Making data harder to access", "Increasing paper usage",
     "Sharing resources such as printers and files", "Removing the need for software",
     "C", "easy", "Networks let users share hardware, software and data and communicate easily."),
    (24, 3, "In which topology are all devices connected to a central device?",
     "Line", "Ring",
     "Bus", "Star",
     "D", "easy", "In a star topology every node connects to a central switch or hub."),
    (25, 3, "In which topology does each device connect to exactly two neighbors forming a closed loop?",
     "Ring", "Star",
     "Tree", "Bus",
     "A", "medium", "A ring topology passes data around a circle from one node to the next."),
    (26, 3, "In a client/server network, the server:",
     "Provides services and resources to clients", "Is always a mobile phone",
     "Cannot store data", "Only requests data from clients",
     "A", "medium", "Clients request services and the server responds by providing them."),
    (27, 3, "The main protocol suite used on the Internet is:",
     "SQL", "PDF",
     "TCP/IP", "HTML",
     "C", "medium", "TCP/IP defines how data is addressed, sent and received across the Internet."),
    (28, 3, "Which device forwards data between different networks?",
     "Monitor", "Keyboard",
     "Scanner", "Router",
     "D", "medium", "A router connects networks and chooses the path for data packets."),
    (29, 3, "An IP address is used to:",
     "Identify a device on a network", "Encrypt a hard disk",
     "Measure screen size", "Store passwords",
     "A", "hard", "Each device on an IP network has an address so data can be delivered to it."),
    (30, 3, "Sending data from one device to all devices on the network is called:",
     "Unicast", "Multicast",
     "Broadcast", "Encryption",
     "C", "hard", "Unicast is one-to-one, multicast is one-to-a-group and broadcast is one-to-all."),
    # ---- Chapter 4: The Systems Development Life Cycle ----
    (31, 4, "SDLC stands for:",
     "Systems Development Life Cycle", "Secure Data Lifecycle",
     "Software Data Link Control", "System Design Logic Code",
     "A", "easy", "The SDLC is the set of phases used to build an information system."),
    (32, 4, "What is usually the first step when developing a business/IT solution?",
     "Training users", "Problem definition and business analysis",
     "Maintenance", "Deployment",
     "B", "easy", "You must understand the problem before designing or building a solution."),
    (33, 4, "Checking whether a solution is technically, economically and operationally possible is the:",
     "Feasibility study", "Deployment phase",
     "Maintenance phase", "Testing phase",
     "A", "easy", "A feasibility study evaluates technical, economic (cost/benefit) and operational feasibility."),
    (34, 4, "Fixing errors and improving the system after it goes live happens in:",
     "Post-implementation and maintenance", "Feasibility study",
     "Problem definition", "Requirements analysis",
     "A", "easy", "Maintenance keeps the system working and updated after deployment."),
    (35, 4, "Determining what the users need the new system to do is:",
     "Requirements analysis", "Training",
     "Deployment", "Coding",
     "A", "medium", "Requirements analysis gathers and documents the functions the system must provide."),
    (36, 4, "Specifying the database, interfaces and architecture of the solution happens in:",
     "Feasibility study", "System design",
     "Maintenance", "Problem definition",
     "B", "medium", "System design describes how the system will meet the requirements."),
    (37, 4, "The purpose of testing and quality assurance is to:",
     "Hire the developers", "Choose the project name",
     "Make sure the system works correctly and meets requirements", "Remove all documentation",
     "C", "medium", "Testing finds defects before the system is delivered to users."),
    (38, 4, "Preparing users to accept and use the new system is called:",
     "Feasibility study", "Routing",
     "Normalization", "Training and change management",
     "D", "medium", "Users need training and support so the organization adopts the new system."),
    (39, 4, "Running the old and new systems together for a period before switching is:",
     "Direct cutover", "Feasibility study",
     "Parallel conversion", "Normalization",
     "C", "hard", "Parallel conversion is safe because the old system remains as a backup, but it costs more."),
    (40, 4, "Why are several alternatives developed and evaluated before selecting a solution?",
     "To make the project longer", "To choose the option that best fits cost, benefits and requirements",
     "Because one alternative is always illegal", "To avoid talking to users",
     "B", "hard", "Comparing alternatives helps select the best solution for the business."),
    # ---- Chapter 5: Intelligent Information Systems Principles ----
    (41, 5, "Artificial intelligence aims to make computers:",
     "Perform tasks that normally require human intelligence", "Print faster",
     "Use less electricity only", "Replace all networks",
     "A", "easy", "AI covers learning, reasoning, problem solving and understanding language."),
    (42, 5, "Machine learning systems improve by:",
     "Adding more monitors", "Being repainted",
     "Learning patterns from data", "Deleting their data",
     "C", "easy", "Machine learning builds models from examples instead of hand-written rules only."),
    (43, 5, "A chatbot that understands written questions mainly uses:",
     "Spreadsheets", "Natural Language Processing (NLP)",
     "Network topology", "Normalization",
     "B", "easy", "NLP lets computers understand and generate human language."),
    (44, 5, "A system that captures the knowledge of human experts to give advice is a(n):",
     "Payroll system", "Router",
     "Operating system", "Expert system",
     "D", "easy", "Expert systems use a knowledge base of expert rules to solve problems in a specific field."),
    (45, 5, "In an expert system, the part that applies rules to facts to reach conclusions is the:",
     "Database index", "Inference engine",
     "Printer driver", "Knowledge base",
     "B", "medium", "The knowledge base stores rules; the inference engine reasons with them."),
    (46, 5, "Neural networks are inspired by:",
     "Spreadsheet formulas", "Road networks",
     "The structure of the human brain", "Electric grids",
     "C", "medium", "Neural networks are layers of connected artificial neurons that learn from data."),
    (47, 5, "Fuzzy logic is useful because it can handle:",
     "Network cables", "Uncertain or approximate values (degrees of truth)",
     "Only exact 0 or 1 values", "Printing reports",
     "B", "medium", "Fuzzy logic allows values between true and false, like 'warm' or 'fairly high'."),
    (48, 5, "Recommending products to customers based on their previous purchases is an application of:",
     "Data entry", "Network cabling",
     "Manual filing", "Machine learning",
     "D", "medium", "Recommendation systems learn customer preferences from historical data."),
    (49, 5, "Training a model on examples that already have correct answers (labels) is:",
     "Supervised learning", "Normalization",
     "Unsupervised learning", "Broadcasting",
     "A", "hard", "Supervised learning uses labeled data; unsupervised learning finds patterns without labels."),
    (50, 5, "Which is a key challenge of intelligent information systems?",
     "They never need data", "Bias, privacy and explainability of decisions",
     "They cannot run on computers", "They only work offline",
     "B", "hard", "AI systems must be fair, protect personal data and be able to explain their outputs."),
    # ---- Chapter 6: Decision Support Systems ----
    (51, 6, "A Decision Support System (DSS) is designed to:",
     "Record every sale", "Replace all employees",
     "Connect network cables", "Help managers make decisions",
     "D", "easy", "A DSS supports (not replaces) decision makers with data and models."),
    (52, 6, "DSS are best suited for which type of decisions?",
     "No decisions at all", "Semi-structured and unstructured decisions",
     "Only fully routine decisions", "Only hardware repair",
     "B", "easy", "Routine structured decisions can be automated; DSS help with semi-structured problems."),
    (53, 6, "Asking 'what happens to profit if we raise prices by 10%?' is called:",
     "Routing", "Backup",
     "What-if analysis", "Data entry",
     "C", "easy", "What-if analysis changes input values to see their effect on the results."),
    (54, 6, "Which is a main component of a DSS?",
     "Router", "Keyboard",
     "Printer", "Model management subsystem",
     "D", "easy", "A DSS has data management, model management and a user interface (dialog) component."),
    (55, 6, "The DSS component that lets the user interact with the system is the:",
     "User interface (dialog) subsystem", "Model base",
     "Database", "Inference engine",
     "A", "medium", "The user interface allows managers to enter questions and see results."),
    (56, 6, "A DSS that mainly uses statistical, financial or optimization models is:",
     "Model-driven DSS", "Hardware-driven DSS",
     "Communication-driven DSS", "Document-driven DSS",
     "A", "medium", "Model-driven DSS emphasize access to and manipulation of models."),
    (57, 6, "A DSS that supports a group of people working together on a decision is a:",
     "Single-user spreadsheet only", "Payroll system",
     "TPS", "Group DSS (GDSS)",
     "D", "medium", "GDSS support communication and collaboration among decision makers."),
    (58, 6, "A DSS focused on querying and analyzing large amounts of company data is:",
     "Knowledge-driven DSS", "Model-driven DSS",
     "Data-driven DSS", "Communication-driven DSS",
     "C", "medium", "Data-driven DSS give access to large databases or data warehouses for analysis."),
    (59, 6, "How do modern DSS benefit from AI integration?",
     "They become slower on purpose", "They no longer need users",
     "They stop using data", "They can learn from data and give predictions and recommendations",
     "D", "hard", "AI adds prediction, pattern recognition and recommendations to classic DSS."),
    (60, 6, "Which statement best describes the role of a DSS?",
     "It is only used to store files", "It makes every decision alone",
     "It supports the manager's judgment rather than replacing it", "It is a type of network cable",
     "C", "hard", "The final decision stays with the human; the DSS provides analysis to support it."),
]


def insert_data(con):
    """Inserts the users, the course, its chapters and the question bank (parameterized INSERTs)."""
    con.execute("PRAGMA foreign_keys = ON")
    con.executemany(
        "INSERT INTO users (user_id, full_name, email, user_code, password_hash, role) VALUES (?, ?, ?, ?, ?, ?)",
        [(uid, name, email, code, DEMO_PASSWORD_HASH, role) for uid, name, email, code, role in USERS])
    con.executemany("INSERT INTO courses (course_id, code, title, instructor_id) VALUES (?, ?, ?, ?)", COURSES)
    con.executemany("INSERT INTO enrollments (user_id, course_id) VALUES (?, ?)", ENROLLMENTS)
    con.executemany("INSERT INTO topics (topic_id, course_id, chapter_no, name) VALUES (?, ?, ?, ?)", TOPICS)
    con.executemany(
        "INSERT INTO questions (question_id, topic_id, body, option_a, option_b, option_c, option_d,"
        " correct_option, difficulty, explanation) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", QUESTIONS)
    con.commit()


# =====================================================================
# 3. Checks
# =====================================================================
def check(con):
    """Prints row counts and tests that the relations and constraints work."""
    print("Rows per table:")
    for table in TABLES:
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:<14}{n}")

    bad = con.execute("PRAGMA foreign_key_check").fetchall()
    print("Foreign keys:", "all valid" if not bad else f"{len(bad)} broken rows")

    print("Questions per chapter (easy / medium / hard):")
    for ch, name, e, m, h in con.execute("""
            SELECT t.chapter_no, t.name,
                   SUM(q.difficulty = 'easy'), SUM(q.difficulty = 'medium'), SUM(q.difficulty = 'hard')
            FROM topics t JOIN questions q USING (topic_id)
            GROUP BY t.topic_id ORDER BY t.chapter_no"""):
        print(f"  Ch {ch}: {e} / {m} / {h}   {name}")

    spread = dict(con.execute("SELECT correct_option, COUNT(*) FROM questions GROUP BY correct_option"))
    print("Correct answers per option:", spread)

    missing = con.execute("SELECT COUNT(*) FROM questions WHERE explanation IS NULL OR explanation = ''").fetchone()[0]
    print("Questions without an explanation:", missing)

    # a CHECK constraint must reject an invalid difficulty
    try:
        con.execute("INSERT INTO questions (topic_id, body, option_a, option_b, option_c, option_d, correct_option,"
                    " difficulty) VALUES (1, 'test', 'a', 'b', 'c', 'd', 'A', 'very hard')")
        print("CHECK constraint: NOT working")
    except sqlite3.IntegrityError:
        print("CHECK constraint: rejected difficulty 'very hard' as expected")
    con.rollback()


def build(path=DEFAULT_DB, reset=True):
    """Builds a fresh database file and returns an open connection to it."""
    if reset and os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    create_tables(con)
    insert_data(con)
    return con


if __name__ == "__main__":
    con = build()
    print(f"Database created: {DEFAULT_DB}\n")
    check(con)
    con.close()
