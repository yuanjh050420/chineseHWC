"""Shared config + path helpers. Every stage imports from here so the schema,
species list, and source list are defined in exactly one place (config/*.yaml)."""
from __future__ import annotations
import functools
from pathlib import Path
import yaml

# Repo root = parent of this tools/ dir. All default paths are relative to it,
# so scripts are always run from repo root (mohammad-style convention).
ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"


@functools.lru_cache(maxsize=None)
def _load(name: str) -> dict:
    return yaml.safe_load((CONFIG / name).read_text())


def schema() -> dict:
    return _load("schema.yaml")


def search_terms() -> dict:
    return _load("search_terms.yaml")


def sources() -> dict:
    return _load("sources.yaml")


def all_sources() -> list[dict]:
    """Curated mainland + Taiwan sources as one list (each dict gets region already)."""
    s = sources()
    return list(s.get("sources", [])) + list(s.get("taiwan_sources", []))


def species_list() -> list[dict]:
    return schema()["species"]


def columns() -> list[str]:
    """Canonical 14 DB columns + provenance columns, in write order."""
    sc = schema()
    return list(sc["columns"]) + list(sc["provenance_columns"])


def db_columns() -> list[str]:
    """Just the original 14 columns (for comparing against the seed CSV)."""
    return list(schema()["columns"])


def conflict_types() -> list[str]:
    return schema()["conflict_types"]


def build_queries() -> list[dict]:
    """Cartesian product species-term x conflict-keyword -> query strings.
    Returns [{species, species_term, keyword_zh, keyword_en, query}]."""
    st = search_terms()
    prefix = st["country_prefix"]
    join = st.get("join", " ")
    out = []
    for sp in species_list():
        for term in sp["chinese"]:
            for kw_zh, kw_en in st["conflict_keywords"].items():
                out.append({
                    "species": sp["english"],
                    "species_term": term,
                    "keyword_zh": kw_zh,
                    "keyword_en": kw_en,
                    "query": join.join([prefix, term, kw_zh]),
                })
    return out


# Map any Chinese species term back to its canonical English name (for extraction QA).
@functools.lru_cache(maxsize=None)
def term_to_species() -> dict:
    m = {}
    for sp in species_list():
        for t in sp["chinese"]:
            m[t] = sp["english"]
    return m
