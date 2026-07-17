#!/usr/bin/env bash
# Weekly monitor run: discover -> fetch -> extract -> geocode -> store -> dashboard.
# Each stage is resumable and writes to data/cache.sqlite; safe to re-run.
# Used by both the GitHub Actions cron and the launchd Mac fallback.
set -euo pipefail
cd "$(dirname "$0")"

echo "=== chineseHWC weekly run $(date -u +%Y-%m-%dT%H:%MZ) ==="

# 1. Discover candidate URLs from curated outlets (recent window only).
python3 10_discover.py --weekly

# 2. Fetch + extract text (polite, resumable, bot-block-resilient).
python3 20_fetch.py

# 3. LLM-extract incidents (needs ANTHROPIC_API_KEY).
python3 30_extract.py

# 4. Geocode new incidents (Nominatim gazetteer + uncertainty).
python3 40_geocode.py

# 5. Store: auto-publish confident rows to master; queue the rest for review.
python3 50_store.py

# 6. Rebuild the static dashboard from the updated master.
python3 build_dashboard.py

echo "=== done. master + dashboard updated; review_queue.csv holds pending rows ==="