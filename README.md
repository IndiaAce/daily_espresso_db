# Daily Espresso ☕

A small, fast morning newsletter that builds itself. Security headlines, the
CVEs that are actually being exploited right now, AI/ML news, and three French
cards — one static page, published every morning to GitHub Pages.

**Live:** https://indiaace.github.io/daily_espresso_db/

No LLM, no API keys, no server. A GitHub Action fetches a list of RSS feeds and
the CISA KEV catalog, ranks what it finds, renders HTML, and commits it.

## How it works

```
data/sources.toml  →  fetch  →  rank  →  render  →  docs/
```

| Stage | Module | What it does |
| --- | --- | --- |
| Fetch | `espresso/fetch.py` | Pulls each feed and the CISA KEV catalog. Every fetcher swallows its own errors and returns `[]` — one dead source must never cost a morning issue. |
| Rank | `espresso/rank.py` | Drops URLs already published, dedupes near-identical headlines across sources, scores by `source weight × recency decay` (halves every 36h), then applies per-source caps. |
| Drill | `espresso/drill.py` | Picks the day's French cards from `sha256(date)`, so the same day always yields the same cards. |
| Render | `espresso/render.py` | Jinja2 → HTML. |
| Publish | `espresso/archive.py` | Writes `index.html`, the dated permalink, a JSON snapshot, and rebuilds `archive.html`. |

Output layout:

```
docs/
  index.html              today (overwritten each morning)
  archive.html            every edition, newest first
  2026/09/03.html         permanent dated issues
  issues/2026-09-03.json  machine-readable snapshot — the archive is rebuilt from these
  assets/                 copied from static/
```

## Local use

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m espresso brew --dry-run     # print the issue, write nothing
python -m espresso brew               # build into docs/
python -m espresso drill              # just today's French cards
open docs/index.html
```

Useful flags:

- `--date 2026-09-01` — build a specific date (the French cards are pinned to it)
- `--out /tmp/preview` — write somewhere other than `docs/`
- `--ignore-seen` — don't suppress previously-published URLs, and don't record new ones.
  Use this for any throwaway build, or it will poison tomorrow's issue.

## Tuning what shows up

Everything lives in [`data/sources.toml`](data/sources.toml) — no code changes needed.

```toml
[[source]]
name    = "Krebs on Security"
url     = "https://krebsonsecurity.com/feed/"
section = "security"   # security | ai
weight  = 1.5          # multiplier on the recency score; 1.0 is neutral
cap     = 2            # optional per-source ceiling within its section
```

Section sizes, the staleness cutoff, and the KEV window are in
[`espresso/config.py`](espresso/config.py) (`SECTION_LIMITS`, `MAX_AGE_DAYS`,
`KEV_WINDOW_DAYS`).

**Note:** Anthropic publishes no RSS feed (both `anthropic.com/rss.xml` and
`/news/rss.xml` 404), which is why it isn't in the AI section.

## State

- `data/seen.json` — URL → first-seen date, so a story never appears twice.
  Pruned after 90 days (`SEEN_RETENTION_DAYS`). Committed by the Action.
- `data/french.json` — 2,708 FR/EN cards, a one-time snapshot parsed out of
  `fun-flash-cards/words.txt`. Not a live dependency on that repo.

## Deployment

GitHub Pages, *Deploy from a branch* → `main` / `/docs`. `docs/` is committed on
purpose: it's the published artifact, and it stays diffable next to the code
that produced it.

`.github/workflows/brew.yml` runs daily and commits only when something changed.
GitHub disables cron on repos with no activity for 60 days — the daily commit
keeps it alive on its own.

## Design

`templates/` and `static/espresso.css` currently carry the "Signal" palette from
lukewescott.com as a placeholder. They're the only files that need to change to
adopt the Claude Design `Daily Espresso.dc.html` layout — the pipeline hands the
template one `issue` dict and doesn't care what it looks like.
