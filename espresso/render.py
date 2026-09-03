"""Render an issue to HTML via Jinja2."""

from __future__ import annotations

import datetime as dt
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import SECTIONS, TEMPLATES
from .fetch import Item


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["timeago"] = timeago
    env.filters["domain"] = domain
    env.filters["shortdate"] = shortdate
    return env


def timeago(when: dt.datetime | str | None, now: dt.datetime | None = None) -> str:
    if not when:
        return ""
    if isinstance(when, str):
        try:
            when = dt.datetime.fromisoformat(when)
        except ValueError:
            return ""
    now = now or dt.datetime.now(dt.timezone.utc)
    minutes = int((now - when).total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)}m ago"
    if minutes < 60 * 24:
        return f"{minutes // 60}h ago"
    return f"{minutes // (60 * 24)}d ago"


def shortdate(value: str) -> str:
    """2026-03-17 -> 17 MAR, matching the design's inset headers."""
    try:
        return dt.date.fromisoformat(value).strftime("%-d %b").upper()
    except (TypeError, ValueError):
        return value or ""


def domain(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).netloc.removeprefix("www.")


def build_rotating(rotating: dict[str, Any], day: dt.date) -> dict[str, Any] | None:
    """The dark panel. Returns None when disabled or empty."""
    if not rotating.get("enabled") or not rotating.get("entry"):
        return None

    panel = {
        "label": rotating.get("label", ""),
        "caption": rotating.get("countdown_caption", ""),
        "entries": [
            {"title": e.get("title", ""), "body": " ".join(e.get("body", "").split())}
            for e in rotating["entry"]
        ],
        "days": None,
    }
    target = rotating.get("countdown_date")
    if target:
        try:
            panel["days"] = (dt.date.fromisoformat(target) - day).days
        except ValueError:
            print(f"  ! rotating: bad countdown_date {target!r}")
    return panel


def build_issue(
    day: dt.date,
    ranked: dict[str, list[Item]],
    kev: list[dict[str, Any]],
    drill: dict[str, Any],
    now: dt.datetime,
    *,
    weather: list[dict[str, Any]] | None = None,
    nhl: dict[str, Any] | None = None,
    rotating: dict[str, Any] | None = None,
    masthead: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The single dict that both the HTML template and the JSON snapshot read."""
    sections = {
        key: {"key": key, "label": label, "stories": [i.to_dict() for i in ranked.get(key, [])]}
        for key, label in SECTIONS
    }
    return {
        "date": day.isoformat(),
        "date_long": day.strftime("%A, %B %-d, %Y"),
        # The design sets the date in mono caps: TUESDAY 1 SEPTEMBER 2026.
        "date_mast": day.strftime("%A %-d %B %Y").upper(),
        "built_at": now.isoformat(),
        "masthead": masthead or {},
        "sections": sections,
        # Filled in by publish(), which is the only place that can count
        # editions on disk. Kept here so the JSON snapshot always has the key.
        "edition_no": None,
        "sources_line": ", ".join(
            sorted({i.source.upper() for group in ranked.values() for i in group})
        ),
        "weather": weather or [],
        "kev": kev,
        "nhl": nhl or {},
        "rotating": rotating,
        "drill": drill,
        "counts": {
            "stories": sum(len(v) for v in ranked.values()),
            "kev": len(kev),
        },
    }


def render_issue(
    issue: dict[str, Any],
    *,
    asset_prefix: str,
    root_prefix: str = "",
    permalink: str | None = None,
) -> str:
    template = _env().get_template("espresso.html.j2")
    return template.render(
        issue=issue, asset_prefix=asset_prefix, root_prefix=root_prefix, permalink=permalink
    )


def render_archive(
    editions: list[dict[str, Any]], *, asset_prefix: str, root_prefix: str = ""
) -> str:
    template = _env().get_template("archive.html.j2")
    return template.render(editions=editions, asset_prefix=asset_prefix, root_prefix=root_prefix)
