# Daily Espresso ☕

A one-page morning newsletter that builds itself. Email-security news, the CVEs
actually being exploited right now, AI/ML research, France & Europe, the Bruins
and the Canadiens, today's weather, and a French word — published every morning
to GitHub Pages.

**Live:** https://indiaace.github.io/daily_espresso_db/

No LLM, no API keys, no server. A GitHub Action fetches a list of feeds and
three public APIs, ranks what it finds, renders HTML, and commits it.

## How it works

```
data/sources.toml  →  fetch  →  rank  →  render  →  docs/
```

| Stage | Module | What it does |
| --- | --- | --- |
| Fetch | `espresso/fetch.py` | Feeds, plus CISA KEV, Open-Meteo, and the NHL API. Every fetcher swallows its own errors and returns empty — one dead source must never cost a morning issue. |
| Rank | `espresso/rank.py` | Drops URLs already published, dedupes near-identical headlines across sources, scores by `source weight × recency decay` (halves every 36h), applies per-source caps, and filters out webinar/sponsored noise. |
| Drill | `espresso/drill.py` | Picks the day's French cards from `sha256(date)`, so the same day always yields the same word. |
| Render | `espresso/render.py` | Jinja2 → HTML. |
| Publish | `espresso/archive.py` | Writes `index.html`, the dated permalink, a JSON snapshot, and rebuilds `archive.html`. |

Output layout:

```
docs/
  index.html              today (overwritten each morning)
  archive.html            every edition, newest first
  2026/09/03.html         permanent dated issues
  issues/2026-09-03.json  machine-readable snapshot — the archive is rebuilt from these
  assets/espresso.css
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

## Tuning it

Everything editable lives in [`data/sources.toml`](data/sources.toml).

**Feeds.** `section` is one of `email_security`, `ai`, `france`, `nhl`.

```toml
[[source]]
name    = "Krebs on Security"
url     = "https://krebsonsecurity.com/feed/"
section = "email_security"
weight  = 1.4          # multiplier on the recency score; 1.0 is neutral
cap     = 2            # optional per-source ceiling within its section
require = ["phish", "bec", "spoof"]   # optional — see below
```

`require` is how a broad security feed contributes to a narrow section: an item
only qualifies if its title or summary mentions one of the keywords. That's what
keeps the Email Security panel on the email beat without needing email-only
sources, which barely exist.

**The rotating slot** is the dark panel. Set `enabled = false` to collapse it, or
rewrite the label, countdown and entries whenever the obsession changes:

```toml
[rotating]
enabled = true
label = "Currently Obsessed / GTA VI"
countdown_date = "2026-11-19"
```

**Weather** takes any number of `[[weather.place]]` blocks (Open-Meteo, no key).
**The NHL panel** takes a `home` and `rival` team code and finds their last
head-to-head — falling back to last season through the summer, so the box still
has a score to show in the offseason.

Section sizes and the staleness cutoff are in
[`espresso/config.py`](espresso/config.py) (`SECTION_LIMITS`, `MAX_AGE_DAYS`,
`KEV_WINDOW_DAYS`).

**Sources that don't work, and why:** Anthropic publishes no RSS feed (both
`anthropic.com/rss.xml` and `/news/rss.xml` 404). NHL.com's own feed returns 200
but serves malformed XML. Sublime Security's blog rate-limits automated fetches.

## State

- `data/seen.json` — URL → first-seen date, so a story never appears twice.
  Pruned after 90 days. Committed by the Action. A date's own picks don't
  suppress themselves, so rebuilding today reproduces today rather than
  republishing the runners-up.
- `data/french.json` — 2,708 FR/EN cards, a one-time snapshot parsed out of
  `fun-flash-cards/words.txt`. Not a live dependency on that repo.

## Deployment

GitHub Pages, *Deploy from a branch* → `main` / `/docs`. `docs/` is committed on
purpose: it's the published artifact, and it stays diffable next to the code that
produced it.

`.github/workflows/brew.yml` runs daily at 11:00 UTC and commits only when
something changed. GitHub disables cron on repos with no activity for 60 days —
the daily commit keeps it alive on its own.

## Design

The visual system comes from `Daily Espresso.dc.html` in Claude Design — warm
paper, Instrument Serif headlines, IBM Plex Mono labels, a rust accent, and one
dark panel. It deliberately commits to a single light look, so there is no dark
variant. `templates/` and `static/espresso.css` are the only files that carry it;
the pipeline hands the template one `issue` dict and doesn't care how it looks.
