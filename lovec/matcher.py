"""Префильтр до Claude: стоп-слова → порог цены → ключи.
Кандидат = не отсечён и (хит по ключам ИЛИ цена >= budget_min)."""

from __future__ import annotations

from lovec.models import Listing


def _hit(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)


def prefilter(listing: Listing, cfg: dict) -> bool:
    f = cfg["filter"]
    text = listing.text.lower()
    if _hit(text, f.get("stop", [])):
        return False
    price = listing.price
    if price is not None and price < f["budget_min"]:
        return False
    return _hit(text, f.get("keywords", [])) or (price is not None and price >= f["budget_min"])


def in_target(listing: Listing, cfg: dict) -> bool:
    f = cfg["filter"]
    p = listing.price
    return p is not None and f["target_min"] <= p <= f["target_max"]
