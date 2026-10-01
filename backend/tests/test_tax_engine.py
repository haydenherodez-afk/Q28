"""ZLATI TESTI davčnega engina (Testni način).

Vsaka pričakovana vrednost je izračunana ROČNO iz zakona/uradnih zneskov, ne iz
engina. Če kdo (človek ali AI) spremeni formulo ali pravilo in se rezultat
spremeni, test pade -> nobena tiha sprememba davčnega kalkulatorja.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.tax_engine import Profile, YearInput, calculate_year, load_rules, monthly_contributions, what_if
from app.tax_engine.engine import lestvica, olajsava_otroci, splosna_olajsava
from app.tax_engine.rules import RuleError
from app.tax_engine.vat import VatLine, periods_for_year, vat_periods
from app.tax_engine.workdays import due_on_day, is_workday, last_workday_of_month

R = load_rules(2026)
FULL_YEAR = date(2026, 1, 1)


def norm(**kw):
    return Profile(regime="normiran", activity_start=FULL_YEAR, **kw)


def dej(**kw):
    return Profile(regime="dejanski", activity_start=FULL_YEAR, **kw)


# ------------------------------------------------------------------ normiranci 2026
@pytest.mark.parametrize("revenue, odhodki, osnova, davek", [
    ("60000", "48000.00", "12000.00", "2400.00"),     # 80 % do 60k, 20 %
    ("70000", "48000.00", "22000.00", "4400.00"),     # nad 60k ni odhodkov
    ("90000", "48000.00", "42000.00", "8400.00"),
    ("120000", "48000.00", "72000.00", "14400.00"),   # meja 20 % stopnje
    ("130000", "48000.00", "82000.00", "17900.00"),   # 72k*20% + 10k*35%
    ("0", "0.00", "0.00", "0.00"),
])
def test_normiran_full(revenue, odhodki, osnova, davek):
    res = calculate_year(norm(), YearInput(2026, revenue))
    assert res.scheme == "full"
    assert res.value("normirani_odhodki") == Decimal(odhodki)
    assert res.value("davcna_osnova") == Decimal(osnova)
    assert res.value("dohodnina") == Decimal(davek)


@pytest.mark.parametrize("revenue, odhodki, osnova, davek", [
    ("10000", "8000.00", "2000.00", "400.00"),
    ("20000", "13000.00", "7000.00", "1400.00"),      # 10.000 + 7.500*40 %
    ("50000", "17000.00", "33000.00", "6600.00"),     # meja 20 % pri 33k
    ("60000", "17000.00", "43000.00", "10100.00"),    # 6.600 + 10.000*35 %
])
def test_normiran_partial_scheme_when_under_9_months(revenue, odhodki, osnova, davek):
    p = Profile(regime="normiran", activity_start=date(2026, 10, 1))
    res = calculate_year(p, YearInput(2026, revenue))
    assert res.scheme == "partial"
    assert res.value("normirani_odhodki") == Decimal(odhodki)
    assert res.value("davcna_osnova") == Decimal(osnova)
    assert res.value("dohodnina") == Decimal(davek)


def test_popoldanski_always_partial():
    p = Profile(regime="normiran", activity_start=FULL_YEAR, full_time=False)
    assert calculate_year(p, YearInput(2026, "20000")).scheme == "partial"


def test_nine_months_boundary():
    # 1.4. -> točno 9 mesecev -> polna shema
    assert calculate_year(Profile(regime="normiran", activity_start=date(2026, 4, 1)),
                          YearInput(2026, "1000")).scheme == "full"
    # 2.4. -> manj kot 9 mesecev
    assert calculate_year(Profile(regime="normiran", activity_start=date(2026, 4, 2)),
                          YearInput(2026, "1000")).scheme == "partial"


# ------------------------------------------------------------------ dohodnina lestvica 2026
@pytest.mark.parametrize("osnova, davek", [
    ("9721.43", "1555.43"),        # 16 %
    ("28592.44", "6461.89"),       # 1.555,43 + 4.906,46
    ("30000", "6926.39"),          # + 1.407,56 * 33 %
    ("57184.88", "15897.40"),      # + 28.592,44 * 33 %
    ("82346.23", "25710.32"),      # + 25.161,35 * 39 %
    ("100000", "34537.21"),        # + 17.653,77 * 50 %
])
def test_lestvica(osnova, davek):
    assert lestvica(Decimal(osnova), R)[0] == Decimal(davek)


def test_splosna_olajsava():
    assert splosna_olajsava(Decimal("20000"), R) == Decimal("5551.93")
    # 5.551,93 + 20.832,39 − 1,17259 × 10.000 = 14.658,42
    assert splosna_olajsava(Decimal("10000"), R) == Decimal("14658.42")
    # na pragu je dodatna olajšava ~0
    assert splosna_olajsava(Decimal("17766.18"), R) == Decimal("5551.93")


def test_olajsava_otroci():
    assert olajsava_otroci(1, 0, R) == Decimal("2995.83")
    assert olajsava_otroci(3, 0, R) == Decimal("11684.62")           # 2.995,83+3.256,77+5.432,02
    assert olajsava_otroci(4, 0, R) == Decimal("11684.62") + Decimal("7607.27")
    assert olajsava_otroci(0, 1, R) == Decimal("10856.24")


# ------------------------------------------------------------------ prispevki (uradni zneski)
def test_min_contributions_march_2026_matches_official_651_04():
    rows, _ = monthly_contributions(Profile(activity_start=date(2026, 3, 1)), 2026, R)
    march = rows[0]
    assert march.month == 3
    assert march.total == Decimal("651.04")        # uradni znesek od marca 2026
    assert march.components == {
        "piz": Decimal("370.51"), "zz": Decimal("204.66"), "do": Decimal("30.43"),
        "starsevsko": Decimal("3.04"), "zaposlovanje": Decimal("3.04"),
    }


def test_min_contributions_feb_2026_matches_official_648_85():
    rows, _ = monthly_contributions(Profile(activity_start=date(2026, 2, 1)), 2026, R)
    assert rows[0].total == Decimal("648.85")      # uradni znesek za februar 2026


def test_first_registration_piz_relief_50_then_30():
    p = Profile(activity_start=date(2026, 10, 1), first_registration_date=date(2026, 10, 1))
    rows, exp = monthly_contributions(p, 2026, R)
    assert [r.month for r in rows] == [10, 11, 12]
    assert rows[0].piz_relief == Decimal("185.26")              # 50 % od 370,51
    assert rows[0].total == Decimal("465.78")                   # 651,04 − 185,26
    assert exp.value == Decimal("1397.34")
    p2 = Profile(activity_start=date(2025, 1, 1), first_registration_date=date(2025, 1, 1))
    rows2, _ = monthly_contributions(p2, 2026, R)
    mar = next(r for r in rows2 if r.month == 3)
    assert mar.piz_relief == Decimal("111.15")                  # 30 % v 2. letu
    assert next(r for r in rows2 if r.month == 1).piz_relief == Decimal("104.97")  # 13. mesec od vpisa: 30 % od 349,90
    p3 = Profile(activity_start=date(2026, 1, 1), first_registration_date=date(2024, 1, 1))
    assert all(r.piz_relief == 0 for r in monthly_contributions(p3, 2026, R)[0])  # po 24 mesecih ni več olajšave


def test_contribution_due_dates_move_to_workday():
    p = Profile(activity_start=date(2026, 1, 1))
    rows, _ = monthly_contributions(p, 2026, R)
    for r in rows:
        assert is_workday(r.due_date)
        assert r.due_date.day >= 20


def test_partial_month_prorated():
    rows, _ = monthly_contributions(Profile(activity_start=date(2026, 11, 16)), 2026, R)
    nov = rows[0]
    assert nov.fraction == Decimal(15) / Decimal(30)
    assert nov.total == Decimal("325.53")   # pol osnove, zaokroženo po komponentah (+19,68 OZP)


def test_base_clamped_to_max():
    p = Profile(activity_start=FULL_YEAR, contribution_base_monthly=Decimal("20000"))
    rows, _ = monthly_contributions(p, 2026, R)
    assert next(r for r in rows if r.month == 6).base == Decimal("8876.11")


def test_pending_law_only_in_simulation():
    p = Profile(activity_start=FULL_YEAR, contribution_base_monthly=Decimal("8876.11"))
    real = calculate_year(p, YearInput(2026, "100000"))
    sim = calculate_year(p, YearInput(2026, "100000", simulate_pending=True))
    assert next(r for r in real.contributions if r.month == 6).base == Decimal("8876.11")
    assert next(r for r in sim.contributions if r.month == 6).base == Decimal("7500")
    assert any("ZIURS" in w for w in sim.warnings)


# ------------------------------------------------------------------ dejanski s.p.
def test_dejanski_full_example():
    # prihodki 60.000, stroški 10.000, minimalni prispevki celo leto
    res = calculate_year(dej(), YearInput(2026, "60000", "10000"))
    prispevki = res.value("prispevki")
    # jan: 577,65 + 37,17 = 614,82 ; feb 648,85 ; mar–dec 10 × 651,04 = 6.510,40
    assert prispevki == Decimal("7774.07")
    osnova = Decimal("60000") - Decimal("10000") - prispevki
    assert res.value("davcna_osnova") == osnova
    neto_osnova = osnova - Decimal("5551.93")
    assert res.value("dohodnina") == lestvica(neto_osnova, R)[0]


def test_dejanski_investment_relief_capped():
    res = calculate_year(dej(), YearInput(2026, "20000", "5000", investments="100000"))
    assert res.value("davcna_osnova") == Decimal("0.00")


def test_neto_identity():
    for regime in ("normiran", "dejanski"):
        res = calculate_year(Profile(regime=regime, activity_start=FULL_YEAR), YearInput(2026, "75000", "9000"))
        assert res.value("neto") == (Decimal("75000") - Decimal("9000") - res.value("prispevki")
                                     - res.value("dohodnina"))


def test_every_item_has_explain_and_sources():
    res = calculate_year(norm(), YearInput(2026, "50000", "5000")).to_dict()
    for key, item in res["items"].items():
        assert item["steps"], key
    assert res["items"]["dohodnina"]["sources"][0]["rule_id"] == "normiran.stopnja"


def test_akontacija_next_year_annualised_for_partial_year():
    p = Profile(regime="normiran", activity_start=date(2026, 10, 1))
    res = calculate_year(p, YearInput(2026, "10000"))
    # osnova 2.000 za okt–dec (3 meseci) -> letno 8.000; pravil 2027 še ni -> stopnje 2026 (partial) 20 %
    assert res.value("akontacija_naslednje_leto") == Decimal("1600.00")
    assert res.next_year["akontacija_obroki"] == "mesečno"
    assert res.next_year["akontacija_obrok"] == Decimal("133.33")


def test_mechanism_matches_real_edavki_obracun_2025_to_2026():
    """Mehanizem, preverjen na PRAVEM obračunu eDavki (DDD-DDD) za s.p., odprt julija 2025.
    Uradni obračun je potrdil: (1) tristopenjske normirane odhodke za < 9 mesecev,
    (2) enotno 20 % stopnjo za 2025, (3) preračun osnove × 12/6 (začeti mesec šteje cel),
    (4) akontacijo 2026 po stopnjah 2026 za 'ostale' (20 % do 33.000, 35 % nad tem).
    Številke spodaj so sintetične (repo je javen), formula pa je ista."""
    from app.tax_engine.engine import normiran_tax
    r25 = load_rules(2025)
    out = normiran_tax(Decimal("50000"), Decimal("5.71"), True, r25)
    assert out["_scheme"] == "partial"
    assert out["normirani_odhodki"].value == Decimal("17000.00")
    assert out["davcna_osnova"].value == Decimal("33000.00")
    assert out["dohodnina"].value == Decimal("6600.00")          # enotna 20 % v 2025
    # akontacija za 2026: 33.000 × 12/6 = 66.000 -> 33.000×20 % + 33.000×35 % = 18.150
    from app.tax_engine.engine import _bracket_sum
    tax, _ = _bracket_sum(Decimal("66000"), load_rules(2026).p("normiran.stopnja", "partial"))
    assert tax == Decimal("18150.00")
    p = Profile(regime="normiran", activity_start=date(2025, 7, 10))
    from app.tax_engine.engine import activity_month_count
    assert activity_month_count(p, 2025) == 6


def test_sprakt_example_full_year_60k():
    """Vloga DD-SprAkt (polno zavarovan ≥ 9 mesecev): 60.000 -> 48.000 -> 12.000 -> 2.400 / 200 mesečno."""
    res = calculate_year(norm(), YearInput(2026, "60000"))
    assert res.value("akontacija_naslednje_leto") == Decimal("2400.00")
    assert res.next_year["akontacija_obrok"] == Decimal("200.00")


def test_whatif_compares_both_regimes():
    rows = what_if(norm(), 2026, ["70000", "90000"], expense_ratio=Decimal("0.1"))
    assert set(rows[0]["regimes"]) == {"normiran", "dejanski"}
    assert rows[1]["regimes"]["normiran"]["dohodnina"] == "8400.00"


# ------------------------------------------------------------------ pravila
def test_missing_year_raises():
    with pytest.raises(RuleError):
        load_rules(2019)


def test_every_rule_has_source():
    for rule in R.all():
        assert rule.source, rule.id
        assert rule.source_url, rule.id


# ------------------------------------------------------------------ DDV in roki
def test_vat_new_taxpayer_monthly_and_due_last_workday():
    reg = date(2026, 10, 1)
    periods = periods_for_year(2026, reg)
    assert [p[2] for p in periods] == ["mesečno"] * 3
    lines = [VatLine(date(2026, 10, 5), Decimal("1000"), Decimal("220"), "out"),
             VatLine(date(2026, 10, 9), Decimal("100"), Decimal("22"), "in")]
    vp = vat_periods(2026, reg, lines)
    assert vp[0].payable == Decimal("198.00")
    assert vp[0].due_date == date(2026, 11, 30)  # zadnji delovni dan novembra (ponedeljek)


def test_vat_quarterly_after_12_months():
    periods = periods_for_year(2026, date(2024, 1, 1), Decimal("100000"))
    assert [p[2] for p in periods] == ["trimesečno"] * 4
    periods_big = periods_for_year(2026, date(2024, 1, 1), Decimal("300000"))
    assert len(periods_big) == 12


def test_workdays():
    assert not is_workday(date(2026, 10, 31))           # sobota + dan reformacije
    assert last_workday_of_month(2026, 10) == date(2026, 10, 30)
    assert not is_workday(date(2026, 4, 6))             # velikonočni ponedeljek 2026
    assert due_on_day(2026, 12, 25) == date(2026, 12, 28)  # 25., 26. praznik, 27. nedelja
