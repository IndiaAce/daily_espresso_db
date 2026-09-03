"""Paths and the source registry."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA = ROOT / "data"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
DOCS = ROOT / "docs"

SOURCES_FILE = DATA / "sources.toml"
FRENCH_FILE = DATA / "french.json"
SEEN_FILE = DATA / "seen.json"

# Sections, in the order they appear in an issue.
SECTIONS = [
    ("security", "Security"),
    ("ai", "AI & ML"),
]

# How many items survive into each section.
SECTION_LIMITS = {"security": 5, "ai": 5}

# Items older than this never appear, even if a feed keeps serving them.
MAX_AGE_DAYS = 5

# How long a URL stays suppressed in seen.json before it is forgotten.
SEEN_RETENTION_DAYS = 90

USER_AGENT = "daily-espresso/0.1 (+https://github.com/IndiaAce/daily_espresso_db)"
HTTP_TIMEOUT = 20

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
KEV_WINDOW_DAYS = 14
KEV_LIMIT = 4


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    section: str
    weight: float = 1.0
    cap: int | None = None


def load_sources(path: Path | None = None) -> list[Source]:
    """Read sources.toml. Unknown sections are dropped with a warning."""
    path = path or SOURCES_FILE
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)

    known = {key for key, _ in SECTIONS}
    sources: list[Source] = []
    for entry in raw.get("source", []):
        section = entry.get("section")
        if section not in known:
            print(f"  ! skipping {entry.get('name')!r}: unknown section {section!r}")
            continue
        sources.append(
            Source(
                name=entry["name"],
                url=entry["url"],
                section=section,
                weight=float(entry.get("weight", 1.0)),
                cap=entry.get("cap"),
            )
        )
    return sources
