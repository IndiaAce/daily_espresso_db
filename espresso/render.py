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


def domain(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).netloc.removeprefix("www.")


def build_issue(
    day: dt.date,
    ranked: dict[str, list[Item]],
    kev: list[dict[str, Any]],
    drill: dict[str, Any],
    now: dt.datetime,
) -> dict[str, Any]:
    """The single dict that both the HTML template and the JSON snapshot read."""
    return {
        "date": day.isoformat(),
        "date_long": day.strftime("%A, %B %-d, %Y"),
        "weekday": day.strftime("%A"),
        "built_at": now.isoformat(),
        "sections": [
            {"key": key, "label": label, "stories": [i.to_dict() for i in ranked.get(key, [])]}
            for key, label in SECTIONS
        ],
        "kev": kev,
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
