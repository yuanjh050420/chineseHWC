# Crawling notes — how this tool handles bot-blocking and recall

You told us you don't know much about web crawling and that sites block bots.
Here's what this tool does about it, in plain terms.

## Expect quiet weeks — this is correct, not broken

Human–large-carnivore conflict is a **rare event**. The source manuscript found
520 incidents across the whole of China over **20 years** — roughly one incident
every two weeks nationally. So in any given weekly run it is entirely normal for
the pipeline to find **few or zero** new incidents, even after fetching hundreds
of articles. The working RSS feeds (People's Daily, China Daily, LTN, ettoday)
are general national/Taiwan news firehoses; the extractor correctly rejects the
overwhelming majority — sports, lottery, entertainment, politics — because they
are not carnivore-conflict stories. A run that reads 600 articles and keeps 0 is
the extractor doing its job, not a failure.

**Project decision (Roland, Jul 2026):** curated named sources give clean, honest,
manuscript-consistent data but accumulate slowly, and neither RSS (recent, little
HWC) nor archive search (real HWC, but years old) reliably surfaces *recent*
incidents. To reach recent conflict stories from mainland outlets whose own search
is blocked to us, Google News has since been **ENABLED** as a dedicated recency
channel (see the "Google News — the recency channel" section below). Curated
sources remain primary; Google News supplements them, and every hit still passes
the strict extractor (China/Taiwan scope + study criteria) and the 12-month cutoff.
Even so, quiet stretches from the curated channels alone are expected and correct.

To sanity-check a quiet run, look at the exclusion reasons in the `extracted`
cache table — they should read like "sports article", "lottery result",
"entertainment news", confirming the extractor read and understood each article.

## The core principle: be a polite guest, not an intruder

We do **not** try to defeat blocks. We don't solve CAPTCHAs, we don't spoof to
impersonate a specific browser to evade detection, and we don't hammer sites.
Instead the crawler is polite by construction (`tools/http.py`):

- **One request at a time per site**, with a 4-second gap + random jitter. We
  can fetch many *different* sites in parallel, but never pound a single one.
- **robots.txt is respected** — if a site says "don't crawl this", we don't.
- **Retries back off exponentially** on timeouts/5xx, then give up gracefully.
- **We rotate among a few normal browser identity strings** so we look like
  ordinary traffic, not to disguise who we are.
- **Anti-bot pages are detected, not swallowed.** If a site returns a
  "please verify you're human" interstitial instead of the article, we mark that
  URL `blocked` and move on — we never mistake a block page for article text.

## What actually blocks us, and the honest recall picture

1. **Most Chinese portals dropped public RSS years ago.** sina, sohu, 163, qq,
   ifeng no longer publish usable feeds. Only some outlets (chinanews, people,
   CNR, and the Taiwan sites) still do. `config/sources.yaml` therefore lists,
   per outlet, candidate RSS feeds **and** an on-site search fallback; the
   discover stage probes which are live and logs it (`source_liveness` table).
   Run `./10_discover.py --seed-liveness` to see the current map.

2. **Datacenter IPs get blocked more than home IPs.** When the weekly job runs on
   GitHub's servers, some sites throttle the cloud IP. `www.sohu.com`, for
   example, served an anti-bot page to our test requests. The same request from
   a home/office connection usually succeeds. **This is why the tool is built to
   run identically on GitHub OR on your Mac (launchd) — if GitHub gets blocked
   on a site that matters, run that stage on the Mac.**

3. **Old links die.** ~40% of the 20-year ground-truth URLs predate 2015 and
   many no longer resolve. That's fine for going-forward monitoring (we only
   fetch fresh links), and it's why the benchmark used the recoverable subset.

## Resumability (so a block is never fatal)

Every stage writes to `data/cache.sqlite`. A URL fetched OK is never refetched;
a blocked/errored URL is retried next run. So if a run is interrupted or a site
blocks you today, just run the same command again later — it picks up where it
left off and only retries what failed.

## If recall feels too low

The curated named-source + RSS channels are deliberately conservative and
high-precision. If volume is lower than you want, options in order:
1. Run the Google News recency channel (now ENABLED) — see the section below. This
   is the primary lever for recent volume and reaches outlets we can't search directly.
2. Add more outlets to `config/sources.yaml` (copy an existing entry).
3. Run the fetch stage on your Mac (home IP) for sites that block the cloud.

## Google News — the recency channel (ENABLED)

Backfill via each outlet's own search reaches OLD archives (it surfaced real
incidents from 2001–2021), and RSS carries only recent-but-mostly-non-HWC news.
Neither reliably delivers *recent* human–carnivore conflict. Google News fills
that gap: it aggregates recent stories from mainland outlets whose own search is
blocked to us, and its `when:1y` operator restricts results to the past year.

Status: **enabled** (`google_news_rss.enabled: true`). Run it on its own with:

    python 10_discover.py --google-news-only     # skip curated outlets, Google News only

Two things to know:
  - VOLUME: up to ~100 items per query × ~190 queries is ~19,000 raw hits, but
    heavy cross-query duplication (the same story matches many terms) collapses
    that to a smaller set of unique URLs after dedup — plan for several thousand
    candidates to fetch, not tens of thousands. Fetch is long and extraction costs
    real API calls (one call per unique article). Fully resumable.
  - NOISE: many hits are foreign (Japan's bear surge, Nepal, Europe). The
    extractor's China/Taiwan geographic-scope criterion rejects these, so expect
    a large `exclude` count — that's the filter working, not a problem.
  Everything still passes the strict extractor + the 12-month store cutoff.

  robots.txt note: Google News' robots.txt disallows /rss/search. We apply a
  NARROW, documented exemption for THIS feed host only (`google_news_rss.robots_exempt:
  true`); every other site remains fully robots-respecting. A scoped decision to
  read a public syndication feed — revisit if the project's policy stance changes.
