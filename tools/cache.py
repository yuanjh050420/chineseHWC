"""SQLite fetch/extract cache — makes every network stage resumable and idempotent.
A re-run skips URLs already fetched OK; only missing/failed ones are retried."""
from __future__ import annotations
import sqlite3, time, json
from pathlib import Path
from .config import DATA

CACHE_PATH = DATA / "cache.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fetched (
    url           TEXT PRIMARY KEY,
    status        TEXT,          -- 'ok' | 'dead' | 'blocked' | 'error'
    http_code     INTEGER,
    fetched_at    REAL,
    final_url     TEXT,
    text          TEXT,          -- extracted main article text (trafilatura)
    title         TEXT,
    pub_date      TEXT,          -- publication date (page metadata or RSS), critical for year/month
    image_url     TEXT,          -- representative image (og:image) for dashboard popup thumbnails
    error         TEXT
);
CREATE TABLE IF NOT EXISTS discovered (
    url           TEXT PRIMARY KEY,
    source_key    TEXT,
    title         TEXT,
    pubdate       TEXT,
    query         TEXT,
    discovered_at REAL
);
CREATE TABLE IF NOT EXISTS extracted (
    url           TEXT PRIMARY KEY,
    include       INTEGER,       -- 1 keep / 0 reject
    row_json      TEXT,          -- extracted incident row (schema dict)
    model         TEXT,
    reason        TEXT,
    extracted_at  REAL
);
CREATE TABLE IF NOT EXISTS geocoded (
    place_key     TEXT PRIMARY KEY,   -- province|county|district
    lon           REAL,
    lat           REAL,
    uncertainty_m REAL,
    resolved      INTEGER,
    source        TEXT,
    matched       TEXT,
    remarks       TEXT,
    geocoded_at   REAL
);
CREATE TABLE IF NOT EXISTS source_liveness (
    source_key    TEXT,
    feed_url      TEXT,
    kind          TEXT,          -- 'rss' | 'search'
    ok            INTEGER,
    n_items       INTEGER,
    checked_at    REAL,
    note          TEXT
);
"""


# Columns added after the initial schema shipped. CREATE TABLE IF NOT EXISTS does
# NOT alter an existing table, so we additively migrate old caches here.
_MIGRATIONS = {
    "fetched": [("image_url", "TEXT")],
}

def _migrate(con):
    for table, cols in _MIGRATIONS.items():
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, decl in cols:
            if name not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    con.commit()


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or CACHE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    _migrate(con)
    return con


def get_fetched(con, url: str):
    r = con.execute("SELECT * FROM fetched WHERE url=?", (url,)).fetchone()
    return dict(r) if r else None


def save_fetched(con, url, status, http_code=None, final_url=None, text=None, title=None,
                 pub_date=None, image_url=None, error=None):
    con.execute(
        "INSERT OR REPLACE INTO fetched(url,status,http_code,fetched_at,final_url,text,title,pub_date,image_url,error) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (url, status, http_code, time.time(), final_url, text, title, pub_date, image_url, error),
    )
    con.commit()


def save_discovered(con, rows: list[dict]):
    """rows: [{url, source_key, title, pubdate, query}]  — dedup on url."""
    now = time.time()
    con.executemany(
        "INSERT OR IGNORE INTO discovered(url,source_key,title,pubdate,query,discovered_at) VALUES(?,?,?,?,?,?)",
        [(r["url"], r.get("source_key"), r.get("title"), r.get("pubdate"), r.get("query"), now) for r in rows],
    )
    con.commit()


def save_extracted(con, url, include, row: dict | None, model, reason):
    con.execute(
        "INSERT OR REPLACE INTO extracted(url,include,row_json,model,reason,extracted_at) VALUES(?,?,?,?,?,?)",
        (url, 1 if include else 0, json.dumps(row, ensure_ascii=False) if row else None, model, reason, time.time()),
    )
    con.commit()


def log_liveness(con, source_key, feed_url, kind, ok, n_items, note=""):
    con.execute(
        "INSERT INTO source_liveness(source_key,feed_url,kind,ok,n_items,checked_at,note) VALUES(?,?,?,?,?,?,?)",
        (source_key, feed_url, kind, 1 if ok else 0, n_items, time.time(), note),
    )
    con.commit()
