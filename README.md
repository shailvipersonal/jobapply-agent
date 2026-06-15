# 🤖 My Job Apply Agent

A **personal, local web app** for job hunting — like a private jobright.ai that
runs entirely on your own computer. Set up your details once, then from a clean
browser dashboard you can:

- 📄 **Upload your resume**
- 🎯 **Score it against any job** (paste a link or the description) and see your
  callback chance — High / Medium / Low
- ✨ **Auto-fix your resume with AI**, tailored to that job, and download it
- 🚀 **Apply by pasting a job link** — the agent opens the page, signs into (or
  creates) your account, fills the form, and submits
- 🗂 **Track every application** in one place, exportable to CSV

No terminal needed for day-to-day use — just a friendly web page.

---

## 🚀 Getting started (easy mode)

### On Windows
1. Install **Python 3.10+** from [python.org](https://www.python.org/downloads/)
   — during install, tick **"Add Python to PATH"**.
2. **Double-click `start.bat`.**
   The first run sets everything up (a few minutes) and then opens the app at
   <http://127.0.0.1:8000>. Future runs start in seconds.

### On macOS / Linux
1. Install Python 3.10+.
2. In a terminal: `bash start.sh`

That's it. The dashboard opens automatically in your browser.

> If `start.bat` ever closes too fast to read an error, open it once from a
> terminal (`./start.bat`) to see the message.

---

## 🧭 How to use the dashboard

The app has four tabs, meant to be used left to right:

**1 · Setup** — Enter your name, contact, links, work authorization, education,
the email/password the agent should use for job-site accounts, and (optionally)
an **OpenAI API key**. Click *Save setup*. You only do this once.

**2 · Resume & Match** — Upload your resume, then paste a job link (or the job
description) and click *Analyze my chances*. You'll get a match score, your
callback chance, matched vs missing keywords, and concrete improvements. Click
*Fix my resume with AI* to generate a tailored version you can download.

**3 · Apply** — Paste a job link and click *Apply now*. A browser window opens so
you can watch. By default the agent fills the form and lets you **review** before
you click *Submit now*; tick *Submit automatically* to skip the review.

**4 · History** — See everything you've applied to and export it to CSV.

---

## 🔑 About the OpenAI key (optional but recommended)

Without a key, the app still works: resume scoring uses keyword matching and form
filling uses smart heuristics. **With** a key (paste it in Setup), you unlock:

- Deeper, recruiter-style resume analysis
- AI resume rewriting tailored to each job
- More robust form filling on unusual application forms

Get a key at <https://platform.openai.com/api-keys>. It's stored only in your
local `.env` file and used solely for your own analysis calls.

---

## 🔐 Privacy & security

Everything runs on your machine. These are all **gitignored** so they never get
pushed to GitHub: `config/profile.yaml`, `config/credentials.yaml`, `.env`,
`data/` (your resume, database, generated files), and `browser_profile/` (saved
logins). The only outbound network calls are the optional OpenAI requests; your
job-site password is never sent anywhere.

---

## 🧰 Power-user / CLI mode (optional)

The same engine also has a command-line interface if you prefer it:

```bash
python -m jobagent apply <job-url>     # fill (and optionally submit) one job
python -m jobagent batch jobs.txt      # apply to many at once
python -m jobagent list                # show history
python -m jobagent export out.csv      # export history
```

---

## 📤 Publishing to your GitHub

From this project folder:

```bash
git init
git add .
git status          # confirm NO personal files are listed (see Privacy above)
git commit -m "Personal job apply agent (local web app)"
git branch -M main
git remote add origin https://github.com/<your-username>/jobapply-agent.git
git push -u origin main
```

Or with the GitHub CLI: `gh repo create jobapply-agent --public --source=. --push`

When you later set it up on another computer, just clone the repo and run
`start.bat` / `start.sh` again.

---

## 🗂 Project layout

```
jobapply-agent/
├── start.bat / start.sh    # one-click setup + launch
├── run.py                  # starts the local web server
├── webui/index.html        # the dashboard UI
├── jobagent/
│   ├── web.py              # FastAPI app + API
│   ├── browser_worker.py   # keeps one browser window alive across actions
│   ├── apply.py            # fills & submits application forms
│   ├── form_filler.py      # detects + fills fields (heuristics + AI)
│   ├── resume.py           # parse, score, and rewrite resumes
│   ├── scrape.py           # reads job-description text from a link
│   ├── settings_store.py   # Setup form  <->  config files
│   ├── config.py           # loads profile / credentials / settings
│   ├── records.py          # application history (SQLite + CSV)
│   ├── llm.py              # optional OpenAI helpers
│   └── cli.py              # optional command-line interface
├── config/                 # your details (gitignored once created)
├── requirements.txt
└── README.md
```

---

## 🧪 Try it offline first (recommended)

A demo job page (`sample_job.html`) is included so you can test the whole flow
without touching a real job site:

1. Start the app (`start.bat` / `start.sh`) and open the dashboard.
2. Find the demo file's path. It's `sample_job.html` in this project folder. As a
   URL it looks like:
   - Windows: `file:///C:/Users/you/jobapply-agent/sample_job.html`
   - macOS/Linux: `file:///Users/you/jobapply-agent/sample_job.html`
   (Tip: drag the file into a browser tab and copy the address bar.)
3. **Resume & Match tab:** upload a resume, paste that `file:///…` URL as the job
   link, and click *Analyze* — you'll get a score against the demo job.
4. **Apply tab:** paste the same `file:///…` URL and click *Apply now*. Watch the
   browser fill the form, then click *Submit now*. You'll see a green
   "submitted" confirmation (nothing leaves your computer).

Once that works end to end, switch to real job links.

---

## 🆘 Troubleshooting

**"Python was not found" when running `start.bat`**
Install Python 3.10+ from [python.org](https://www.python.org/downloads/) and tick
**"Add Python to PATH"** during setup, then run `start.bat` again.

**`start.bat` window flashes and closes instantly**
Open a terminal in the project folder and run `start.bat` from there so the error
message stays visible.

**Install fails with a connection / SSL error**
You're likely on a restricted network (e.g. a work VPN/firewall) that blocks
PyPI. Try again on a normal home connection.

**"Port 8000 is already in use"**
Another program (or a previous run) is using the port. Close the old window, or
edit `PORT = 8000` near the top of `run.py` to e.g. `8001`.

**"Playwright is not installed" / browser doesn't open**
Run these once in the project folder:
```bash
.venv\Scripts\python -m pip install -r requirements.txt   # Windows
.venv\Scripts\python -m playwright install chromium
```
(macOS/Linux: use `.venv/bin/python` instead.)

**Resume scoring says "keyword-based"**
That means no OpenAI key is set. Add one in the **Setup** tab to unlock AI
analysis and resume rewriting. Keyword scoring still works without it.

**The form only filled some fields**
Complex/multi-step portals don't always expose everything at once. Use the
default **review** mode and finish the remaining fields in the opened browser
before clicking *Submit now*.

**A site shows a CAPTCHA or asks for a code**
Solve it yourself in the visible browser window once — your session is saved to
`browser_profile/` and reused next time.

**It says "already applied"**
You've applied to that exact URL before (tracked in History). That's the
duplicate guard; it's expected.

---

## ⚠️ Honest expectations

- **CAPTCHAs / 2-factor / email verification** can't be automated — when a site
  needs them, do that step once in the visible browser; the login is then saved
  and reused.
- **Standard application forms** (Greenhouse, Lever, simple career pages) work
  well. **Complex multi-step portals** (some Workday flows) may only get
  partially filled — review mode lets you finish the rest before submitting.
- Keep the browser window visible at first so you can watch and step in.
- Please respect each job site's Terms of Service — this is a personal helper for
  **your own** applications.

MIT licensed — see `LICENSE`.
