"""Dedupe, score, and cap the fetched items."""

from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urlsplit, urlunsplit

from .config import SECTION_LIMITS
from .fetch import Item

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have how in is it its of on or that the to "
    "was were what when where which who will with your you new now".split()
)
# Query params that identify a campaign, not a document.
_JUNK_PARAMS = ("utm_", "ref", "ref_src", "source", "fbclid", "gclid", "mc_cid", "mc_eid")

# Vendor feeds mix marketing into the news stream. These are ads, not stories,
# and their freshness makes them rank well, so they have to be cut explicitly.
_NOISE_RE = re.compile(
    r"^\s*\[(virtual event|webinar|live event|on-demand|podcast|sponsored)\]"
    r"|\bsponsored content\b"
    r"|\bregister (now|today)\b"
    r"|\bwhitepaper\b",
    re.I,
)


def is_noise(title: str) -> bool:
    return bool(_NOISE_RE.search(title))


def canonical_url(url: str) -> str:
    """Strip tracking params and trailing slashes so the same story dedupes."""
    parts = urlsplit(url)
    query = "&".join(
        p
        for p in parts.query.split("&")
        if p and not any(p.lower().startswith(j) for j in _JUNK_PARAMS)
    )
    path = parts.path.rstrip("/") or "/"
    netloc = parts.netloc.lower().removeprefix("www.")
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def _tokens(title: str) -> frozenset[str]:
    return frozenset(w for w in _WORD_RE.findall(title.lower()) if w not in _STOPWORDS and len(w) > 2)


def _similar(a: frozenset[str], b: frozenset[str], threshold: float = 0.6) -> bool:
    """Jaccard-ish overlap against the smaller title, so a headline that is a
    prefix of a longer one still counts as the same story."""
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= threshold


def score(item: Item, now: dt.datetime) -> float:
    """source weight x recency decay. Undated items are treated as ~1 day old."""
    if item.published:
        age_hours = max((now - item.published).total_seconds() / 3600.0, 0.0)
    else:
        age_hours = 24.0
    # Halves roughly every 36 hours.
    decay = 0.5 ** (age_hours / 36.0)
    return item.weight * decay


def rank(
    items: list[Item],
    now: dt.datetime,
    seen: dict[str, str],
    caps: dict[str, int] | None = None,
    limits: dict[str, int] | None = None,
) -> dict[str, list[Item]]:
    """Group items by section, then filter -> dedupe -> cap -> truncate."""
    caps = caps or {}
    limits = limits or SECTION_LIMITS

    by_section: dict[str, list[Item]] = {}
    for item in items:
        item.score = score(item, now)
        by_section.setdefault(item.section, []).append(item)

    result: dict[str, list[Item]] = {}
    for section, group in by_section.items():
        group.sort(key=lambda i: i.score, reverse=True)

        chosen: list[Item] = []
        chosen_tokens: list[frozenset[str]] = []
        per_source: dict[str, int] = {}
        limit = limits.get(section, 5)

        for item in group:
            if is_noise(item.title):
                continue
            key = canonical_url(item.url)
            if key in seen:
                continue
            cap = caps.get(item.source)
            if cap is not None and per_source.get(item.source, 0) >= cap:
                continue
            tokens = _tokens(item.title)
            if any(_similar(tokens, other) for other in chosen_tokens):
                continue

            chosen.append(item)
            chosen_tokens.append(tokens)
            per_source[item.source] = per_source.get(item.source, 0) + 1
            if len(chosen) >= limit:
                break

        result[section] = chosen
    return result
