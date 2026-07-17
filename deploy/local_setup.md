# Running the monitor locally (Mac now, Windows PC later)

The pipeline is designed to run on a normal computer with a home internet
connection. This is the **recommended way to run it** — home IPs get real data
from Chinese news sites, while cloud/datacenter IPs (GitHub Actions) are heavily
throttled and return little. Every stage is a standalone script; `run_weekly.py`
chains them and works identically on macOS, Windows, and Linux.

GitHub is still useful for **hosting the dashboard** (GitHub Pages) even if the
crawl runs locally — see "Publishing" below. You do not have to use it.

---

## One-time setup (same on Mac and Windows)

1. **Install Python 3.11+** (3.13 recommended).
   - Mac: `brew install python@3.13` or from python.org.
   - Windows: from python.org — **check "Add Python to PATH"** during install.
2. **Get the code.**
   - If cloning from GitHub: `git clone https://github.com/Rolandisimo1/chineseHWC-monitor.git`
   - Or copy the `chineseHWC` folder directly.
3. **Install dependencies** (from inside the project folder):
   ```
   python -m venv .venv
   # Mac/Linux:
   source .venv/bin/activate
   # Windows (PowerShell):
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
4. **Add your Anthropic API key.** Copy `.env.example` to `.env` and fill in:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   HWC_EXTRACT_MODEL=claude-3-5-haiku-latest
   GEOCODE_CONTACT_EMAIL=you@example.com
   ```
   (The key comes from https://console.anthropic.com → API Keys. `.env` is
   git-ignored, so it never leaves the machine.)

---

## Running it

```
# fast, reliable — RSS feeds only:
python run_weekly.py

# richer — adds bounded on-site search (recommended from a home IP):
python run_weekly.py --with-search
```

This updates `data/master/incidents.csv` and rebuilds `docs/index.html`.
Open `docs/index.html` in any browser to see the dashboard. Incidents needing
review land in `data/master/review_queue.csv` (nothing is dropped).

### Confirming a review-queue row
Open `data/master/review_queue.csv`, delete rows that aren't real incidents, put
`1` in the `keep` column for the good ones, save, then:
```
python 50_store.py --promote
```

---

## Scheduling a weekly run (optional)

### Mac (launchd)
See the plist in `deploy/launchd_setup.md`. Point it at `run_weekly.py`:
```xml
<string>/path/to/.venv/bin/python</string>
<string>/path/to/chineseHWC/run_weekly.py</string>
```

### Windows (Task Scheduler)
1. Open **Task Scheduler** → **Create Basic Task**.
2. Trigger: **Weekly**, pick a day/time.
3. Action: **Start a program**.
   - Program/script: the venv Python, e.g.
     `C:\Users\<you>\chineseHWC\.venv\Scripts\python.exe`
   - Add arguments: `run_weekly.py`
   - Start in: `C:\Users\<you>\chineseHWC`
4. Finish. Test with **Run** (right-click the task).

---

## Publishing the dashboard

The dashboard is one self-contained file (`docs/index.html`). Two ways to show
it on rolandkays.com:

- **Via GitHub Pages (recommended, automatic URL).** After a local run:
  ```
  python run_weekly.py --with-search --publish
  ```
  `--publish` commits the updated data + dashboard and pushes to GitHub; Pages
  redeploys, and your WordPress iframe shows the new version. (Requires GitHub
  Pages enabled once — see `deploy/wordpress_embed.md`.)
- **Without GitHub.** Upload `docs/index.html` to any web host, or into WordPress
  via a plugin, and embed/link it. More manual, but no GitHub needed.

---

## Handing off to a student (Windows PC)

Everything they need is in this repo. Give them:
1. This file (`deploy/local_setup.md`) — the full setup + run instructions.
2. The Anthropic API key (or have them create their own).
3. `README.md` — pipeline overview; `CLAUDE.md` — method-fidelity rules to not
   drift from the manuscript.

Nothing is Mac-specific except the optional launchd scheduler; `run_weekly.py`
and every stage script are pure Python and run on Windows unchanged. The SQLite
cache makes runs resumable, so an interrupted run on any machine is safe to
restart.
