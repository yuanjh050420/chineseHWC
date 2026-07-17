# chineseHWC-monitor

Automated weekly monitoring of **human–large-carnivore conflict** news in China
and Taiwan, extending the 20-year (2005–2024, 520-incident) dataset from
*"Mapping Two Decades of Human-Large Carnivore Conflict in China."*

The pipeline discovers new conflict news from a **curated list of Chinese/Taiwan
news outlets** (RSS feeds + on-site search), extracts the same structured fields
the manuscript coded, geocodes them, appends to a master store, and rebuilds a
self-contained HTML dashboard. It runs weekly on GitHub Actions (or locally on a
Mac via launchd) and publishes the dashboard to GitHub Pages for embedding in
rolandkays.com.

## Pipeline stages (standalone, numbered, resumable CLIs)

Run from the repo root. Each script has `--help`.

| Stage | Script | What it does |
|-------|--------|--------------|
| Discover | `10_discover.py` | Poll curated outlets' RSS + search for species×keyword terms → candidate URLs |
| Fetch    | `20_fetch.py`    | Polite, resumable fetch + article-text extraction (trafilatura), bot-block resilient |
| Extract  | `30_extract.py`  | LLM reads each article → coded incident row + include/exclude decision |
| Geocode  | `40_geocode.py`  | Chinese place text → lon/lat + uncertainty radius (Nominatim gazetteer by default; Amap opt-in) |
| Store    | `50_store.py`    | Join geocode, year/month fallback from pubdate, dedup, append confident rows to master, queue borderline rows for review |
| Dashboard| `build_dashboard.py` | Rebuild the self-contained HTML dashboard from the master store |

`run_weekly.sh` chains all stages for the scheduled job.

### Human review (recall-favoring policy)

Confident, in-scope incidents are auto-published to the master store and
dashboard. Borderline ones (low confidence, unresolved location, or missing
date) are written to `data/master/review_queue.csv` instead — nothing is dropped
silently. To confirm: open that file, delete bad rows, set `keep=1` on good
ones, then `./50_store.py --promote`. The weekly GitHub Action opens an issue
when rows are pending.

## Data

- `data/seed/All_species.csv` — the published 520-incident ground truth.
- `data/master/incidents.csv` — the live master store (seed + newly found; committed back weekly).
- `data/master/incidents.parquet` — typed mirror (derived; git-ignored).

## Config (edit these, not the code)

- `config/schema.yaml` — species list (Chinese search names), 7 conflict types, victim vocab, incident schema.
- `config/search_terms.yaml` — the 10 Chinese conflict keywords + query assembly.
- `config/sources.yaml` — curated outlets with candidate RSS/search endpoints + politeness policy.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # fill in ANTHROPIC_API_KEY (+ optional AMAP_KEY)
python 10_discover.py --seed-liveness   # probe which feeds are actually live
```

## Deployment

- **Weekly automation:** `.github/workflows/weekly.yml` (GitHub Actions cron,
  commits data back, publishes Pages, opens a review issue).
- **Mac fallback:** `deploy/launchd_setup.md` (run on a home IP if the cloud
  gets bot-blocked).
- **WordPress embed:** `deploy/wordpress_embed.md` (push to GitHub, enable Pages,
  iframe into rolandkays.com; public-vs-private repo notes).

## The bot-blocking reality (read `docs/`)

Chinese portals block automated clients and most dropped public RSS years ago.
This tool is **polite by construction** (per-host rate limits, robots.txt,
retry/backoff, no CAPTCHA defeat) and **honest about recall**: the discover
stage logs which feeds are live so gaps are visible. See `docs/crawling_notes.md`.

## Extractor accuracy

The LLM extractor is benchmarked against the 520-incident ground truth; see
`benchmark/accuracy_report.md` for per-field accuracy.
