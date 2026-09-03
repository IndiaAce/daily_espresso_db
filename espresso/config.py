"""Paths, the source registry, and the standing config for the fixed panels."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

DATA = ROOT / "data"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
DOCS = ROOT / "docs"

SOURCES_FILE = DATA / "sources.toml"
FRENCH_FILE = DATA / "french.json"
SEEN_FILE = DATA / "seen.json"

# Feed-driven sections. The template places them; this only routes sources.
SECTIONS = [
    ("email_security", "Email Security"),
    ("ai", "AI / ML Research"),
    ("france", "France & Europe"),
    ("nhl", "NHL"),
    ("tennis", "Tennis"),
]

# The NHL panel spends most of its height on the scoreline box, so it takes
# fewer stories than the others.
SECTION_LIMITS = {"email_security": 3, "ai": 3, "france": 3, "nhl": 2, "tennis": 2}

# Items older than this never appear, even if a feed keeps serving them.
MAX_AGE_DAYS = 5

# How long a URL stays suppressed in seen.json before it is forgotten.
SEEN_RETENTION_DAYS = 90

USER_AGENT = "daily-espresso/0.2 (+https://github.com/IndiaAce/daily_espresso_db)"
HTTP_TIMEOUT = 20

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
KEV_WINDOW_DAYS = 14
KEV_LIMIT = 3

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
NHL_SCHEDULE_URL = "https://api-web.nhle.com/v1/club-schedule-season/{team}/{season}"

TENNIS_BASE = "https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}"
# Weeks ahead to probe for the next tournaments. Each probe is one request per
# tour, so this trades build time for how far the "next up" list can see.
TENNIS_LOOKAHEAD_WEEKS = (2, 3, 4, 6)


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    section: str
    weight: float = 1.0
    cap: int | None = None
    # When set, an item must mention one of these to qualify. Lets a general
    # security feed contribute to a narrow section without a separate source.
    require: tuple[str, ...] = ()


@dataclass
class Config:
    sources: list[Source] = field(default_factory=list)
    weather: list[dict[str, Any]] = field(default_factory=list)
    nhl: dict[str, Any] = field(default_factory=dict)
    tennis: dict[str, Any] = field(default_factory=dict)
    rotating: dict[str, Any] = field(default_factory=dict)
    masthead: dict[str, Any] = field(default_factory=dict)


def load_config(path: Path | None = None) -> Config:
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
                require=tuple(k.lower() for k in entry.get("require", [])),
            )
        )

    return Config(
        sources=sources,
        weather=raw.get("weather", {}).get("place", []),
        nhl=raw.get("nhl", {}),
        tennis=raw.get("tennis", {}),
        rotating=raw.get("rotating", {}),
        masthead=raw.get("masthead", {}),
    )
