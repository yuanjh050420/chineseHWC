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

**Project decision (Roland, Jul 2026): accept this low volume as the true base
rate.** We deliberately do NOT enable general search-engine aggregators (e.g.
Google News) to inflate the count, to keep the data high-quality and consistent
with the manuscript's named-source methodology. Incidents accumulate slowly and
honestly. If a genuine conflict story exists only on a non-RSS mainland site, we
may miss it — that is an accepted limitation, not a bug to fix.

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

The curated + RSS approach is deliberately conservative (your choice: "named
sites + RSS only"). If weekly volume is lower than you want, options in order:
1. Add more outlets to `config/sources.yaml` (copy an existing entry).
2. Enable the Google News RSS fallback (`google_news_rss.enabled: true`) — it's
   a general-engine aggregator that accepts the same species×keyword queries and
   returns far more candidates, at the cost of stepping outside the curated list.
3. Run the fetch stage on your Mac (home IP) for sites that block the cloud.
