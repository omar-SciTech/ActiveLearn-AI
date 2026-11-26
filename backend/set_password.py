"""Change a user's login code (stored as a salted hash, like every password in the app).

  python set_password.py DR001 "new-password"               # by student / staff code
  python set_password.py ahmed.is201@university.edu "new"   # or by e-mail

Uses the hosted database (~/activelearn_data/activelearn.db) when it exists, otherwise backend/activelearn.db,
or DB_PATH if that environment variable is set.
"""
import os, sqlite3, sys
from werkzeug.security import generate_password_hash

HERE = os.path.dirname(os.path.abspath(__file__))
hosted = os.path.join(os.path.expanduser("~"), "activelearn_data", "activelearn.db")
DB = os.environ.get("DB_PATH") or (hosted if os.path.exists(hosted) else os.path.join(HERE, "activelearn.db"))

if len(sys.argv) != 3 or len(sys.argv[2]) < 6:
    sys.exit('usage: python set_password.py "<code or e-mail>" "<new password, 6+ characters>"')

who, code = sys.argv[1], sys.argv[2]
with sqlite3.connect(DB) as c:
    n = c.execute("UPDATE users SET password_hash=? WHERE lower(user_code)=lower(?) OR lower(email)=lower(?)",
                  (generate_password_hash(code), who, who)).rowcount
print(f"{n} user(s) updated in {DB}" if n else f"no user named {who!r} in {DB}")
