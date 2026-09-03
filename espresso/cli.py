"""python -m espresso <command>"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from .archive import load_seen, publish, save_seen
from .config import DOCS, SECTIONS, load_sources
from .drill import drill_for
from .fetch import fetch_feed, fetch_kev
from .rank import canonical_url, rank
from .render import build_issue


def _gather(day: dt.date, now: dt.datetime, use_seen: bool):
    sources = load_sources()
    print(f"Fetching {len(sources)} source(s)…")

    items = []
    for source in sources:
        items.extend(fetch_feed(source, now))
    kev = fetch_kev(now)

    seen = load_seen() if use_seen else {}
    caps = {s.name: s.cap for s in sources if s.cap is not None}
    ranked = rank(items, now, seen, caps=caps)
    drill = drill_for(day)
    return build_issue(day, ranked, kev, drill, now), ranked, seen


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
    for section in issue["sections"]:
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
    print("\n  [French]")
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
