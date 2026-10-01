"""Slovenski dela prosti dnevi in premik rokov (ZDavP-2: rok, ki pade na dela prost dan,
se izteče naslednji delovni dan)."""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from functools import lru_cache


def _easter(year: int) -> date:
    # Anonymous Gregorian algorithm
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


@lru_cache(maxsize=32)
def holidays(year: int) -> frozenset[date]:
    easter = _easter(year)
    fixed = [
        (1, 1), (1, 2),   # novo leto
        (2, 8),           # Prešernov dan
        (4, 27),          # dan upora proti okupatorju
        (5, 1), (5, 2),   # praznik dela
        (6, 25),          # dan državnosti
        (8, 15),          # Marijino vnebovzetje
        (10, 31),         # dan reformacije
        (11, 1),          # dan spomina na mrtve
        (12, 25),         # božič
        (12, 26),         # dan samostojnosti in enotnosti
    ]
    days = {date(year, m, d) for m, d in fixed}
    days.add(easter)                       # velika noč
    days.add(easter + timedelta(days=1))   # velikonočni ponedeljek
    days.add(easter + timedelta(days=49))  # binkošti
    return frozenset(days)


def is_workday(day: date) -> bool:
    return day.weekday() < 5 and day not in holidays(day.year)


def next_workday(day: date) -> date:
    while not is_workday(day):
        day += timedelta(days=1)
    return day


def last_workday_of_month(year: int, month: int) -> date:
    day = date(year, month, calendar.monthrange(year, month)[1])
    while not is_workday(day):
        day -= timedelta(days=1)
    return day


def add_months(year: int, month: int, n: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + n
    return idx // 12, idx % 12 + 1


def due_on_day(year: int, month: int, day: int) -> date:
    """Rok 'do N. v mesecu' -> premaknjen na naslednji delovni dan."""
    last = calendar.monthrange(year, month)[1]
    return next_workday(date(year, month, min(day, last)))
