"""DDV: obdobja, izstopni/vstopni DDV, obveznost in roki."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .money import ZERO, D, r2
from .rules import RuleSet, load_rules
from .trace import Explained
from .workdays import add_months, last_workday_of_month


@dataclass
class VatLine:
    day: date
    net: Decimal
    vat: Decimal
    direction: str            # "out" (izdani račun) | "in" (prejeti račun)
    deductible: bool = True   # vstopni DDV, ki ga lahko odbiješ


@dataclass
class VatPeriod:
    start: date
    end: date
    kind: str
    output_vat: Decimal
    input_vat: Decimal
    payable: Decimal
    due_date: date
    explain: Explained

    def to_dict(self, rules=None) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "kind": self.kind,
            "output_vat": str(r2(self.output_vat)),
            "input_vat": str(r2(self.input_vat)),
            "payable": str(r2(self.payable)),
            "due_date": self.due_date.isoformat(),
            "explain": self.explain.to_dict(rules),
        }


def is_monthly(registration: date, period_start: date, prev_year_turnover: Decimal, rules: RuleSet) -> bool:
    months = (period_start.year - registration.year) * 12 + (period_start.month - registration.month)
    if months < int(rules.p("ddv.obdobje", "new_taxpayer_monthly_months")):
        return True
    return D(prev_year_turnover) > D(rules.p("ddv.obdobje", "quarterly_max_turnover"))


def _month_end(y: int, m: int) -> date:
    ny, nm = add_months(y, m, 1)
    return date.fromordinal(date(ny, nm, 1).toordinal() - 1)


def periods_for_year(year: int, registration: date, prev_year_turnover: Decimal = ZERO) -> list[tuple[date, date, str]]:
    rules = load_rules(year)
    out = []
    month = 1
    while month <= 12:
        start = date(year, month, 1)
        if _month_end(year, month) < registration:
            month += 1
            continue
        if is_monthly(registration, start, prev_year_turnover, rules) or (month - 1) % 3 != 0:
            out.append((start, _month_end(year, month), "mesečno"))
            month += 1
        else:
            out.append((start, _month_end(year, month + 2), "trimesečno"))
            month += 3
    return out


def vat_periods(year: int, registration: date, lines: list[VatLine],
                prev_year_turnover: Decimal = ZERO) -> list[VatPeriod]:
    rules = load_rules(year)
    result = []
    for start, end, kind in periods_for_year(year, registration, prev_year_turnover):
        out_vat = sum((l.vat for l in lines if l.direction == "out" and start <= l.day <= end), ZERO)
        in_vat = sum((l.vat for l in lines if l.direction == "in" and l.deductible and start <= l.day <= end), ZERO)
        payable = r2(out_vat - in_vat)
        dy, dm = add_months(end.year, end.month, 1)
        due = last_workday_of_month(dy, dm)
        e = Explained("ddv", f"DDV {start.strftime('%m/%Y')}" + ("" if kind == "mesečno" else f"–{end.strftime('%m/%Y')}"),
                      payable, formula="izstopni DDV − odbitni vstopni DDV",
                      rule_ids=["ddv.stopnje", "ddv.obdobje"])
        e.step("Izstopni DDV (izdani računi)", out_vat).step("Vstopni DDV (prejeti računi)", -in_vat)
        e.step("Za plačilo" if payable >= 0 else "Presežek (vračilo / prenos)", payable)
        e.step("Rok za DDV-O in plačilo", None, due.isoformat())
        result.append(VatPeriod(start, end, kind, out_vat, in_vat, payable, due, e))
    return result
