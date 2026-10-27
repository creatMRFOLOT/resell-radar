from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Listing:
    """Объявление из выдачи."""
    id: str
    title: str
    price: int
    url: str
    snippet: str = ""        # краткое описание из карточки, если оно есть
    city: str = ""
    published: str = ""


@dataclass
class ItemPage:
    """Что известно со страницы самого объявления."""
    title: str = ""
    description: str = ""
    params: dict[str, str] = field(default_factory=dict)
    published: str = ""
    total_views: int | None = None
    today_views: int | None = None
