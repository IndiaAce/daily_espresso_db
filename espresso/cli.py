"""python -m espresso <command>"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from .archive import load_seen, publish, save_seen
from .config import DOCS, load_config
from .drill import drill_for
from .fetch import fetch_feed, fetch_kev, fetch_nhl, fetch_weather
from .rank import canonical_url, rank
from .render import build_issue, build_rotating


def _gather(day: dt.date, now: dt.datetime, use_seen: bool):
    config = load_config()
    print(f"Fetching {len(config.sources)} source(s)…")

    items = []
    for source in config.sources:
        items.extend(fetch_feed(source, now))

    kev = fetch_kev(now)
    weather = fetch_weather(config.weather)
    nhl = fetch_nhl(config.nhl.get("home", ""), config.nhl.get("rival", ""), day) if config.nhl else {}
    if nhl and config.nhl.get("label"):
        nhl["label"] = config.nhl["label"]

    seen = load_seen() if use_seen else {}
    # Today's own picks must not suppress themselves: without this, re-running
    # a build for a date that already published would drop its whole front page
    # and republish the runners-up.
    already = {url for url, seen_on in seen.items() if seen_on == day.isoformat()}
    caps = {s.name: s.cap for s in config.sources if s.cap is not None}
    ranked = rank(items, now, {u: d for u, d in seen.items() if u not in already}, caps=caps)

    issue = build_issue(
        day,
        ranked,
        kev,
        drill_for(day),
        now,
        weather=weather,
        nhl=nhl,
        rotating=build_rotating(config.rotating, day),
        masthead=config.masthead,
    )
    return issue, ranked, seen


def cmd_brew(args: argparse.Namespace) -> int:
    day = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    now = dt.datetime.now(dt.timezone.utc)

    issue, ranked, seen = _gather(day, now, use_seen=not args.ignore_seen)

    print()
    _summarize(issue)

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    out = Path(args.out) if args.out else DOCS
    written = publish(issue, out)

    if not args.ignore_seen:
        for group in ranked.values():
            for item in group:
                seen.setdefault(canonical_url(item.url), day.isoformat())
        save_seen(seen, day)

    print(f"\nWrote {written['index']}")
    print(f"      {written['dated']}")
    print(f"      {written['archive']}")
    return 0


def cmd_drill(args: argparse.Namespace) -> int:
    day = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    result = drill_for(day)
    print(f"{day:%A, %B %d} — French")
    for card in result["cards"]:
        print(f"  {card['fr']:<28} {card['en']}")
    return 0


def _summarize(issue: dict) -> None:
    print(f"{issue['date_long']} — {issue['counts']['stories']} stories, {issue['counts']['kev']} KEV")

    if issue["weather"]:
        line = "  ".join(
            f"{p['code']} {p['high']}°/{p['low']}° {p['conditions']}" for p in issue["weather"]
        )
        print(f"\n  [Weather] {line}")

    for section in issue["sections"].values():
        print(f"\n  [{section['label']}]")
        if not section["stories"]:
            print("    (nothing today)")
        for item in section["stories"]:
            print(f"    · {item['title'][:88]}")
            print(f"      {item['source']}")

    if issue["kev"]:
        print("\n  [Actively exploited]")
        for vuln in issue["kev"]:
            flag = " ⚠ ransomware" if vuln["ransomware"] else ""
            print(f"    · {vuln['cve']} — {vuln['vendor']} {vuln['product']}{flag}")

    nhl = issue.get("nhl") or {}
    if nhl.get("last_meeting"):
        m = nhl["last_meeting"]
        ot = " OT" if m["overtime"] else ""
        state = "offseason" if nhl.get("offseason") else "in season"
        print(f"\n  [NHL · {state}]")
        print(f"    · {m['away']} {m['away_score']} @ {m['home']} {m['home_score']}{ot} — {m['date']}")

    if issue.get("rotating"):
        r = issue["rotating"]
        days = f" — {r['days']} days" if r["days"] is not None else ""
        print(f"\n  [{r['label']}{days}]")
        for entry in r["entries"]:
            print(f"    · {entry['title']}")

    print("\n  [Mot du jour]")
    for card in issue["drill"]["cards"]:
        print(f"    · {card['fr']} — {card['en']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="espresso", description="Brew the Daily Espresso.")
    sub = parser.add_subparsers(dest="command", required=True)

    brew = sub.add_parser("brew", help="fetch, rank, render, and publish today's issue")
    brew.add_argument("--date", help="ISO date to build (default: today)")
    brew.add_argument("--out", help=f"output directory (default: {DOCS})")
    brew.add_argument("--dry-run", action="store_true", help="print the issue, write nothing")
    brew.add_argument(
        "--ignore-seen",
        action="store_true",
        help="do not suppress previously-published URLs, and do not record new ones",
    )
    brew.set_defaults(func=cmd_brew)

    drill = sub.add_parser("drill", help="print the French cards for a date")
    drill.add_argument("--date", help="ISO date (default: today)")
    drill.set_defaults(func=cmd_drill)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
