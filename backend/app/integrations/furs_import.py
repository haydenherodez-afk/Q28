"""Uvoz uradnih dokumentov eDavki (PDF): obračun DohDej (DDD-DDD) in vloga za spremembo akontacije
(DD-SprAkt). Branje je determinističen (regex na tekstu PDF), nato engine preveri, ali se
njegov izračun ujema s FURS — zelo močan test pravilnosti."""
from __future__ import annotations

import io
import re
from datetime import date
from decimal import Decimal

from pypdf import PdfReader

from ..tax_engine import D, fmt_eur, load_rules, r2
from ..tax_engine.engine import Profile, _bracket_sum, activity_month_count, normiran_tax
from ..tax_engine.rules import RuleError

AMOUNT = r"(-?[\d\.]+,\d{2})"


def _amt(s: str) -> Decimal:
    return D(s.replace(".", "").replace(",", "."))


def _date(s: str) -> date:
    d, m, y = s.split(".")
    return date(int(y), int(m), int(d))


def extract_text(data: bytes) -> str:
    text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    return text.replace("\xa0", " ").replace("\u2009", " ")


def parse_dohdej_obracun(text: str) -> dict:
    lines = {}
    for line in text.splitlines():
        m = re.match(rf"^\s*(\d+)\.\s+.*?\s{AMOUNT}\s*$", line)
        if m:
            lines.setdefault(int(m.group(1)), _amt(m.group(2)))
    per = re.search(r"za obdobje od\s+(\d{2}\.\d{2}\.\d{4})\s+do\s+(\d{2}\.\d{2}\.\d{4})", text)
    text = re.sub(r"[ \t]+", " ", text)
    regime = "normiran" if re.search(r"N\s*[–-]\s*Normirani", text) else "dejanski"
    not9 = bool(re.search(r"nisem bil obvezno zavarovan[^.]*vsaj 9 mesecev", text))
    was9 = bool(re.search(r"sem bil obvezno zavarovan[^.]*vsaj 9 mesecev", text)) and not not9
    taxno = re.search(r"Davčna številka\s+(\d{8})", text)
    skd = re.search(r"Vrsta dejavnosti\s+([\d\.]+)", text)
    prisp = re.search(rf"iz naslova opravljanja dejavnosti\s+{AMOUNT}", text)
    return {
        "doc_type": "DDD-DDD",
        "title": "Obračun akontacije dohodnine in dohodnine od dohodka iz dejavnosti",
        "period_from": _date(per.group(1)) if per else None,
        "period_to": _date(per.group(2)) if per else None,
        "regime": regime,
        "insured_9_months": was9 and not not9,
        "tax_number": taxno.group(1) if taxno else None,
        "skd": skd.group(1) if skd else None,
        "contributions_charged": _amt(prisp.group(1)) if prisp else None,
        "revenue": lines.get(4, lines.get(1)),
        "expenses": lines.get(8),
        "tax_base": lines.get(13),
        "tax": lines.get(20),
        "akontacija_paid": lines.get(25),
        "to_pay": lines.get(26),
        "overpaid": lines.get(27),
        "akontacija_base": lines.get(28),
        "akontacija_annual": lines.get(29),
        "akontacija_monthly": lines.get(30),
        "akontacija_quarterly": lines.get(31),
    }


def parse_sprakt(text: str) -> dict:
    def find(label):
        m = re.search(rf"{label}\s+{AMOUNT}", text)
        return _amt(m.group(1)) if m else None
    od = re.search(r"Obdobje od\s+(\d{2}\.\d{2}\.\d{4})", text)
    do = re.search(r"Obdobje do\s+(\d{2}\.\d{2}\.\d{4})", text)
    return {
        "doc_type": "DD-SprAkt",
        "title": "Vloga za medletno spremembo višine akontacij DohDej",
        "period_from": _date(od.group(1)) if od else None,
        "period_to": _date(do.group(1)) if do else None,
        "regime": "normiran" if "normiranih odhodkov" in text else "dejanski",
        "insured_9_months": bool(re.search(r"bom obvezno zavarovan[^\n]*najmanj 9 mesecev", text)),
        "revenue_estimate": find("Ocena višine prihodkov v tekočem obdobju s prilagoditvami"),
        "expenses_estimate": find("Ocena višine odhodkov v tekočem obdobju s prilagoditvami"),
        "tax_base": find("Ocenjena višina davčne osnove v tekočem obdobju"),
        "akontacija_annual": find(r"Ocenjena višina \(letne\) akontacije"),
        "akontacija_monthly": find("Mesečni obrok"),
        "business_name": (re.search(r"Naziv\s+(.+)", text).group(1).strip() if re.search(r"Naziv\s+(.+)", text) else None),
        "tax_number": (re.search(r"Davčna številka\s+(\d{8})", text).group(1)
                       if re.search(r"Davčna številka\s+(\d{8})", text) else None),
    }


def _check(label, ours, furs) -> dict:
    ok = furs is None or ours is None or abs(D(ours) - D(furs)) <= Decimal("0.01")
    return {"label": label, "engine": None if ours is None else str(r2(ours)),
            "furs": None if furs is None else str(r2(furs)), "match": ok}


def verify(doc: dict) -> list[dict]:
    """Engine izračuna isto, kar je izračunal FURS, in primerja."""
    checks = []
    try:
        if doc["doc_type"] == "DDD-DDD" and doc["regime"] == "normiran" and doc.get("period_from"):
            year = doc["period_from"].year
            rules = load_rules(year)
            p = Profile(regime="normiran", activity_start=doc["period_from"])
            months = activity_month_count(p, year)
            insured = D(12) if doc["insured_9_months"] else D(min(months, 8))
            res = normiran_tax(doc["revenue"], insured, True, rules)
            checks.append(_check("Normirani odhodki", res["normirani_odhodki"].value, doc["expenses"]))
            checks.append(_check("Davčna osnova", res["davcna_osnova"].value, doc["tax_base"]))
            checks.append(_check("Dohodnina", res["dohodnina"].value, doc["tax"]))
            if doc.get("akontacija_base") is not None:
                factor = D(12) / D(months) if months < 12 else D(1)
                ak_base = r2(res["davcna_osnova"].value * factor)
                checks.append(_check(f"Osnova za akontacijo (× 12/{months})", ak_base, doc["akontacija_base"]))
                try:
                    nr = load_rules(year + 1)
                    scheme = "full" if doc["insured_9_months"] else "partial"
                    tax, _ = _bracket_sum(ak_base, nr.p("normiran.stopnja", scheme))
                    checks.append(_check(f"Akontacija za {year + 1}", r2(tax), doc["akontacija_annual"]))
                    checks.append(_check("Mesečni obrok", r2(r2(tax) / 12), doc["akontacija_monthly"]))
                except RuleError:
                    pass
        elif doc["doc_type"] == "DD-SprAkt" and doc["regime"] == "normiran" and doc.get("period_from"):
            rules = load_rules(doc["period_from"].year)
            insured = D(12) if doc["insured_9_months"] else D(8)
            res = normiran_tax(doc["revenue_estimate"], insured, True, rules)
            checks.append(_check("Normirani odhodki", res["normirani_odhodki"].value, doc["expenses_estimate"]))
            checks.append(_check("Davčna osnova", res["davcna_osnova"].value, doc["tax_base"]))
            checks.append(_check("Letna akontacija", res["dohodnina"].value, doc["akontacija_annual"]))
            checks.append(_check("Mesečni obrok", r2(res["dohodnina"].value / 12), doc["akontacija_monthly"]))
    except RuleError as e:
        checks.append({"label": "Pravila", "engine": None, "furs": None, "match": False, "error": str(e)})
    return checks


def profile_updates(doc: dict) -> dict:
    """Predlagane nastavitve profila (uporabnik jih potrdi)."""
    up = {}
    if doc["doc_type"] == "DDD-DDD":
        up["regime"] = doc["regime"]
        if doc.get("period_from") and doc["period_from"] > date(doc["period_from"].year, 1, 1):
            up["activity_start"] = doc["period_from"].isoformat()
        if doc.get("revenue") is not None:
            up["prev_year_turnover"] = str(doc["revenue"])
        up["prev_year_insured_75"] = bool(doc["insured_9_months"])
        if doc.get("akontacija_annual") is not None:
            up["akontacija_annual"] = str(doc["akontacija_annual"])
        if doc.get("tax_number"):
            up["tax_number"] = doc["tax_number"]
    elif doc["doc_type"] == "DD-SprAkt":
        up["regime"] = doc["regime"]
        if doc.get("akontacija_annual") is not None:
            up["akontacija_annual"] = str(doc["akontacija_annual"])
        if doc.get("business_name"):
            up["business_name"] = doc["business_name"]
        if doc.get("tax_number"):
            up["tax_number"] = doc["tax_number"]
    return up


def import_pdf(data: bytes) -> dict:
    text = extract_text(data)
    flat = re.sub(r"\s+", " ", text)
    if "Vloga za medletno spremembo višine akontacij" in flat:
        doc = parse_sprakt(text)
        note = "Znižana akontacija velja šele, ko FURS vlogo odobri — preveri v eDavkih."
    elif "Obračun akontacije dohodnine in dohodnine od dohodka iz dejavnosti" in flat:
        doc = parse_dohdej_obracun(text)
        note = (f"Doplačilo po obračunu: {fmt_eur(doc['to_pay'])} (rok 30 dni po oddaji)."
                if doc.get("to_pay") else "")
    else:
        raise ValueError("Dokument ni prepoznan (podprta sta obračun DohDej in vloga DD-SprAkt iz eDavkov).")
    checks = verify(doc)
    serial = {k: (v.isoformat() if isinstance(v, date) else str(v) if isinstance(v, Decimal) else v)
              for k, v in doc.items()}
    return {"document": serial, "checks": checks, "all_match": bool(checks) and all(c["match"] for c in checks),
            "profile_updates": profile_updates(doc), "note": note}
