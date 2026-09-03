"""Fetch items from RSS/Atom feeds and the CISA KEV catalog.

Every fetcher swallows its own errors and returns an empty list. One dead
source must never cost a morning issue.
"""

from __future__ import annotations

import datetime as dt
import html
import re
import unicodedata
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
    NHL_SCHEDULE_URL,
    TENNIS_BASE,
    TENNIS_LOOKAHEAD_WEEKS,
    USER_AGENT,
    WEATHER_URL,
    Source,
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# hnrss restates the link and score in the body; it reads as noise next to a real summary.
_BOILERPLATE_RE = re.compile(r"^\s*(article url|comments url)\s*:", re.I)
# Feeds that truncate their own summaries leave a marker behind.
_SPONSOR_RE = re.compile(r"\s+(presented by|pres\. by|sponsored by|powered by)\s+.*$", re.I)
_TRUNCATION_RE = re.compile(r"\s*(\[\s*(\.{3}|…|read more)\s*\]|\(\s*more\s*\))\s*$", re.I)


def _clean(text: str | None, limit: int = 260) -> str:
    """Strip markup and entities out of feed summaries, then truncate on a word."""
    if not text:
        return ""
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()
    text = _WS_RE.sub(" ", html.unescape(text)).strip()
    text = _TRUNCATION_RE.sub("", text)
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
        if source.require:
            haystack = f"{title} {summary}".lower()
            if not any(k in haystack for k in source.require):
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


# WMO weather codes, collapsed to the handful of phrases a masthead needs.
_WMO = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "showers", 81: "showers", 82: "heavy showers",
    85: "snow showers", 86: "snow showers",
    95: "thunderstorms", 96: "thunderstorms", 99: "thunderstorms",
}


def fetch_weather(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Today's high/low and conditions per place. Returns [] on failure."""
    out = []
    for place in places:
        try:
            resp = requests.get(
                WEATHER_URL,
                params={
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "timezone": place.get("timezone", "auto"),
                    "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                    "forecast_days": 1,
                },
                timeout=HTTP_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            daily = resp.json()["daily"]
            out.append(
                {
                    "code": place["code"],
                    "high": round(daily["temperature_2m_max"][0]),
                    "low": round(daily["temperature_2m_min"][0]),
                    "conditions": _WMO.get(daily["weather_code"][0], ""),
                }
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ! weather {place.get('code')}: {type(exc).__name__}: {exc}")
    if out:
        print(f"  · weather: {', '.join(p['code'] for p in out)}")
    return out


def _nhl_season(today: dt.date) -> str:
    """NHL seasons run Oct-Jun and are keyed by both years, e.g. 20252026."""
    start = today.year if today.month >= 7 else today.year - 1
    return f"{start}{start + 1}"


def _nhl_games(team: str, season: str) -> list[dict[str, Any]]:
    resp = requests.get(
        NHL_SCHEDULE_URL.format(team=team, season=season),
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    return resp.json().get("games", [])


def fetch_nhl(home: str, rival: str, today: dt.date) -> dict[str, Any]:
    """Last head-to-head, plus each side's next game. Returns {} on failure.

    Falls back to the previous season during the summer, so the panel still has
    a last meeting to show between June and October.
    """
    def finished(game: dict[str, Any]) -> bool:
        return game.get("gameState") in ("OFF", "FINAL")

    def h2h(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            g
            for g in games
            if finished(g) and rival in (g["awayTeam"]["abbrev"], g["homeTeam"]["abbrev"])
        ]

    season = _nhl_season(today)
    try:
        games = _nhl_games(home, season)
        head_to_head = h2h(games)
        # Between June and October the new schedule is published but nothing has
        # been played, so the last meeting is still last season's.
        if not head_to_head:
            prev = f"{int(season[:4]) - 1}{season[:4]}"
            head_to_head = h2h(_nhl_games(home, prev))
    except Exception as exc:  # noqa: BLE001
        print(f"  ! NHL: {type(exc).__name__}: {exc}")
        return {}

    upcoming = [g for g in games if g.get("gameState") in ("FUT", "PRE")]
    played_this_season = any(finished(g) for g in games)

    last = None
    if head_to_head:
        game = head_to_head[-1]
        away, home_t = game["awayTeam"], game["homeTeam"]
        period = (game.get("gameOutcome") or {}).get("lastPeriodType", "REG")
        last = {
            "date": game["gameDate"],
            "venue": (game.get("venue") or {}).get("default", ""),
            "away": away["abbrev"],
            "away_score": away.get("score"),
            "home": home_t["abbrev"],
            "home_score": home_t.get("score"),
            "overtime": period != "REG",
            "period": period,
        }

    result = {
        "last_meeting": last,
        "next_game": None,
        # Camps and preseason are on the schedule long before anything counts;
        # the panel reads "offseason" until a game has actually been played.
        "offseason": not played_this_season,
    }
    if upcoming:
        game = upcoming[0]
        result["next_game"] = {
            "date": game["gameDate"],
            "away": game["awayTeam"]["abbrev"],
            "home": game["homeTeam"]["abbrev"],
        }

    state = "offseason" if result["offseason"] else "in season"
    print(f"  · NHL: {state}" + (f", last {home}/{rival} {last['date']}" if last else ""))
    return result


def _fold(name: str) -> str:
    """Strip diacritics and case so 'Świątek' matches ESPN's 'Swiatek'."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower().strip()


def _matches(display: str, follow: str) -> bool:
    a, b = _fold(display), _fold(follow)
    if b in a:
        return True
    # Fall back to surname, which is how these players are usually listed.
    return bool(b) and b.split()[-1] == a.split()[-1] if a and b else False


def _tennis_scoreboard(tour: str, date: str | None = None) -> dict[str, Any]:
    resp = requests.get(
        TENNIS_BASE.format(tour=tour) + "/scoreboard",
        params={"dates": date} if date else None,
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    return resp.json()


def _tennis_match(comp: dict[str, Any], grouping: str, event: str) -> dict[str, Any]:
    players = []
    for side in comp.get("competitors", []):
        athlete = side.get("athlete") or {}
        players.append(
            {
                "name": athlete.get("displayName", ""),
                "winner": bool(side.get("winner")),
                "sets": [s.get("value") for s in side.get("linescores", [])],
            }
        )
    status = (comp.get("status") or {}).get("type", {})
    return {
        "event": event,
        "grouping": grouping,
        "round": (comp.get("round") or {}).get("displayName", ""),
        "date": (comp.get("date") or "")[:10],
        "state": status.get("state", ""),
        "status": status.get("description", ""),
        "players": players,
    }


def fetch_tennis(config: dict[str, Any], today: dt.date) -> dict[str, Any]:
    """Current tournaments, the followed players' matches, rankings, and what's
    next on tour. Every part degrades independently; returns {} on total failure.
    """
    if not config.get("enabled", True):
        return {}

    tours = [t.lower() for t in config.get("tours", ["atp", "wta"])]
    follow = config.get("follow", [])
    depth = int(config.get("ranking_depth", 3))
    want_upcoming = int(config.get("upcoming", 2))

    events: dict[str, dict[str, Any]] = {}
    matches: list[dict[str, Any]] = []

    for tour in tours:
        try:
            board = _tennis_scoreboard(tour)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! tennis {tour} scoreboard: {type(exc).__name__}: {exc}")
            continue
        for event in board.get("events", []):
            name = event.get("name", "")
            events.setdefault(
                name,
                {
                    "name": name,
                    "start": (event.get("date") or "")[:10],
                    "end": (event.get("endDate") or "")[:10],
                    "venue": (event.get("venue") or {}).get("fullName", ""),
                    "major": bool(event.get("major")),
                },
            )
            if not follow:
                continue
            for group in event.get("groupings", []):
                label = (group.get("grouping") or {}).get("displayName", "")
                for comp in group.get("competitions", []):
                    names = [
                        (c.get("athlete") or {}).get("displayName", "")
                        for c in comp.get("competitors", [])
                    ]
                    if any(_matches(n, f) for n in names for f in follow):
                        matches.append(_tennis_match(comp, label, name))

    # One match per player per state: their latest result and their next outing.
    def annotate(match: dict[str, Any] | None, player: str) -> dict[str, Any] | None:
        """Add who the opponent is and whether our player won — the template
        can't fold diacritics, so it can't work this out itself."""
        if not match:
            return None
        match = dict(match)
        mine = next((p for p in match["players"] if _matches(p["name"], player)), None)
        other = next((p for p in match["players"] if p is not mine), None)
        match["opponent"] = other["name"] if other else ""
        match["won"] = bool(mine and mine["winner"])
        return match

    following = []
    for player in follow:
        mine = [m for m in matches if any(_matches(p["name"], player) for p in m["players"])]
        if not mine:
            continue
        played = sorted([m for m in mine if m["state"] == "post"], key=lambda m: m["date"])
        ahead = sorted([m for m in mine if m["state"] != "post"], key=lambda m: m["date"])
        following.append(
            {
                "name": player,
                "last": annotate(played[-1] if played else None, player),
                "next": annotate(ahead[0] if ahead else None, player),
            }
        )

    rankings = {}
    for tour in tours:
        try:
            resp = requests.get(
                TENNIS_BASE.format(tour=tour) + "/rankings",
                timeout=HTTP_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            blocks = resp.json().get("rankings") or []
            if not blocks:
                continue
            rankings[tour.upper()] = [
                {
                    "rank": entry.get("current"),
                    "name": (entry.get("athlete") or {}).get("displayName", ""),
                    "points": entry.get("points"),
                }
                for entry in (blocks[0].get("ranks") or [])[:depth]
            ]
        except Exception as exc:  # noqa: BLE001
            print(f"  ! tennis {tour} rankings: {type(exc).__name__}: {exc}")

    upcoming: dict[str, dict[str, Any]] = {}
    running = set(events)
    for weeks in TENNIS_LOOKAHEAD_WEEKS:
        if len(upcoming) >= want_upcoming:
            break
        stamp = (today + dt.timedelta(weeks=weeks)).strftime("%Y%m%d")
        for tour in tours:
            try:
                board = _tennis_scoreboard(tour, stamp)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! tennis {tour} +{weeks}w: {type(exc).__name__}: {exc}")
                continue
            for event in board.get("events", []):
                name = event.get("name", "")
                start = (event.get("date") or "")[:10]
                if name in running or name in upcoming or start <= today.isoformat():
                    continue
                upcoming[name] = {
                    "name": _SPONSOR_RE.sub("", name).strip(),
                    "tour": tour.upper(),
                    "start": start,
                    "end": (event.get("endDate") or "")[:10],
                    "major": bool(event.get("major")),
                }

    result = {
        "events": sorted(events.values(), key=lambda e: e["start"]),
        "following": following,
        "rankings": rankings,
        "upcoming": sorted(upcoming.values(), key=lambda e: e["start"])[:want_upcoming],
    }
    print(
        f"  · tennis: {len(result['events'])} live, {len(following)} followed, "
        f"{len(result['upcoming'])} upcoming"
    )
    return result
