"""Decide whether a product is Pokemon TCG, what kind it is, and whether it's at MSRP."""
from __future__ import annotations

import unicodedata


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


TCG_WORDS = [
    "trading card", "tcg", "booster", "elite trainer", "etb", "collection",
    "tin", "premium", "bundle", "blister", "build & battle", "build and battle",
    "card game", "pack", "binder collection", "surprise box", "display",
]
EXCLUDE_WORDS = [
    "plush", "nintendo switch", "video game", "funko", "lego", "costume",
    "t-shirt", "shirt", "hoodie", "backpack", "lunch", "figure", "mega construx",
    "sleeves", "deck box", "playmat", "binder only", "portfolio", "toploader",
    "puzzle", "book", "sticker", "squishmallow", "pajama", "blanket",
]

# (category, keywords) checked in order; first match wins
CATEGORIES = [
    ("Elite Trainer Box", ["elite trainer", " etb"]),
    ("Booster Bundle", ["booster bundle"]),
    ("Booster Box", ["booster box", "booster display"]),
    ("Premium Collection", ["premium collection", "ultra premium", "super premium"]),
    ("Tin", [" tin", "tin "]),
    ("Collection Box", ["collection", "box"]),
    ("Booster Pack", ["booster pack", "blister", "sleeved booster", "booster"]),
]


def is_pokemon_tcg(name: str) -> bool:
    n = _norm(name)
    if "pokemon" not in n:
        return False
    if any(w in n for w in EXCLUDE_WORDS):
        return False
    return any(w in n for w in TCG_WORDS)


def category(name: str) -> str:
    n = " " + _norm(name) + " "
    for cat, words in CATEGORIES:
        if any(w in n for w in words):
            return cat
    return "Other TCG"


def is_priority(name: str, priority_categories: list[str]) -> bool:
    n = _norm(name)
    if "30th" in n or "anniversary" in n:
        return True
    return category(name) in priority_categories


def at_msrp(name: str, price: float | None, msrp_table: dict, tolerance: float) -> bool | None:
    """True/False if we know the MSRP for this category, None if we don't."""
    if price is None:
        return None
    msrp = msrp_table.get(category(name))
    if not msrp:
        return None
    return price <= float(msrp) * (1 + tolerance)
