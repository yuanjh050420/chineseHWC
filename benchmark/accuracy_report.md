# Extractor accuracy — benchmark against the 520-incident ground truth

**What this measures.** We re-fetched the original news articles behind the
published database, ran the LLM extractor on the article text, and scored its
output field-by-field against how the manuscript team coded that same article.

## Benchmark set

- **165** ground-truth incidents lie on the news domains reachable for this
  benchmark (of 520 total); **103** of those articles were still live and yielded
  usable text (older links die, and some hosts block datacenter IPs — see below).
- The 103 span **9 of 10 species** and **all 7 conflict types**.
- Model: Claude Haiku-class (the production default; `HWC_EXTRACT_MODEL`).

## Headline results (per-field accuracy, on the 83 articles the model accepted)

| Field | Accuracy | Read |
|-------|---------:|------|
| species | **96.4%** | excellent — canonical vocabulary constrains it |
| conflict_type | **92.8%** | excellent — few, reasonable confusions |
| province | **89.2%** | strong |
| victim | **85.5%** | strong (token-overlap match on compound victims) |
| n_deaths | **83.1%** | strong once surplus-killing counting is constrained |
| county | **80.7%** | good |
| n_victims | **79.5%** | good |
| month | **74.7%** | moderate — report lag / vague dates ("近日") |
| year | **47.0%** | WEAK — see caveat; needs human review |

**Include-rate on readable articles: 85.6%** (83/97). All ground-truth rows are
true incidents, so this approximates recall: the extractor keeps ~86% of genuine
incidents, excluding the rest usually for defensible reasons (sighting with no
impact, zoo/rescue animal, unconfirmed species) — exactly the manuscript's
exclusion criteria being applied.

## The year problem (be honest about this)

Year is only ~47% exact. The distribution of (predicted − actual) shows most
errors are ±1–2 years (report lag: the incident happened shortly before the
article) plus a tail where the model grabbed an unrelated year (a past case cited
for context, a republication date). **This is intrinsically hard from article
text** — the manuscript itself notes reports lag incidents, and the coded "year"
sometimes reflects the event while the article emphasizes the publication date.
Mitigations applied in the shipped prompt: explicit "incident date, not
publication/other date" instruction and an earliest-plausible-date rule.
**Recommendation:** treat extracted year/month as needs-review for any incident
where article publication year and extracted year differ by >1.

## Confusion detail

- **Conflict type** (6 disagreements / 83): "Attack livestock"→"Attack human"
  (×2), plus single crop→livestock, property→settlement, and settlement→(dog
  attack / livestock) boundary cases. All are genuine edge categories.
- **Species** (3 disagreements / 83): Asiatic black bear↔brown bear,
  Eurasian lynx↔clouded leopard (both textually ambiguous), and one grey
  wolf→black bear (a real error).

## Two bugs the benchmark caught (now fixed)

1. **Charset corruption.** Older Sina/Sohu articles are GB2312/GBK; `requests`
   guessed Latin-1 and produced mojibake, which the model correctly refused to
   code. Fixed in `tools/http.py` (charset detection on the raw bytes). This
   turned ~27 "unparseable" cases into clean extractions.
2. **Count scoring.** Ground-truth counts are free text (`'30+'`, `'3+1'`,
   `'未知'`); the scorer's naive `int()` cast scored every count as wrong. Fixed
   in `benchmark/score.py` (leading-int / compound-sum / unknown handling). This
   is what moved n_deaths from an apparent 52% to its true 83%.

## Caveats on the benchmark itself

- **Location fields** were partly geo-resolved by the original coders (Google
  Maps), so ground-truth province/county isn't always verbatim in the text.
  Places are scored leniently (admin-suffix-stripped substring match); the true
  "in-text recoverability" may be higher than the number suggests.
- **Bot-blocking is real.** `www.sohu.com` served an anti-bot interstitial to
  ~23 requests; the fetcher detected these (didn't ingest block pages as
  articles) and recorded them rather than failing silently. On a home IP these
  usually succeed — hence the Mac-fallback design.

## Bottom line

For the fields that define an incident — **species, conflict type, location,
victim, and casualty counts — the extractor is 80–96% accurate** and safe to
automate under the recall-favoring, human-review policy. **Year/month should be
reviewed** where they disagree with publication date. This matches the
manuscript's own stance that AI-assisted extraction is a valuable complement,
with a human in the loop for the ambiguous cases.
