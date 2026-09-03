"""The daily French card.

Deterministic by date: the same day always yields the same card, so a re-run
or a rebuild never rewrites a published issue.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from .config import FRENCH_FILE


def load_corpus(path: Path | None = None) -> list[dict[str, str]]:
    with open(path or FRENCH_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def _pick(corpus: list[dict[str, str]], day: dt.date, salt: str = "") -> dict[str, str]:
    digest = hashlib.sha256(f"{day.isoformat()}{salt}".encode()).digest()
    return corpus[int.from_bytes(digest[:8], "big") % len(corpus)]


def drill_for(day: dt.date, corpus: list[dict[str, str]] | None = None, count: int = 3) -> dict[str, Any]:
    """Pick `count` distinct cards for `day`, plus which one to quiz on."""
    corpus = corpus if corpus is not None else load_corpus()
    if not corpus:
        return {"cards": [], "quiz": None}

    cards: list[dict[str, str]] = []
    salt = 0
    # Re-salt on collision rather than walking the list, so neighbouring
    # alphabetical entries never appear together.
    while len(cards) < min(count, len(corpus)) and salt < count * 20:
        card = _pick(corpus, day, salt=str(salt))
        if card not in cards:
            cards.append(card)
        salt += 1

    return {"cards": cards, "quiz": cards[0] if cards else None}
