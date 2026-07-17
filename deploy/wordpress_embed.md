# Publishing the dashboard on rolandkays.com (WordPress)

The dashboard is a single self-contained file, `docs/index.html`. The plan:
GitHub serves it (free, always-on) and your WordPress page embeds it in an
`<iframe>`. You never upload anything to WordPress by hand after setup — the
weekly job refreshes the page automatically.

## Step 1 — Push the repo to GitHub

On your Mac (the sandbox can't create `.git`):
```bash
cd /Users/rwkays/claude_code/chineseHWC
git init && git add . && git commit -m "Initial commit: chineseHWC monitor"
git branch -M main
git remote add origin https://github.com/Rolandisimo1/chineseHWC-monitor.git
git push -u origin main
```
(Create the empty `chineseHWC-monitor` repo on GitHub first.)

## Step 2 — Add your Anthropic key as a secret

Repo → **Settings → Secrets and variables → Actions** → look under **Repository
secrets** (GitHub shows the *name* only, never the value — you can update or
remove, but not view, an existing secret). Add one via **New repository secret**:
- Name: `ANTHROPIC_API_KEY`. The workflow also accepts `ANTHROPIC_KEY` or
  `CLAUDE_API_KEY` if that's what you already have — it tries all three and fails
  with a clear message if none is set. Value comes from
  https://console.anthropic.com → API Keys.
- Note: Actions secrets are **per-repo** (unless set at the Organization level).
  A key stored in a different repo or only on your account won't be visible here
  — add it to `chineseHWC-monitor` specifically.
- (Optional) `GEOCODE_CONTACT_EMAIL` = your email, for the Nominatim usage policy.

## Step 3 — Turn on GitHub Pages

Repo → **Settings → Pages** → Source: **GitHub Actions**. The weekly workflow
already publishes the `docs/` folder. After the first run, your dashboard is live at:
```
https://rolandisimo1.github.io/chineseHWC-monitor/
```

### Public vs. private repo — the one real decision
- **Free GitHub Pages requires a *public* repo.** The code and the incident CSV
  would be publicly visible. The data is already public (it's news-derived) and
  your key stays a secret (never in the repo), so public is usually fine.
- If you want the repo **private**, Pages needs a paid plan (GitHub Pro/Team),
  OR run the Mac fallback and push only `docs/` to a separate public repo.

## Step 4 — Embed in a WordPress page

Edit the page on rolandkays.com. Add a **Custom HTML** block (not the visual
editor) and paste:
```html
<iframe
  src="https://rolandisimo1.github.io/chineseHWC-monitor/"
  title="China Human–Carnivore Conflict Monitor"
  style="width:100%; height:1500px; border:0; overflow:hidden;"
  loading="lazy">
</iframe>
```
Notes:
- **height:1500px** fits the map + all charts; adjust to taste.
- If your theme boxes content narrowly, use a full-width page template so the
  map has room.
- WordPress.com (hosted) sometimes strips `<iframe>` on lower plans; the
  **"Embed" / iframe block** or a plugin like *iframe* handles it. Self-hosted
  WordPress (.org) allows iframes in a Custom HTML block directly.

## Step 5 — Confirm the weekly refresh

- The workflow runs Mondays 06:00 UTC. Trigger a test run now: repo →
  **Actions → Weekly HWC monitor → Run workflow**.
- When it finds new incidents it commits an updated `docs/index.html`; Pages
  redeploys within a minute; your embedded iframe shows the new data on next load.
- When incidents need review, it opens a **GitHub Issue** (you get an email)
  listing how many are pending in `review_queue.csv`.

## What updates automatically vs. needs you
- **Automatic:** discovery, fetch, extraction, geocoding, dashboard rebuild,
  publish, and appending *confident* new incidents.
- **You, occasionally:** approve the review queue (open the issue → edit
  `review_queue.csv` → `./50_store.py --promote`). Confident incidents don't
  wait for this; only borderline ones do.
