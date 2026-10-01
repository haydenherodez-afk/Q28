"""Zlati primeri, ki jih aplikacija požene v "Testnem načinu" (in ob vsaki spremembi pravil).
Pričakovane vrednosti so izračunane ročno / iz uradnih zneskov, ne iz engina."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .engine import Profile, YearInput, calculate_year, lestvica, monthly_contributions
from .rules import load_rules

FY = date(2026, 1, 1)

CASES = [
    # (id, opis, funkcija -> Decimal, pričakovano)
    ("norm_60k", "Normiranec polni, 60.000 € -> dohodnina 2.400 €",
     lambda: calculate_year(Profile(activity_start=FY), YearInput(2026, "60000")).value("dohodnina"), "2400.00"),
    ("norm_70k", "Normiranec polni, 70.000 € -> nad 60k ni odhodkov -> 4.400 €",
     lambda: calculate_year(Profile(activity_start=FY), YearInput(2026, "70000")).value("dohodnina"), "4400.00"),
    ("norm_90k", "Normiranec polni, 90.000 € -> 8.400 €",
     lambda: calculate_year(Profile(activity_start=FY), YearInput(2026, "90000")).value("dohodnina"), "8400.00"),
    ("norm_130k", "Normiranec polni, 130.000 € -> 72k×20 % + 10k×35 % = 17.900 €",
     lambda: calculate_year(Profile(activity_start=FY), YearInput(2026, "130000")).value("dohodnina"), "17900.00"),
    ("norm_partial_20k", "Normiranec < 9 mesecev, 20.000 € -> odhodki 13.000 €",
     lambda: calculate_year(Profile(activity_start=date(2026, 10, 1)), YearInput(2026, "20000")).value("normirani_odhodki"),
     "13000.00"),
    ("norm_partial_60k", "Normiranec < 9 mesecev, 60.000 € -> 6.600 + 10.000×35 % = 10.100 €",
     lambda: calculate_year(Profile(activity_start=date(2026, 10, 1)), YearInput(2026, "60000")).value("dohodnina"),
     "10100.00"),
    ("lestvica_30k", "Lestvica 2026: neto osnova 30.000 € -> 6.926,39 €",
     lambda: lestvica(Decimal("30000"), load_rules(2026))[0], "6926.39"),
    ("lestvica_100k", "Lestvica 2026: neto osnova 100.000 € -> 34.537,21 €",
     lambda: lestvica(Decimal("100000"), load_rules(2026))[0], "34537.21"),
    ("prisp_mar", "Minimalni prispevki marec 2026 = uradnih 651,04 €",
     lambda: monthly_contributions(Profile(activity_start=date(2026, 3, 1)), 2026)[0][0].total, "651.04"),
    ("prisp_feb", "Minimalni prispevki februar 2026 = uradnih 648,85 €",
     lambda: monthly_contributions(Profile(activity_start=date(2026, 2, 1)), 2026)[0][0].total, "648.85"),
    ("sprakt_60k", "Vloga DD-SprAkt 60.000 € -> akontacija 2.400 € (uradni dokument)",
     lambda: calculate_year(Profile(activity_start=FY), YearInput(2026, "60000")).value("akontacija_naslednje_leto"),
     "2400.00"),
]


def run() -> dict:
    results = []
    for cid, label, fn, expected in CASES:
        try:
            got = fn()
            ok = Decimal(str(got)) == Decimal(expected)
            results.append({"id": cid, "label": label, "expected": expected, "got": str(got), "passed": ok})
        except Exception as e:  # noqa: BLE001
            results.append({"id": cid, "label": label, "expected": expected, "got": None, "passed": False,
                            "error": str(e)})
    failed = [r for r in results if not r["passed"]]
    return {"total": len(results), "passed": len(results) - len(failed), "failed": len(failed), "results": results}
