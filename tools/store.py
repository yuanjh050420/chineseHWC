"""Master incident store — the single source of truth the dashboard reads and
the weekly job appends to. Seeded once from the published 520-row database.

Format: Parquet (canonical, typed) + a CSV mirror (human-readable, git-diffable,
committed back by the weekly GitHub Action). Dedup on URL, plus a fuzzy
(species, year, month, county) guard against the same incident reported by
multiple outlets.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from .config import DATA, db_columns, columns, schema

MASTER_PARQUET = DATA / "master" / "incidents.parquet"
MASTER_CSV = DATA / "master" / "incidents.csv"
SEED_CSV = DATA / "seed" / "All_species.csv"


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=columns())


def load() -> pd.DataFrame:
    if MASTER_PARQUET.exists():
        return pd.read_parquet(MASTER_PARQUET)
    return _empty()


def seed_from_published(force: bool = False) -> pd.DataFrame:
    """Load All_species.csv into the master store with provenance columns filled."""
    if MASTER_PARQUET.exists() and not force:
        return load()
    df = pd.read_csv(SEED_CSV)
    df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]
    # provenance — the 520 historical rows
    df["source"] = "seed_2025_manuscript"
    df["discovered_date"] = ""
    df["extract_model"] = ""
    df["extract_confidence"] = ""
    df["title"] = ""
    df["summary_en"] = ""
    df["summary_zh"] = ""
    df["image_url"] = ""
    df["needs_review"] = 0
    # geocoding provenance: these coords were placed MANUALLY via Google Maps to
    # township precision, as bare points; we record that regime and leave the
    # automated-uncertainty field unknown (not zero — we genuinely don't have it).
    df["geocode_source"] = "manual_googlemaps_2025"
    df["coordinateUncertaintyInMeters"] = pd.NA
    df["geocode_matched"] = ""
    for c in columns():
        if c not in df.columns:
            df[c] = pd.NA
    df = df[columns()]
    write(df)
    return df


# Columns that are free text in the historical DB ('30+', '3+1', '未知') but may
# arrive as ints from the extractor — store as string so both regimes coexist.
_TEXTUAL = ["Number of victems", "Number of deaths", "No.", "Year", "Month",
            "extract_confidence", "coordinateUncertaintyInMeters"]

def write(df: pd.DataFrame):
    MASTER_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    # tolerate schema additions: any column in the current schema that an older
    # master lacks is created blank, so re-writes never KeyError after a schema bump.
    for c in columns():
        if c not in df.columns:
            df[c] = pd.NA
    df = df[columns()].copy()
    # normalize mixed-type columns to nullable string to keep parquet/csv stable
    for c in _TEXTUAL:
        if c in df.columns:
            df[c] = df[c].apply(lambda v: "" if pd.isna(v) else str(v))
    df.to_parquet(MASTER_PARQUET, index=False)
    df.to_csv(MASTER_CSV, index=False)


def _incident_key(row) -> tuple:
    return (str(row.get("Species", "")).strip(),
            row.get("Year"), row.get("Month"),
            str(row.get("County", "")).strip())


def append(new_rows: pd.DataFrame) -> dict:
    """Append new incident rows, deduping on URL and on the fuzzy incident key.
    Returns {added, dup_url, dup_incident}."""
    master = load()
    known_urls = set(master["URL"].dropna().astype(str)) if len(master) else set()
    known_keys = set(master.apply(_incident_key, axis=1)) if len(master) else set()
    added, dup_url, dup_inc = [], 0, 0
    for _, r in new_rows.iterrows():
        if str(r.get("URL")) in known_urls:
            dup_url += 1; continue
        k = _incident_key(r)
        if k in known_keys:
            dup_inc += 1; continue
        added.append(r); known_urls.add(str(r.get("URL"))); known_keys.add(k)
    if added:
        out = pd.concat([master, pd.DataFrame(added)], ignore_index=True)
        write(out)
    return {"added": len(added), "dup_url": dup_url, "dup_incident": dup_inc, "total": len(load())}


def next_id(species_english: str, existing: pd.DataFrame | None = None) -> str:
    """Assign the next stable incident id for a species (e.g. ABB188)."""
    sp = next((s for s in schema()["species"] if s["english"] == species_english), None)
    prefix = sp["id_prefix"] if sp else "UNK"
    df = existing if existing is not None else load()
    nums = []
    for v in df.loc[df["Species"] == species_english, "No."].dropna().astype(str):
        if v.startswith(prefix) and v[len(prefix):].isdigit():
            nums.append(int(v[len(prefix):]))
    return f"{prefix}{(max(nums) + 1) if nums else 1:03d}"
