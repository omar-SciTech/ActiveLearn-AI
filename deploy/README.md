# Hosting on PythonAnywhere (free)

The free plan gives a permanent link `https://<username>.pythonanywhere.com`, 512 MB of disk and a
database that is kept between visits. PyTorch does not fit in 512 MB, so the site runs the **numpy copy**
of the same trained model (`model/predictor_np.py`, identical predictions). Flask and numpy are already
installed on PythonAnywhere.

## First setup
1. Create a free (Beginner) account on https://www.pythonanywhere.com.
2. **Consoles → Bash**, then:
   ```
   git clone https://github.com/omar-SciTech/ActiveLearn-AI.git
   ```
3. **Web → Add a new web app → Next → Manual configuration → Python 3.10** (or newer) → Next.
4. On the Web tab, open the **WSGI configuration file** link, delete everything in it, paste the contents
   of `deploy/pythonanywhere_wsgi.py`, and **Save**.
5. Back on the Web tab, set **Force HTTPS** on, then press the green **Reload** button.
6. Open `https://<username>.pythonanywhere.com`.

## Change the instructor code (do this once)
The demo instructor code `password123` is written in the public README. In a Bash console:
```
cd ~/ActiveLearn-AI/backend
python3 set_password.py "Dr. Instructor" "<new code>"
```
then press **Reload** on the Web tab.

## Update the site after a new push to GitHub
```
cd ~/ActiveLearn-AI && git pull
```
then **Reload** on the Web tab. The live database is in `~/activelearn_data/` and is not touched by `git pull`.

## Keep it online
Free web apps must be renewed once a month: log in and press **"Run until 1 month from today"** on the Web tab
(PythonAnywhere e-mails a reminder a week before the site is disabled).
