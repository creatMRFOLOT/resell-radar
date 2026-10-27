"""Сборка и подготовка поисковых ссылок Avito."""
from __future__ import annotations

from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

# Значение параметра user в ссылках Avito: 1 = частные лица, 2 = компании.
# Если сомневаетесь, выставьте фильтр на самом Avito и вставьте получившуюся ссылку:
# параметры из неё программа не переопределяет.
SELLER_PARAM = {"private": "1", "company": "2"}


def is_avito_url(url: str) -> bool:
    parts = urlsplit((url or "").strip())
    host = parts.netloc.lower()
    return parts.scheme in ("http", "https") and (host == "avito.ru" or host.endswith(".avito.ru"))


def query_from_url(url: str) -> str:
    return dict(parse_qsl(urlsplit(url).query)).get("q", "")


def build_search_url(region: str, category: str, query: str, min_price: int = 0) -> str:
    # pmax не ставим: для оценки рынка нужны все цены, а не только дешёвые.
    path = f"/{region}/{category}" if category else f"/{region}"
    return f"https://www.avito.ru{path}?q={quote_plus(query)}&s=104&pmin={min_price}"


def prepare_url(url: str, seller: str = "any") -> str:
    """Ссылка пользователя -> ссылка для мониторинга.

    * сортировка «по дате», если пользователь не выбрал свою;
    * pmax убирается: иначе рынок оценивается только по дешёвым объявлениям;
    * тип продавца добавляется, только если пользователь не задал его сам.
    """
    parts = urlsplit(url.strip())
    params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "pmax"]
    keys = {k for k, _ in params}
    if "s" not in keys:
        params.append(("s", "104"))
    if "user" not in keys and seller in SELLER_PARAM:
        params.append(("user", SELLER_PARAM[seller]))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), ""))
