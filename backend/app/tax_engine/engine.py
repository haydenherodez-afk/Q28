"""HericR Tax Engine — deterministični davčni kalkulator za s.p.

Pravila: AI NIKOLI ne računa davka. AI kliče te funkcije in razloži rezultat.
Vsi parametri pridejo iz rules/<leto>.yaml; vsak rezultat je `Explained` z
vsemi koraki, formulo in viri.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .money import ZERO, D, fmt_eur, r2
from .rules import RuleSet, load_rules
from .trace import Explained
from .workdays import add_months, due_on_day

REGIMES = ("normiran", "dejanski")


# --------------------------------------------------------------------------- vhodni podatki
@dataclass
class Profile:
    regime: str = "normiran"                  # "normiran" | "dejanski"
    full_time: bool = True                    # polni s.p. (ne popoldanski)
    activity_start: date = date(2026, 1, 1)
    activity_end: date | None = None
    first_registration_date: date | None = None   # PRVI vpis v poslovni register -> PIZ olajšava
    vat_registered: bool = True
    vat_registration_date: date | None = None
    children: int = 0
    special_care_children: int = 0
    contribution_base_monthly: Decimal | None = None   # zavarovalna osnova iz odločbe / izbrana
    akontacija_annual: Decimal = ZERO                   # odmerjena akontacija za tekoče leto

    def __post_init__(self):
        if self.regime not in REGIMES:
            raise ValueError(f"Neznan režim '{self.regime}' (dovoljeno: {', '.join(REGIMES)})")
        if self.contribution_base_monthly is not None:
            self.contribution_base_monthly = D(self.contribution_base_monthly)
        self.akontacija_annual = D(self.akontacija_annual)


@dataclass
class YearInput:
    year: int
    revenue: Decimal              # prihodki BREZ DDV
    expenses: Decimal = ZERO      # dejanski stroški BREZ odbitnega DDV (brez prispevkov)
    investments: Decimal = ZERO   # vlaganja v opremo (olajšava pri dejanskih)
    simulate_pending: bool = False  # What-if: upoštevaj sprejete, a še neveljavne zakone
    contributions_through: int | None = None  # "do danes": prispevki samo do vključno tega meseca

    def __post_init__(self):
        self.revenue = D(self.revenue)
        self.expenses = D(self.expenses)
        self.investments = D(self.investments)
        if self.revenue < 0 or self.expenses < 0 or self.investments < 0:
            raise ValueError("Prihodki, stroški in vlaganja ne smejo biti negativni")


# --------------------------------------------------------------------------- rezultati
@dataclass
class MonthContribution:
    year: int
    month: int
    fraction: Decimal
    base: Decimal
    components: dict[str, Decimal]
    piz_relief: Decimal
    ozp: Decimal
    total: Decimal
    due_date: date

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "month": self.month,
            "fraction": str(self.fraction.quantize(Decimal("0.0001"))),
            "base": str(r2(self.base)),
            "components": {k: str(r2(v)) for k, v in self.components.items()},
            "piz_relief": str(r2(self.piz_relief)),
            "ozp": str(r2(self.ozp)),
            "total": str(r2(self.total)),
            "due_date": self.due_date.isoformat(),
        }


@dataclass
class AnnualResult:
    year: int
    regime: str
    scheme: str
    insured_months: Decimal
    items: dict[str, Explained]
    contributions: list[MonthContribution]
    next_year: dict
    warnings: list[str] = field(default_factory=list)
    rules: RuleSet | None = None

    def value(self, key: str) -> Decimal:
        return self.items[key].value

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "regime": self.regime,
            "scheme": self.scheme,
            "insured_months": str(self.insured_months.quantize(Decimal("0.01"))),
            "items": {k: v.to_dict(self.rules) for k, v in self.items.items()},
            "contributions": [c.to_dict() for c in self.contributions],
            "next_year": {k: (str(r2(v)) if isinstance(v, Decimal) else v) for k, v in self.next_year.items()},
            "warnings": self.warnings,
        }


# --------------------------------------------------------------------------- pomožne
def _bracket_sum(amount: Decimal, brackets: list[dict]) -> tuple[Decimal, list[tuple[Decimal, Decimal, Decimal, Decimal]]]:
    """Progresivno: vrne (vsota, [(od, do, osnova v razredu, stopnja)])."""
    total = ZERO
    parts = []
    lower = ZERO
    for b in brackets:
        upper = None if b["upto"] is None else D(b["upto"])
        rate = D(b["rate"])
        if amount <= lower:
            break
        top = amount if upper is None else min(amount, upper)
        chunk = top - lower
        if chunk > 0:
            total += chunk * rate
            parts.append((lower, top, chunk, rate))
        if upper is None:
            break
        lower = upper
    return total, parts


def _pct(rate: Decimal) -> str:
    s = f"{(rate * 100).normalize():f}".replace(".", ",")
    return f"{s} %"


def insured_fractions(profile: Profile, year: int) -> dict[int, Decimal]:
    """Delež vsakega meseca v letu, ko je s.p. aktiven (po dnevih)."""
    out = {}
    for month in range(1, 13):
        days_in = calendar.monthrange(year, month)[1]
        m_start, m_end = date(year, month, 1), date(year, month, days_in)
        start = max(m_start, profile.activity_start)
        end = min(m_end, profile.activity_end) if profile.activity_end else m_end
        days = (end - start).days + 1
        if days > 0:
            out[month] = D(days) / D(days_in)
    return out


def _months_between(a: date, b: date) -> int:
    """Celi meseci od a do b (b >= a)."""
    months = (b.year - a.year) * 12 + (b.month - a.month)
    if b.day < a.day:
        months -= 1
    return months


# --------------------------------------------------------------------------- PRISPEVKI
def monthly_contributions(profile: Profile, year: int, rules: RuleSet | None = None,
                          simulate_pending: bool = False,
                          through_month: int | None = None) -> tuple[list[MonthContribution], Explained]:
    rules = rules or load_rules(year)
    comps = rules.p("prispevki.stopnje", "components")
    total_rate = sum(D(c["rate"]) for c in comps)
    relief_rule = rules.get("prispevki.prva_samozaposlitev")
    due_day = int(rules.p("prispevki.rok", "day"))
    min_rule = rules.get("prispevki.min_osnova")
    max_rule = rules.get("prispevki.max_osnova")
    ozp_rule = rules.get("prispevki.ozp")

    exp = Explained(
        "prispevki", "Prispevki za socialno varnost", ZERO,
        formula=f"Σ po mesecih: osnova × {_pct(total_rate)} − PIZ olajšava + OZP",
        rule_ids=["prispevki.stopnje", "prispevki.min_osnova", "prispevki.max_osnova", "prispevki.ozp", "prispevki.rok"],
    )
    rows: list[MonthContribution] = []
    unverified: dict[str, list[str]] = {}
    for month, frac in insured_fractions(profile, year).items():
        if through_month is not None and month > through_month:
            continue
        day = date(year, month, 1)
        min_base, v1 = min_rule.period_value(day)
        max_base, v2 = max_rule.period_value(day)
        if simulate_pending and rules.has("pending.ziurs.razvojna_kapica"):
            max_base = min(max_base, D(rules.p("pending.ziurs.razvojna_kapica", "max_osnova")))
        ozp, v3 = ozp_rule.period_value(day)
        for ok, rid in ((v1, "prispevki.min_osnova"), (v2, "prispevki.max_osnova"), (v3, "prispevki.ozp")):
            if not ok:
                unverified.setdefault(rid, []).append(f"{month:02d}/{year}")
        chosen = profile.contribution_base_monthly or min_base
        base = min(max(chosen, min_base), max_base)
        base_eff = base * frac
        components = {c["key"]: r2(base_eff * D(c["rate"])) for c in comps}

        relief = ZERO
        if profile.first_registration_date:
            m = _months_between(profile.first_registration_date, max(day, profile.activity_start))
            if 0 <= m < 12:
                relief = r2(components["piz"] * D(relief_rule.params["first_12_months"]))
            elif 12 <= m < 24:
                relief = r2(components["piz"] * D(relief_rule.params["next_12_months"]))
        ozp_eff = r2(ozp * frac)
        total = sum(components.values()) - relief + ozp_eff
        ny, nm = add_months(year, month, 1)
        rows.append(MonthContribution(year, month, frac, base_eff, components, relief, ozp_eff, total,
                                      due_on_day(ny, nm, due_day)))

    exp.value = sum((r.total for r in rows), ZERO)
    if rows:
        first = rows[0]
        exp.step("Mesečna zavarovalna osnova", first.base / first.fraction if first.fraction else first.base,
                 "izbrana osnova, omejena z najnižjo in najvišjo")
        for c in comps:
            exp.step(f"{c['label']} ({_pct(D(c['rate']))})", None)
        exp.step(f"Skupna stopnja {_pct(total_rate)}", None)
        exp.step("Število zavarovanih mesecev", sum((r.fraction for r in rows), ZERO), "delni meseci po dnevih")
        relief_total = sum((r.piz_relief for r in rows), ZERO)
        if relief_total:
            exp.rule_ids.append("prispevki.prva_samozaposlitev")
            exp.step("Olajšava prva samozaposlitev (PIZ)", -relief_total)
        exp.step("OZP (pavšal) skupaj", sum((r.ozp for r in rows), ZERO))
        exp.step("Prispevki skupaj", exp.value)
    if unverified:
        months = sorted({m for ms in unverified.values() for m in ms})
        exp.warnings.append(f"Najnižja/najvišja osnova oz. OZP za {', '.join(months)} ni neodvisno potrjena "
                            f"(pravila: {', '.join(sorted(unverified))}) — preveri na FURS izpisu prispevkov.")
    if simulate_pending:
        exp.warnings.append("SIMULACIJA: upoštevana razvojna kapica iz ZIURS, ki še NE velja.")
        exp.rule_ids.append("pending.ziurs.razvojna_kapica")
    return rows, exp


# --------------------------------------------------------------------------- NORMIRANI
def normiran_tax(revenue: Decimal, months_insured: Decimal, full_time: bool, rules: RuleSet) -> dict[str, Explained]:
    min_months = D(rules.p("normiran.odhodki", "full_min_months"))
    scheme = "full" if (full_time and months_insured >= min_months) else "partial"
    scheme_label = "polni (≥ 9 mesecev polno zavarovan)" if scheme == "full" else "ostali (< 9 mesecev ali popoldanski)"

    od_br = rules.p("normiran.odhodki", scheme)
    odhodki, od_parts = _bracket_sum(revenue, od_br)
    odhodki = r2(odhodki)
    e_od = Explained("normirani_odhodki", "Normirani odhodki", odhodki,
                     formula=rules.get("normiran.odhodki").formula, rule_ids=["normiran.odhodki"])
    e_od.step("Shema", None, scheme_label)
    e_od.step("Prihodki (brez DDV)", revenue)
    for lo, hi, chunk, rate in od_parts:
        e_od.step(f"{_pct(rate)} od prihodkov {fmt_eur(lo)} – {fmt_eur(hi)}", chunk * rate)
    e_od.step("Normirani odhodki", odhodki)

    osnova = r2(revenue - odhodki)
    e_osn = Explained("davcna_osnova", "Davčna osnova", osnova, formula="prihodki − normirani odhodki",
                      rule_ids=["normiran.odhodki"])
    e_osn.step("Prihodki", revenue).step("Normirani odhodki", -odhodki).step("Davčna osnova", osnova)

    st_br = rules.p("normiran.stopnja", scheme)
    davek, st_parts = _bracket_sum(osnova, st_br)
    davek = r2(davek)
    e_tax = Explained("dohodnina", "Dohodnina (normiranec, dokončna)", davek,
                      formula=rules.get("normiran.stopnja").formula, rule_ids=["normiran.stopnja"])
    e_tax.step("Davčna osnova", osnova)
    for lo, hi, chunk, rate in st_parts:
        e_tax.step(f"{_pct(rate)} od osnove {fmt_eur(lo)} – {fmt_eur(hi)}", chunk * rate)
    e_tax.step("Dohodnina", davek)
    if revenue > 0:
        e_tax.step("Efektivna stopnja glede na prihodke", None, _pct((davek / revenue * 100).quantize(Decimal("0.01")) / 100))
    if scheme == "partial" and full_time:
        e_tax.warnings.append(
            "V tem letu si zavarovan manj kot 9 mesecev, zato velja shema 'ostali' "
            "(80 % odhodkov do 12.500 €, 20 % davka do 33.000 € osnove). Potrdi pri FURS.")
    return {"normirani_odhodki": e_od, "davcna_osnova": e_osn, "dohodnina": e_tax, "_scheme": scheme}


# --------------------------------------------------------------------------- DEJANSKI
def lestvica(osnova: Decimal, rules: RuleSet) -> tuple[Decimal, list]:
    davek, parts = _bracket_sum(osnova, rules.p("dohodnina.lestvica", "brackets"))
    return r2(davek), parts


def splosna_olajsava(dohodek: Decimal, rules: RuleSet) -> Decimal:
    p = rules.p("dohodnina.splosna_olajsava")
    base = D(p["base"])
    if dohodek <= D(p["additional_threshold"]):
        extra = D(p["additional_constant"]) - D(p["additional_factor"]) * dohodek
        return r2(base + max(extra, ZERO))
    return base


def olajsava_otroci(children: int, special: int, rules: RuleSet) -> Decimal:
    p = rules.p("dohodnina.olajsava_otroci")
    amounts = [D(p["first"]), D(p["second"]), D(p["third"])]
    total = ZERO
    for i in range(children):
        if i < 3:
            total += amounts[i]
        else:
            total += amounts[2] + D(p["increment_after_third"]) * (i - 2)
    total += D(p["special_care"]) * special
    return r2(total)


def dejanski_tax(revenue: Decimal, expenses: Decimal, prispevki: Decimal, investments: Decimal,
                 profile: Profile, rules: RuleSet) -> dict[str, Explained]:
    dobicek = r2(revenue - expenses - prispevki)
    e_od = Explained("odhodki", "Davčno priznani odhodki", r2(expenses + prispevki),
                     formula="dejanski stroški + obvezni prispevki za socialno varnost")
    e_od.step("Dejanski stroški (brez DDV)", expenses).step("Prispevki za socialno varnost", prispevki)
    e_od.step("Odhodki skupaj", expenses + prispevki)

    vl_rate = D(rules.p("dohodnina.olajsava_vlaganja", "rate"))
    vlaganja = r2(min(investments * vl_rate, max(dobicek, ZERO)))
    osnova = r2(max(dobicek - vlaganja, ZERO))
    e_osn = Explained("davcna_osnova", "Davčna osnova", osnova,
                      formula="prihodki − odhodki − olajšava za vlaganja",
                      rule_ids=["dohodnina.olajsava_vlaganja"])
    e_osn.step("Prihodki", revenue).step("Odhodki", -(expenses + prispevki)).step("Dobiček", dobicek)
    if vlaganja:
        e_osn.step(f"Olajšava za vlaganja ({_pct(vl_rate)} od {fmt_eur(investments)})", -vlaganja)
    e_osn.step("Davčna osnova", osnova)
    if dobicek < 0:
        e_osn.warnings.append("Izguba: davčna osnova je 0, izguba se lahko prenese v naslednja leta.")

    splosna = splosna_olajsava(osnova, rules)
    otroci = olajsava_otroci(profile.children, profile.special_care_children, rules)
    neto = r2(max(osnova - splosna - otroci, ZERO))
    davek, parts = lestvica(neto, rules)
    e_tax = Explained("dohodnina", "Dohodnina (letna, po lestvici)", davek,
                      formula="(davčna osnova − splošna olajšava − olajšave za otroke) po lestvici",
                      rule_ids=["dohodnina.lestvica", "dohodnina.splosna_olajsava"])
    e_tax.step("Davčna osnova", osnova).step("Splošna olajšava", -splosna)
    if otroci:
        e_tax.rule_ids.append("dohodnina.olajsava_otroci")
        e_tax.step(f"Olajšava za otroke ({profile.children} + {profile.special_care_children} s posebno nego)", -otroci)
    e_tax.step("Neto davčna osnova", neto)
    for lo, hi, chunk, rate in parts:
        e_tax.step(f"{_pct(rate)} od {fmt_eur(lo)} – {fmt_eur(hi)}", chunk * rate)
    e_tax.step("Dohodnina", davek)
    e_tax.warnings.append("Dohodnina pri dejanskih stroških je odvisna tudi od drugih dohodkov; "
                          "izračun predpostavlja, da je s.p. tvoj edini dohodek.")
    return {"odhodki": e_od, "davcna_osnova": e_osn, "dohodnina": e_tax, "_dobicek": dobicek}


# --------------------------------------------------------------------------- GLAVNI IZRAČUN
def calculate_year(profile: Profile, inp: YearInput, rules: RuleSet | None = None) -> AnnualResult:
    rules = rules or load_rules(inp.year)
    warnings: list[str] = []
    fractions = insured_fractions(profile, inp.year)
    insured_months = sum(fractions.values(), ZERO)

    contrib_rows, e_contrib = monthly_contributions(profile, inp.year, rules, inp.simulate_pending,
                                                    inp.contributions_through)
    prispevki = e_contrib.value

    items: dict[str, Explained] = {}
    e_rev = Explained("prihodki", "Prihodki (brez DDV)", inp.revenue, formula="vsota izdanih računov brez DDV")
    e_rev.step("Prihodki", inp.revenue)
    items["prihodki"] = e_rev
    e_exp = Explained("stroski", "Dejanski stroški (brez DDV)", inp.expenses,
                      formula="vsota prejetih računov brez odbitnega DDV")
    e_exp.step("Stroški", inp.expenses)
    items["stroski"] = e_exp
    items["prispevki"] = e_contrib

    if profile.regime == "normiran":
        res = normiran_tax(inp.revenue, insured_months, profile.full_time, rules)
        scheme = res.pop("_scheme")
        items.update(res)
        profit_for_base = items["davcna_osnova"].value  # prispevki niso bili odšteti
    else:
        res = dejanski_tax(inp.revenue, inp.expenses, prispevki, inp.investments, profile, rules)
        dobicek = res.pop("_dobicek")
        items.update(res)
        scheme = "dejanski"
        profit_for_base = dobicek + prispevki

    dohodnina = items["dohodnina"].value
    obligations = r2(prispevki + dohodnina)
    e_state = Explained("drzavi_skupaj", "Državi skupaj (prispevki + dohodnina)", obligations,
                        formula="prispevki + dohodnina (DDV je ločen, ker ni tvoj denar)")
    e_state.step("Prispevki", prispevki).step("Dohodnina", dohodnina).step("Skupaj", obligations)
    items["drzavi_skupaj"] = e_state

    neto = r2(inp.revenue - inp.expenses - obligations)
    e_net = Explained("neto", "Realno ti ostane", neto, formula="prihodki − dejanski stroški − prispevki − dohodnina")
    e_net.step("Prihodki", inp.revenue).step("Dejanski stroški", -inp.expenses)
    e_net.step("Prispevki", -prispevki).step("Dohodnina", -dohodnina).step("Ostane", neto)
    if inp.revenue > 0:
        e_net.step("Delež, ki ti ostane", None, _pct((neto / inp.revenue).quantize(Decimal("0.0001"))))
    items["neto"] = e_net

    # akontacija za naslednje leto (iz tega obračuna)
    ak = _next_year_akontacija(profile, inp, items, insured_months, rules)
    items["akontacija_naslednje_leto"] = ak

    # zavarovalna osnova za naslednje leto
    red = D(rules.p("prispevki.osnova_iz_dobicka", "reduction"))
    months = insured_months if insured_months > 0 else D(12)
    base_next = r2(max(profit_for_base, ZERO) * (1 - red) / months)
    min_base, _ = rules.get("prispevki.min_osnova").period_value(date(inp.year, 12, 1))
    max_base, _ = rules.get("prispevki.max_osnova").period_value(date(inp.year, 12, 1))
    base_next_clamped = min(max(base_next, min_base), max_base)

    ak_obroki = "mesečno" if ak.value > D(rules.p("akontacija.obroki", "monthly_threshold")) else "trimesečno"
    next_year = {
        "akontacija_letna": ak.value,
        "akontacija_obroki": ak_obroki,
        "akontacija_obrok": r2(ak.value / (12 if ak_obroki == "mesečno" else 4)),
        "zavarovalna_osnova_izracunana": base_next,
        "zavarovalna_osnova": base_next_clamped,
        "zavarovalna_osnova_opomba": "Po pravilu prispevki.osnova_iz_dobicka (ni neodvisno potrjeno — preveri na odločbi FURS).",
    }

    if profile.regime == "normiran":
        warnings.extend(_normiran_threshold_warnings(inp.revenue, insured_months, rules))
    if inp.simulate_pending:
        warnings.append("SIMULACIJA s sprejetim, a NEVELJAVNIM zakonom (ZIURS). Ni za planiranje plačil.")
    for e in items.values():
        warnings.extend(w for w in e.warnings if w not in warnings)

    return AnnualResult(inp.year, profile.regime, scheme, insured_months, items, contrib_rows,
                        next_year, warnings, rules)


def activity_month_count(profile: Profile, year: int) -> int:
    """Število koledarskih mesecev z dejavnostjo (začeti mesec šteje cel) — tako preračuna FURS.
    Primer iz obračuna eDavki: dejavnost 10.7.–31.12. -> 6 mesecev -> osnova × 12/6."""
    return len(insured_fractions(profile, year))


def _next_year_akontacija(profile: Profile, inp: YearInput, items: dict, insured_months: Decimal,
                          rules: RuleSet) -> Explained:
    """Akontacija za naslednje leto: osnova iz obračuna, preračunana na 12 mesecev, obdavčena po
    stopnjah, ki veljajo v letu akontacije (če pravila zanj še ne obstajajo, po tekočih)."""
    e = Explained("akontacija_naslednje_leto", "Akontacija dohodnine za naslednje leto", ZERO,
                  rule_ids=["akontacija.obroki", "akontacija.letni_obracun"])
    months = activity_month_count(profile, inp.year)
    factor = (D(12) / D(months)) if 0 < months < 12 else D(1)
    try:
        next_rules = load_rules(inp.year + 1)
    except Exception:
        next_rules = rules
        e.warnings.append(f"Pravila za {inp.year + 1} še niso objavljena — akontacija je izračunana po "
                          f"stopnjah {inp.year}.")
    osnova = r2(items["davcna_osnova"].value * factor)
    e.step("Davčna osnova iz obračuna", items["davcna_osnova"].value)
    if factor != 1:
        e.step(f"Preračun na letno raven (× 12 / {months} mesecev dejavnosti)", osnova)
    if profile.regime == "normiran":
        min_months = D(rules.p("normiran.stopnja", "full_min_months"))
        scheme = "full" if (profile.full_time and insured_months >= min_months) else "partial"
        e.formula = "osnova (preračunana na 12 mesecev) × stopnje za normirance v letu akontacije"
        brackets = next_rules.p("normiran.stopnja", scheme)
        tax, parts = _bracket_sum(osnova, brackets)
        e.rule_ids.append("normiran.stopnja")
        for lo, hi, chunk, rate in parts:
            e.step(f"{_pct(rate)} od {fmt_eur(lo)} – {fmt_eur(hi)}", chunk * rate)
        e.value = r2(tax)
    else:
        e.formula = "davek po lestvici od (letna osnova − splošna olajšava − olajšave za otroke)"
        neto = max(osnova - splosna_olajsava(osnova, next_rules)
                   - olajsava_otroci(profile.children, profile.special_care_children, next_rules), ZERO)
        e.value, _ = lestvica(r2(neto), next_rules)
        e.step("Neto osnova po olajšavah", neto)
    e.step("Letna akontacija", e.value)
    if factor != 1:
        e.warnings.append("Akontacija je preračunana na celo leto. Če pričakuješ nižje prihodke, jo lahko "
                          "z vlogo DD-SprAkt znižaš.")
    return e


def _normiran_threshold_warnings(revenue: Decimal, insured_months: Decimal, rules: RuleSet) -> list[str]:
    out = []
    first_bracket = D(rules.p("normiran.odhodki", "full")[0]["upto"])
    if revenue > first_bracket:
        out.append(f"Prihodki nad {fmt_eur(first_bracket)}: nad to mejo NI več normiranih odhodkov, "
                   "vsak dodaten evro je obdavčen v celoti.")
    top = D(rules.p("normiran.vstopni_prag", "both_years"))
    if revenue > top:
        out.append(f"Prihodki nad {fmt_eur(top)}: če povprečje dveh let preseže prag, ne moreš več biti normiranec.")
    return out


# --------------------------------------------------------------------------- WHAT-IF
def what_if(profile: Profile, year: int, revenues: list, expense_ratio: Decimal | None = None,
            expenses: Decimal | None = None, simulate_pending: bool = False) -> list[dict]:
    """Za vsak prihodek vrne razčlenitev za OBA režima (primerjava)."""
    rules = load_rules(year)
    out = []
    for rev in revenues:
        rev = D(rev)
        exp = D(expenses) if expenses is not None else r2(rev * D(expense_ratio or 0))
        row = {"revenue": str(r2(rev)), "expenses": str(r2(exp)), "regimes": {}}
        for regime in REGIMES:
            p = Profile(**{**profile.__dict__, "regime": regime})
            res = calculate_year(p, YearInput(year, rev, exp, simulate_pending=simulate_pending), rules)
            row["regimes"][regime] = {
                "prispevki": str(res.value("prispevki")),
                "dohodnina": str(res.value("dohodnina")),
                "davcna_osnova": str(res.value("davcna_osnova")),
                "drzavi_skupaj": str(res.value("drzavi_skupaj")),
                "neto": str(res.value("neto")),
                "scheme": res.scheme,
            }
        out.append(row)
    return out
