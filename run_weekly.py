#!/usr/bin/env python3
"""Cross-platform weekly runner: discover -> fetch -> extract -> geocode -> store
-> dashboard. Works identically on macOS, Windows, and Linux (unlike run_weekly.sh,
which is bash-only). This is the recommended entry point for local scheduled runs.

Each stage is resumable and writes to data/cache.sqlite, so a re-run after an
interruption is safe. On a home IP, pass --with-search to enable the richer
on-site search sweep (low-yield and slow from datacenter IPs, worthwhile from home).

Examples:
  python run_weekly.py                 # RSS-only weekly run (fast, reliable)
  python run_weekly.py --with-search   # add bounded on-site search (home IP)
  python run_weekly.py --publish       # also git-commit+push data + dashboard
"""
import argparse, subprocess, sys, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable  # same interpreter that launched this, works on any OS

def run(stage, *extra):
    cmd = [PY, str(ROOT / stage), *extra]
    print(f"\n$ {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        sys.exit(f"[run_weekly] stage {stage} failed (exit {r.returncode})")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--with-search", action="store_true", help="enable bounded on-site search (recommended on a home IP)")
    ap.add_argument("--publish", action="store_true", help="git add/commit/push data + dashboard after the run")
    args = ap.parse_args()

    print(f"=== chineseHWC weekly run {dt.datetime.now().strftime('%Y-%m-%dT%H:%M')} local ===")
    discover_flags = ["--weekly"] + (["--with-search"] if args.with_search else [])
    run("10_discover.py", *discover_flags)
    run("20_fetch.py")
    run("30_extract.py")
    run("40_geocode.py")
    run("50_store.py")
    run("build_dashboard.py")
    print("\n=== done. master + dashboard updated; review_queue.csv holds pending rows ===")

    if args.publish:
        print("\n[publish] committing data + dashboard to git ...")
        subprocess.run(["git", "add", "data/master/incidents.csv",
                        "data/master/review_queue.csv", "docs/index.html"], cwd=ROOT)
        msg = f"weekly update {dt.datetime.now():%Y-%m-%d} (local run)"
        c = subprocess.run(["git", "commit", "-m", msg], cwd=ROOT)
        if c.returncode == 0:
            subprocess.run(["git", "push"], cwd=ROOT)
            print("[publish] pushed — GitHub Pages will redeploy the dashboard shortly.")
        else:
            print("[publish] nothing new to commit.")

if __name__ == "__main__":
    main()
