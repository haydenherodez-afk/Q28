"""Denar: vedno Decimal, zaokroževanje na cent (half-up), nikoli float."""
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def D(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return ZERO
    if isinstance(value, float):
        # float -> str prepreči binarne artefakte (0.1 + 0.2)
        return Decimal(repr(value))
    return Decimal(str(value))


def r2(value) -> Decimal:
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_eur(value) -> str:
    """1234.5 -> '1.234,50 €' (slovenski zapis)."""
    q = r2(value)
    sign = "-" if q < 0 else ""
    whole, frac = f"{abs(q):.2f}".split(".")
    groups = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    return f"{sign}{'.'.join(groups)},{frac} €"
