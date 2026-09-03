"""Fetch items from RSS/Atom feeds and the CISA KEV catalog.

Every fetcher swallows its own errors and returns an empty list. One dead
source must never cost a morning issue.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from dataclasses import dataclass, field
from typing import Any

import feedparser
import requests

from .config import (
    HTTP_TIMEOUT,
    KEV_LIMIT,
    KEV_URL,
    KEV_WINDOW_DAYS,
    MAX_AGE_DAYS,
    USER_AGENT,
    Source,
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# hnrss restates the link and score in the body; it reads as noise next to a real summary.
_BOILERPLATE_RE = re.compile(r"^\s*(article url|comments url)\s*:", re.I)


def _clean(text: str | None, limit: int = 260) -> str:
    """Strip markup and entities out of feed summaries, then truncate on a word."""
    if not text:
        return ""
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()
    text = _WS_RE.sub(" ", html.unescape(text)).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",.;:—-") + "…"


def _published(entry: Any) -> dt.datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return dt.datetime(*parsed[:6], tzinfo=dt.timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


@dataclass
class Item:
    title: str
    url: str
    source: str
    section: str
    published: dt.datetime | None = None
    summary: str = ""
    weight: float = 1.0
    tags: list[str] = field(default_factory=list)
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "section": self.section,
            "published": self.published.isoformat() if self.published else None,
            "summary": self.summary,
            "tags": self.tags,
        }


def fetch_feed(source: Source, now: dt.datetime) -> list[Item]:
    """Pull one RSS/Atom feed. Returns [] on any failure."""
    try:
        resp = requests.get(
            source.url,
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"},
        )
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as exc:  # noqa: BLE001 - a bad feed is expected, not exceptional
        print(f"  ! {source.name}: {type(exc).__name__}: {exc}")
        return []

    if parsed.bozo and not parsed.entries:
        print(f"  ! {source.name}: unparseable ({parsed.get('bozo_exception')})")
        return []

    cutoff = now - dt.timedelta(days=MAX_AGE_DAYS)
    items: list[Item] = []
    for entry in parsed.entries:
        link = (entry.get("link") or "").strip()
        title = _clean(entry.get("title"), limit=180)
        if not link or not title:
            continue
        summary = _clean(entry.get("summary") or entry.get("description"))
        if _BOILERPLATE_RE.match(summary):
            summary = ""
        published = _published(entry)
        # Feeds that omit dates entirely still deserve a slot; only drop
        # items we know to be stale.
        if published and published < cutoff:
            continue
        items.append(
            Item(
                title=title,
                url=link,
                source=source.name,
                section=source.section,
                published=published,
                summary=summary,
                weight=source.weight,
            )
        )

    print(f"  · {source.name}: {len(items)} item(s)")
    return items


def fetch_kev(now: dt.datetime) -> list[dict[str, Any]]:
    """Recently-added CISA Known Exploited Vulnerabilities. Returns [] on failure."""
    try:
        resp = requests.get(KEV_URL, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        catalog = resp.json()
    except Exception as exc:  # noqa: BLE001
        print(f"  ! CISA KEV: {type(exc).__name__}: {exc}")
        return []

    cutoff = (now - dt.timedelta(days=KEV_WINDOW_DAYS)).date()
    recent = []
    for vuln in catalog.get("vulnerabilities", []):
        try:
            added = dt.date.fromisoformat(vuln["dateAdded"])
        except (KeyError, ValueError):
            continue
        if added < cutoff:
            continue
        recent.append(
            {
                "cve": vuln.get("cveID", ""),
                "vendor": vuln.get("vendorProject", ""),
                "product": vuln.get("product", ""),
                "name": vuln.get("vulnerabilityName", ""),
                "summary": _clean(vuln.get("shortDescription"), limit=220),
                "added": added.isoformat(),
                "due": vuln.get("dueDate", ""),
                "ransomware": vuln.get("knownRansomwareCampaignUse") == "Known",
                "url": f"https://nvd.nist.gov/vuln/detail/{vuln.get('cveID', '')}",
            }
        )

    # Newest first; ransomware-linked entries win ties.
    recent.sort(key=lambda v: (v["added"], v["ransomware"]), reverse=True)
    print(f"  · CISA KEV: {len(recent)} added in last {KEV_WINDOW_DAYS}d")
    return recent[:KEV_LIMIT]
