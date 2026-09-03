"""Write an issue into docs/ and keep the archive index in sync."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Any

from .config import DOCS, SEEN_FILE, SEEN_RETENTION_DAYS, STATIC
from .render import render_archive, render_issue


def load_seen(path: Path | None = None) -> dict[str, str]:
    path = path or SEEN_FILE
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        print("  ! seen.json unreadable; starting fresh")
        return {}


def save_seen(seen: dict[str, str], today: dt.date, path: Path | None = None) -> None:
    """Persist seen URLs, forgetting anything past the retention window."""
    path = path or SEEN_FILE
    cutoff = (today - dt.timedelta(days=SEEN_RETENTION_DAYS)).isoformat()
    pruned = {url: day for url, day in seen.items() if day >= cutoff}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(dict(sorted(pruned.items())), fh, indent=0, sort_keys=True)


def copy_assets(out: Path) -> None:
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for src in STATIC.iterdir():
        if src.is_file():
            shutil.copy2(src, assets / src.name)


def issue_path(out: Path, day: dt.date) -> Path:
    return out / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}.html"


def _read_editions(out: Path) -> list[dict[str, Any]]:
    """Rebuild the archive list from the JSON snapshots on disk, so it stays
    correct even if a run is skipped or an old issue is backfilled."""
    editions = []
    for snapshot in sorted((out / "issues").glob("*.json"), reverse=True):
        try:
            with open(snapshot, encoding="utf-8") as fh:
                issue = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue
        day = dt.date.fromisoformat(issue["date"])
        editions.append(
            {
                "date": issue["date"],
                "date_long": issue.get("date_long", issue["date"]),
                "href": f"{day:%Y}/{day:%m}/{day:%d}.html",
                "counts": issue.get("counts", {}),
                "headline": next(
                    (
                        s["stories"][0]["title"]
                        for s in issue.get("sections", [])
                        if s.get("stories")
                    ),
                    "",
                ),
            }
        )
    return editions


def publish(issue: dict[str, Any], out: Path | None = None) -> dict[str, Path]:
    """Write index.html, the dated permalink, the JSON snapshot, and archive.html."""
    out = out or DOCS
    day = dt.date.fromisoformat(issue["date"])
    out.mkdir(parents=True, exist_ok=True)
    copy_assets(out)

    # JSON snapshot first: the archive index is rebuilt from these.
    snapshot = out / "issues" / f"{issue['date']}.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    with open(snapshot, "w", encoding="utf-8") as fh:
        json.dump(issue, fh, ensure_ascii=False, indent=2)

    dated = issue_path(out, day)
    dated.parent.mkdir(parents=True, exist_ok=True)
    dated.write_text(
        render_issue(issue, asset_prefix="../../assets", root_prefix="../../"),
        encoding="utf-8",
    )

    index = out / "index.html"
    index.write_text(
        render_issue(
            issue,
            asset_prefix="assets",
            permalink=f"{day:%Y}/{day:%m}/{day:%d}.html",
        ),
        encoding="utf-8",
    )

    archive = out / "archive.html"
    archive.write_text(
        render_archive(_read_editions(out), asset_prefix="assets"),
        encoding="utf-8",
    )

    return {"index": index, "dated": dated, "snapshot": snapshot, "archive": archive}
