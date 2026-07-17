# CLAUDE.md — chineseHWC-monitor

## Goal
Weekly automated monitoring of human–large-carnivore conflict news in China +
Taiwan, extending the published 520-incident (2005–2024) dataset. Discover →
fetch → LLM-extract → geocode → store → rebuild HTML dashboard. Runs on GitHub
Actions (weekly) and publishes to GitHub Pages; embeddable in rolandkays.com.

## How to run
Standalone numbered scripts at repo root (10_discover, 20_fetch, 30_extract,
40_geocode, 50_store, build_dashboard), chained by run_weekly.sh. See each
`--help`. Config in config/*.yaml (schema, search_terms, sources). Shared code
in tools/ (config, http, cache, discover, extract, geocode, store, dashboard_template).

## Method fidelity (from the manuscript — do not drift from these)
- Search string mirrors the paper: 中国 + [species Chinese name] + [conflict keyword].
- 13 species (10 with records); 7 standardized conflict types; victim/deaths counts.
- 3 inclusion criteria: professional media w/ ≥month + ≥township precision; genuine
  negative impact by a WILD carnivore; animal in human-dominated landscape.
- Conservative counting: "two or three"→2, "more than ten"→11, unspecified casualties→1.
- Surplus killing = single event with >2 fatalities.

## Conventions & guardrails
- Isolated to this folder. Do not touch files outside it.
- Every network stage is resumable + idempotent (SQLite cache); re-running is safe.
- Polite crawling only: per-host rate limits, robots.txt, backoff. Never defeat
  CAPTCHAs or spoof to evade bot detection — record a block and move on.
- Secrets via .env / GitHub Actions secrets only; never hardcode or commit keys.
- Destructive commands (rm, git push, git reset --hard) — ask before running.

## Status / next steps
- [x] Scaffold, config, shared tools, master store seeded (520 rows).
- [x] LLM extractor + benchmark vs 520 GT (species 96%, type 93%, ..., year 47% flagged).
- [x] Discover + fetch stages (validated live on LTN feed; pub-date capture).
- [x] Extract + geocode + store stages (review-queue split; year/month pubdate fallback).
- [x] Self-contained HTML dashboard (docs/index.html; Leaflet + Chart.js).
- [x] GitHub Actions weekly workflow + launchd fallback + WordPress embed guide.
- [ ] USER: push to GitHub, add ANTHROPIC_API_KEY secret, enable Pages, run once.
- Extractor policy: favor recall + human review queue (auto-publish confident, queue borderline).
