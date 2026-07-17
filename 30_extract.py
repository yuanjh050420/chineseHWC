#!/usr/bin/env python3
"""Stage 3 (Extract) — LLM-code each fetched article into an incident row.

Reads articles cached with status='ok', runs the benchmarked extractor
(tools/extract.py) via the Anthropic API, applies the 3 inclusion criteria, and
writes results to the `extracted` cache table. Resumable: skips already-extracted
URLs. Low-confidence / needs-review rows are KEPT and flagged (recall-favoring
policy) for human review before they enter the master store.

Requires ANTHROPIC_API_KEY (env or .env). Model via HWC_EXTRACT_MODEL.

Examples:
  ./30_extract.py                       # extract all pending fetched articles
  ./30_extract.py --limit 100
  ./30_extract.py --review-threshold 0.6
"""
import argparse, sys, os, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools import cache, extract

def _load_dotenv():
    p = Path(__file__).resolve().parent / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def _as_bool(v):
    return v if isinstance(v, bool) else (str(v).strip().lower() in ("true", "yes", "1"))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true", help="re-extract already-processed URLs")
    ap.add_argument("--review-threshold", type=float, default=0.6,
                    help="confidence below this is flagged needs_review (kept, not dropped)")
    ap.add_argument("--model", default=os.environ.get("HWC_EXTRACT_MODEL"))
    args = ap.parse_args()

    _load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY not set (env or .env). See .env.example.")
    import anthropic
    client = anthropic.Anthropic()
    model = args.model or "claude-3-5-haiku-latest"

    con = cache.connect()
    rows = con.execute("SELECT url, text, title, pub_date FROM fetched WHERE status='ok' AND length(text)>80").fetchall()

    def done(u):
        return con.execute("SELECT 1 FROM extracted WHERE url=?", (u,)).fetchone() is not None

    todo = [r for r in rows if args.force or not done(r["url"])]
    print(f"[extract] fetched articles: {len(rows)} | to extract: {len(todo)} | model: {model}", flush=True)

    sysmsg = extract.build_system()
    counts = {"include": 0, "exclude": 0, "review": 0}
    for i, r in enumerate(todo, 1):
        user = extract.build_user(r["text"], title=r["title"], pub_date=r["pub_date"])
        try:
            msg = client.messages.create(model=model, max_tokens=700, system=sysmsg,
                                         messages=[{"role": "user", "content": user}])
            parsed = extract.parse_response(msg.content[0].text)
        except Exception as e:
            cache.save_extracted(con, r["url"], False, None, model, f"api_error: {str(e)[:150]}")
            continue
        include = _as_bool(parsed.get("include"))
        conf = parsed.get("confidence") or 0
        try: conf = float(conf)
        except Exception: conf = 0.0
        needs_review = parsed.get("needs_review", False) or (include and conf < args.review_threshold)
        row = extract.to_row(parsed, r["url"], model, title=r["title"]) if include else None
        if row is not None:
            row["_needs_review"] = bool(needs_review)
            row["pub_date"] = r["pub_date"]
        reason = parsed.get("exclude_reason") if not include else ("needs_review" if needs_review else "ok")
        cache.save_extracted(con, r["url"], include, row, model, reason)
        counts["include"] += int(include); counts["exclude"] += int(not include)
        counts["review"] += int(bool(needs_review) and include)
        if i % 25 == 0:
            print(f"[extract] {i}/{len(todo)} {counts}", flush=True)

    print(f"[extract] done {counts}")
    print(f"[extract] {counts['review']} included rows flagged for human review")

if __name__ == "__main__":
    main()
