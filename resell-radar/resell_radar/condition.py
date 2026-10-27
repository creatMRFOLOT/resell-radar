"""Оценка состояния устройства по тексту объявления.

Из текста достаются найденные дефекты по категориям (экран, плата, аккумулятор...).
Дальше решается, подходит ли объявление пользователю: он сам при настройке
выбрал, что умеет чинить (`repairable`). Пустой список = нужны только целые.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

I = re.IGNORECASE

# Категории дефектов, которые пользователь может согласиться чинить.
REPAIR_KEYS = ("screen", "back_glass", "battery", "board", "water", "locked")

PATTERNS: dict[str, re.Pattern] = {
    "locked": re.compile(
        r"icloud|айклауд|аклауд|apple\s?id|\bfrp\b|google\s?(?:аккаунт|account)|"
        r"гугл\s?аккаунт|заблокирован\w*|блокировк\w*|\bmdm\b|привязан\w*\s+к\s+(?:аккаунт|id|облак)", I),
    "parts": re.compile(
        r"на\s+запчаст\w*|под\s+разбор|на\s+разбор|донор|для\s+ремонт\w*|на\s+ремонт|"
        r"под\s+восстановл\w*|нерабоч\w*|не\s+рабоч\w*", I),
    "water": re.compile(r"залит\w*|после\s+воды|утоплен\w*|влаг\w*|окислен\w*|вода\s+попала", I),
    "screen": re.compile(
        r"(?:разбит\w*|треснут\w*|треснул\w*|трещин\w*|скол\w*)[^.,;\n]{0,25}(?:экран\w*|дисплей\w*)|"
        r"(?:экран\w*|дисплей\w*)[^.,;\n]{0,25}(?:разбит\w*|треснут\w*|треснул\w*|трещин\w*|скол\w*|"
        r"не\s+работа\w*|мерцает|полос\w*|пятн\w*|выгор\w*|битые?|артефакт\w*|зеленит|розовит)|"
        r"полос[аыу]\b|битые?\s+пиксел\w*|выгорани\w*", I),
    "back_glass": re.compile(
        r"(?:разбит\w*|треснут\w*|треснул\w*|трещин\w*|скол\w*)[^.,;\n]{0,20}"
        r"(?:задн\w*|крышк\w*|панел\w*)|"
        r"задн\w*\s+(?:стекл\w*|крышк\w*|панел\w*)[^.,;\n]{0,20}"
        r"(?:разбит\w*|треснут\w*|трещин\w*|скол\w*)", I),
    "battery": re.compile(
        r"быстро\s+(?:разряж|садит)\w*|не\s+держит\s+(?:заряд|батаре)\w*|вздут\w*|"
        r"(?:акб|аккумулятор\w*|батаре\w+)[^.,;\n]{0,15}(?:износ\w*|слаб\w*|плох\w*|сел\w*)|"
        r"износ\w*\s+(?:акб|аккумулятор\w*|батаре\w+)|"
        r"требует\s+замен\w+\s+(?:акб|аккумулятор\w*|батаре\w+)", I),
    "board": re.compile(
        r"не\s+включа\w*|не\s+заряжа\w*|не\s+загружа\w*|бутлуп|bootloop|перезагруж\w*|"
        r"самопроизвольн\w*|зависа\w*|глюч\w*|вылета\w*|кирпич\w*|не\s+ловит\w*|"
        r"нет\s+(?:сети|связи|звука|изображени\w*)|не\s+видит\s+сим\w*|"
        r"не\s+работа\w*\s+(?:камер\w*|динамик\w*|микрофон\w*|wi-?fi|вай-?фай|блютуз|bluetooth|nfc|"
        r"face\s?id|отпечат\w*|сим\w*|зарядк\w*|кнопк\w*|стик\w*)|"
        r"(?:камер\w*|динамик\w*|микрофон\w*|wi-?fi|вай-?фай|face\s?id|nfc)\s+не\s+работа\w*|"
        r"дрейф\w*|дрифт\w*|сильно\s+греется|греется\s+(?:сильно|при)|"
        r"плата\s+(?:мертв\w*|умерл\w*)", I),
    # Подделки отбрасываются всегда.
    "fake": re.compile(r"копия|реплика|муляж|подделк\w*|не\s+оригинал\w*|китайск\w+\s+копи\w*|1\s?:\s?1|1\s?в\s?1", I),
    # Мелочи и следы вмешательства: не отбрасывают, но повышают риск.
    "soft": re.compile(r"царапин\w*|потертост\w*|потёртост\w*|потерт\w*|потёрт\w*|скол\w*|вмятин\w*|"
                       r"следы\s+использован\w*", I),
    "replaced": re.compile(
        r"замен\w+\s+(?:экран\w*|дисплея|аккумулятор\w*|акб|стекл\w*|корпус\w*)|"
        r"менял\w*\s+(?:экран|дисплей|акб|аккумулятор)|вскрывал\w*|ремонтировал\w*|"
        r"был\s+в\s+ремонте|после\s+ремонта", I),
}

# Слова-отрицания перед или после найденного слова: "без трещин", "трещин нет", "не греется".
NEG_BEFORE = ("не ", "без ", "нет ", "ни ", "никаких ", "отсутств", "никогда ")
NEG_AFTER = re.compile(r"\b(?:нет|не\s+был\w*|не\s+имеет|отсутств\w*|не\s+вскрыв\w*|нету)", I)
# Внутри совпадения: "экран без трещин", "экран: трещин нет".
NEG_INSIDE = re.compile(r"\b(?:без|нет|нету)\b", I)
# Категории, где слово «не» входит в сам дефект ("не включается"), поэтому внутреннее
# отрицание для них не проверяется.
NO_INSIDE_NEG = {"board", "parts", "battery", "fake", "locked"}

BATTERY_RE = re.compile(
    r"(?:акб|аккумулятор\w*|батаре\w+|емкост\w+|ёмкост\w+)[^\d\n]{0,20}(\d{2,3})\s?%", I)
LOW_BATTERY_PCT = 75


@dataclass
class Condition:
    findings: dict[str, list[str]] = field(default_factory=dict)
    battery_pct: int | None = None

    @property
    def defects(self) -> set[str]:
        """Категории дефектов (то, что пользователь может согласиться чинить)."""
        found = {k for k in REPAIR_KEYS if self.findings.get(k)}
        if self.findings.get("parts"):
            found.add("board")  # «на запчасти» без подробностей считаем серьёзной поломкой
        if self.battery_pct is not None and self.battery_pct < LOW_BATTERY_PCT:
            found.add("battery")
        return found

    @property
    def is_fake(self) -> bool:
        return bool(self.findings.get("fake"))

    @property
    def soft(self) -> bool:
        return bool(self.findings.get("soft"))

    @property
    def replaced(self) -> bool:
        return bool(self.findings.get("replaced"))


def find_battery(text: str) -> int | None:
    m = BATTERY_RE.search(text)
    if m and 40 <= int(m.group(1)) <= 100:
        return int(m.group(1))
    return None


def analyze(text: str) -> Condition:
    t = (text or "").lower()
    cond = Condition(battery_pct=find_battery(t))
    for cat, pattern in PATTERNS.items():
        for m in pattern.finditer(t):
            before = t[max(0, m.start() - 14):m.start()]
            after = t[m.end():m.end() + 14]
            if any(neg in before for neg in NEG_BEFORE):
                continue
            if NEG_AFTER.search(after):
                continue
            if cat not in NO_INSIDE_NEG and NEG_INSIDE.search(m.group(0)):
                continue
            cond.findings.setdefault(cat, []).append(m.group(0).strip())
    return cond


@dataclass
class Decision:
    accepted: bool
    reasons: list[str] = field(default_factory=list)   # почему отказали
    repair_cost: int = 0
    repairs: list[str] = field(default_factory=list)   # что придётся чинить


def decide(cond: Condition, repairable: list[str], repair_costs: dict[str, int]) -> Decision:
    """Подходит ли объявление пользователю с таким набором навыков."""
    if cond.is_fake:
        return Decision(False, ["похоже на подделку"])
    defects = cond.defects
    allowed = set(repairable)
    missing = sorted(defects - allowed)
    if missing:
        return Decision(False, [f"дефект: {d}" for d in missing])
    cost = sum(int(repair_costs.get(d, 0)) for d in defects)
    return Decision(True, repair_cost=cost, repairs=sorted(defects))
