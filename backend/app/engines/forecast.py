"""Forecast Engine: napoved letnih prihodkov v scenarijih + ponovni davčni izračun za vsakega."""
from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from ..tax_engine import YearInput, calculate_year, fmt_eur
from ..tax_engine.engine import insured_fractions
from ..tax_engine.money import ZERO, D, r2
from .ledger import Ledger


def _elapsed_and_remaining(L: Ledger) -> tuple[Decimal, Decimal, list[int]]:
    """Aktivni meseci do danes (delni po dnevih) in preostali do konca leta."""
    fr = insured_fractions(L.profile, L.year)
    elapsed = ZERO
    remaining = ZERO
    complete = []
    for m, f in fr.items():
        days = calendar.monthrange(L.year, m)[1]
        m_start, m_end = date(L.year, m, 1), date(L.year, m, days)
        if m_end <= L.as_of:
            elapsed += f
            complete.append(m)
        elif m_start > L.as_of:
            remaining += f
        else:
            passed = D((L.as_of - m_start).days + 1) / D(days)
            done = min(f, passed)
            elapsed += done
            remaining += f - done
    return elapsed, remaining, complete


def _trend(series: list[tuple[int, Decimal]]) -> Decimal:
    """Naklon linearne regresije (€/mesec na mesec)."""
    n = len(series)
    if n < 3:
        return ZERO
    xs = [D(x) for x, _ in series]
    ys = [y for _, y in series]
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return ZERO
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def build(L: Ledger, manual_target: Decimal | None = None) -> dict:
    revenue = L.revenue_ytd
    expenses = L.expenses_ytd
    elapsed, remaining, complete = _elapsed_and_remaining(L)
    monthly = L.monthly_revenue()
    series = [(m, monthly.get(m, ZERO)) for m in complete]

    avg = (revenue / elapsed) if elapsed > 0 else ZERO
    last3 = [v for _, v in series[-3:]]
    avg_last3 = (sum(last3) / len(last3)) if last3 else avg
    slope = _trend(series)
    exp_ratio = (expenses / revenue) if revenue > 0 else ZERO

    low_rate = min(avg, avg_last3) * D("0.85")
    high_rate = max(avg * D("1.10"), avg_last3 + slope * (remaining / 2 if remaining else 0))
    scenarios = {
        "LOW": ("Konservativno", revenue + low_rate * remaining,
                f"preostanek po {fmt_eur(low_rate)}/mesec (nižje od povprečij × 0,85)"),
        "CURRENT": ("Trenutno povprečje", revenue + avg * remaining,
                    f"preostanek po povprečju {fmt_eur(avg)}/mesec"),
        "HIGH": ("Rast", revenue + high_rate * remaining,
                 f"preostanek po {fmt_eur(high_rate)}/mesec (trend {fmt_eur(slope)}/mesec)"),
    }
    target = manual_target if manual_target is not None else (D(L.bp.revenue_goal) if L.bp.revenue_goal else None)
    if target:
        scenarios["TARGET"] = ("Ročni cilj", max(D(target), revenue), "tvoj letni cilj")

    out = []
    for key, (label, annual, how) in scenarios.items():
        annual = r2(annual)
        annual_exp = r2(expenses + (annual - revenue) * exp_ratio)
        res = calculate_year(L.profile, YearInput(L.year, annual, annual_exp))
        out.append({
            "key": key, "label": label, "how": how,
            "revenue": str(annual), "expenses": str(annual_exp),
            "prispevki": str(res.value("prispevki")),
            "dohodnina": str(res.value("dohodnina")),
            "drzavi_skupaj": str(res.value("drzavi_skupaj")),
            "neto": str(res.value("neto")),
            "akontacija_naslednje_leto": str(res.value("akontacija_naslednje_leto")),
            "scheme": res.scheme,
            "warnings": res.warnings,
        })
    return {
        "year": L.year,
        "as_of": L.as_of.isoformat(),
        "revenue_ytd": str(revenue),
        "elapsed_months": str(elapsed.quantize(Decimal("0.01"))),
        "remaining_months": str(remaining.quantize(Decimal("0.01"))),
        "monthly": [{"month": m, "revenue": str(r2(monthly.get(m, ZERO)))} for m in range(1, 13)],
        "avg_month": str(r2(avg)),
        "trend_per_month": str(r2(slope)),
        "scenarios": out,
        "note": "Napoved je statistična ocena; davki v vsakem scenariju so izračunani z istim davčnim enginom.",
    }
