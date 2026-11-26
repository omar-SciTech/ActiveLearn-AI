"""WSGI entry point for PythonAnywhere.

Copy this whole file into the WSGI configuration file of your PythonAnywhere web app
(Web tab -> "WSGI configuration file"), replacing everything in it. Nothing to edit: it finds your
username automatically.

What it does:
  * the live database lives OUTSIDE the git folder (~/activelearn_data/activelearn.db), so
    `git pull` to update the code never overwrites the answers of real users;
  * the first time, it starts from the demo database that comes with the repository;
  * it creates a random SECRET_KEY once and keeps it in ~/activelearn_data/secret_key (never in git);
  * it creates the instructor activation key in ~/activelearn_data/instructor_key: without it nobody can
    sign up as an instructor on the public site.
"""
import os, secrets, shutil, sys

HOME = os.path.expanduser("~")
REPO = os.path.join(HOME, "ActiveLearn-AI")
DATA = os.path.join(HOME, "activelearn_data")
os.makedirs(DATA, exist_ok=True)

db = os.path.join(DATA, "activelearn.db")
if not os.path.exists(db):
    shutil.copy(os.path.join(REPO, "backend", "activelearn.db"), db)
os.environ["DB_PATH"] = db

key_file = os.path.join(DATA, "secret_key")
if not os.path.exists(key_file):
    with open(key_file, "w") as f:
        f.write(secrets.token_hex(32))
os.environ["SECRET_KEY"] = open(key_file).read().strip()

# instructors need this key to create an account on the public site (give it to them privately)
ikey_file = os.path.join(DATA, "instructor_key")
if not os.path.exists(ikey_file):
    with open(ikey_file, "w") as f:
        f.write(secrets.token_urlsafe(9))
os.environ["INSTRUCTOR_SIGNUP_KEY"] = open(ikey_file).read().strip()

sys.path.insert(0, os.path.join(REPO, "backend"))
from app import app as application  # noqa: E402
