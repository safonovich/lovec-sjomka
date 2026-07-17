"""Общие модели данных."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Listing:
    platform: str                       # "youdo" | "profi"
    id: str
    title: str
    description: str = ""
    price: Optional[int] = None         # руб; None = бюджет не указан
    url: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.platform}:{self.id}"

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.description}".strip()


@dataclass
class Match:
    listing: Listing
    score: int                          # 0-10, оценка Claude (или 5 при fail-open)
    reason: str
    in_target_budget: bool              # попал в целевую вилку 20-50к
