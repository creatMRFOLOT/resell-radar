"""Оценка рынка: цены считаются по группам «модель + объём памяти».

Смешивать S22 128 ГБ и S22 256 ГБ нельзя: медиана получается ничьей.
Из выборки выбрасываются цены, слишком далёкие от медианы: это обычно битые
устройства, запчасти, мошенники или опечатки в цене.
"""
from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

VALID_STORAGE = (32, 64, 128, 256, 512, 1024)
OUTLIER_LOW = 0.5
OUTLIER_HIGH = 1.8

_PAIR = re.compile(r"(\d{1,2})\s*/\s*(\d{2,4})\s*(?:гб|gb|g\b)?", re.I)
_SINGLE = re.compile(r"(\d{1,4})\s*(гб|gb|тб|tb)\b", re.I)


def storage_gb(text: str) -> int | None:
    """Достаёт объём встроенной памяти: '8/128 ГБ' -> 128, '1 ТБ' -> 1024."""
    t = (text or "").lower()
    for ram, rom in _PAIR.findall(t):
        if int(rom) in VALID_STORAGE:
            return int(rom)
    best = None
    for num, unit in _SINGLE.findall(t):
        value = int(num) * (1024 if unit in ("тб", "tb") else 1)
        if value in VALID_STORAGE and (best is None or value > best):
            best = value
    return best


ALL = "все"   # вся модель одной группой (для устройств без вариантов, например наушников)


def _label(variant: int | str | None) -> str | None:
    if variant is None or variant == "":
        return None
    return f"{variant} ГБ" if isinstance(variant, int) else str(variant)


def variant_label(mode: str, text: str) -> str | None:
    """Название группы внутри модели: объём памяти, вся модель или вариант из регулярки.

    mode: "storage", "none" или регулярка (первая скобка = название варианта).
    None, если вариант определить не удалось.
    """
    if mode == "storage":
        gb = storage_gb(text)
        return _label(gb) if gb else None
    if mode in ("none", ""):
        return ALL
    try:
        m = re.search(mode, text or "", re.I)
    except re.error:
        return None
    if not m:
        return None
    return (m.group(1) if m.groups() and m.group(1) else m.group(0)).strip().lower()


def group_key(item_name: str, variant: int | str | None) -> str:
    label = _label(variant)
    return f"{item_name} | {label}" if label else f"{item_name} | ?"


@dataclass(frozen=True)
class Stats:
    group: str
    count: int          # сколько цен всего видели
    used: int           # сколько вошло в расчёт после отсева выбросов
    low: int
    q1: int
    median: int
    q3: int
    high: int
    approx: bool = False   # True: памяти нет, считали по всей модели


def trimmed_stats(group: str, prices: list[int], min_size: int = 3) -> Stats | None:
    if len(prices) < min_size:
        return None
    raw = statistics.median(prices)
    kept = sorted(p for p in prices if OUTLIER_LOW * raw <= p <= OUTLIER_HIGH * raw)
    if len(kept) < min_size:
        return None
    q1, median, q3 = statistics.quantiles(kept, n=4)
    return Stats(group, len(prices), len(kept), kept[0], round(q1), round(median),
                 round(q3), kept[-1])


class MarketBook:
    """Копит цены объявлений между запусками, чтобы оценка рынка была устойчивее."""

    def __init__(self, path: Path | None = None, window_days: int = 14, min_size: int = 3):
        self.path = Path(path) if path else None
        self.window = timedelta(days=window_days)
        self.min_size = min_size
        self.data: dict[str, dict[str, list]] = {}
        if self.path and self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.data = {}

    def observe(self, group: str, listing_id: str, price: int, now: datetime | None = None):
        now = now or datetime.now()
        self.data.setdefault(group, {})[listing_id] = [int(price), now.isoformat(timespec="seconds")]

    def _prices(self, group: str, now: datetime) -> list[int]:
        border = now - self.window
        return [p for p, ts in self.data.get(group, {}).values()
                if datetime.fromisoformat(ts) >= border]

    def stats(self, item_name: str, variant: int | str | None, now: datetime | None = None) -> Stats | None:
        now = now or datetime.now()
        label = _label(variant)
        if label:
            key = group_key(item_name, label)
            st = trimmed_stats(key, self._prices(key, now), self.min_size)
            if st:
                return st
            if label == ALL:      # вся модель и есть группа, запасного варианта нет
                return None
        # Запасной вариант: вся модель без разбивки на варианты (грубее).
        prefix = f"{item_name} | "
        prices: list[int] = []
        for g in self.data:
            if g.startswith(prefix):
                prices += self._prices(g, now)
        st = trimmed_stats(f"{item_name} | все", prices, self.min_size)
        if st:
            return Stats(st.group, st.count, st.used, st.low, st.q1, st.median, st.q3, st.high, True)
        return None

    def prune(self, now: datetime | None = None):
        now = now or datetime.now()
        border = now - self.window
        for group in list(self.data):
            self.data[group] = {i: v for i, v in self.data[group].items()
                                if datetime.fromisoformat(v[1]) >= border}
            if not self.data[group]:
                del self.data[group]

    def save(self):
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
