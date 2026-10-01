"""Find mistakes: deterministične kontrole podatkov. Vsaka najdba ima stabilen ključ (brez podvajanja)."""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from ..tax_engine import fmt_eur, load_rules
from ..tax_engine.money import ZERO, D, r2
from .ledger import Ledger

VAT_RATES = [Decimal("0"), Decimal("0.05"), Decimal("0.095"), Decimal("0.22")]

# Trgovci, kjer je nakup pogosto zaseben (ni nujno napaka — samo opozorilo)
PRIVATE_HINTS = ["mercator", "spar", "hofer", "lidl", "tuš", "eurospin", "zara", "h&m", "netflix", "spotify",
                 "disney", "restavracija", "pizzeria", "kino", "booking.com", "airbnb", "dm-drogerie", "müller",
                 "lekarna", "big bang", "steam", "playstation"]

CATEGORY_HINTS = {
    "gorivo": ["petrol", "omv", "mol ", "shell", "eni ", "lukoil"],
    "programska oprema": ["adobe", "microsoft", "google", "github", "atlassian", "openai", "anthropic", "dropbox"],
    "telekomunikacije": ["telekom", "a1 ", "telemach", "t-2", "hot mobil"],
    "orodje in material": ["merkur", "bauhaus", "obi ", "würth", "wurth", "hilti", "kovinotehna", "jub"],
    "zavarovanje": ["triglav", "generali", "sava zav", "zavarovalnica"],
}

FURS_HINTS = ["furs", "fu rs", "finančna uprava", "financna uprava", "prispev", "akontac", "ddv", "dohodnin"]


def _f(sev, code, key, title, detail, entity=None, entity_id=None):
    return {"severity": sev, "code": code, "key": key, "title": title, "detail": detail,
            "entity": entity, "entity_id": entity_id}


def find(L: Ledger) -> list[dict]:
    out: list[dict] = []
    today = L.as_of
    rules = load_rules(L.year)

    # ❌ izdan račun brez plačila (zapadel)
    for i in L.all_invoices:
        open_amt = D(i.gross) - D(i.paid_amount)
        if open_amt > D("0.01") and i.due_date and i.due_date < today:
            days = (today - i.due_date).days
            out.append(_f("warning" if days < 30 else "error", "invoice_unpaid", f"invoice_unpaid:{i.id}",
                          f"Račun {i.number} ni plačan ({days} dni po zapadlosti)",
                          f"{i.customer}: odprto {fmt_eur(open_amt)}. Davek si od tega računa že dolžan plačati.",
                          "invoice", i.id))

    # ❌ priliv na TRR brez računa
    for t in L.bank:
        if t.amount > 0 and not t.matched_invoice_id and t.date.year == L.year and t.category != "zasebno":
            out.append(_f("warning", "payment_without_invoice", f"payment_without_invoice:{t.id}",
                          f"Priliv {fmt_eur(t.amount)} brez povezanega računa",
                          f"{t.date.isoformat()} · {t.counterparty} · {t.description[:80]}", "bank", t.id))
        # odliv brez prejetega računa (ni davek, ni zasebno)
        if (t.amount < 0 and not t.matched_expense_id and t.date.year == L.year
                and t.category not in ("prispevki", "akontacija", "ddv", "dohodnina", "drugo", "zasebno", "dvig")
                and not any(h in f"{t.counterparty} {t.description}".lower() for h in FURS_HINTS)
                and -t.amount >= 20):
            out.append(_f("info", "payment_without_expense", f"payment_without_expense:{t.id}",
                          f"Odliv {fmt_eur(-t.amount)} brez prejetega računa",
                          f"{t.date.isoformat()} · {t.counterparty}. Naloži račun (skener) ali označi kot zasebno.",
                          "bank", t.id))
        # odliv FURS, ki ni evidentiran kot davčno plačilo
        if t.amount < 0 and any(h in f"{t.counterparty} {t.description}".lower() for h in FURS_HINTS) \
                and t.category not in ("prispevki", "akontacija", "ddv", "dohodnina", "drugo"):
            out.append(_f("info", "furs_payment_untagged", f"furs_payment_untagged:{t.id}",
                          f"Plačilo FURS {fmt_eur(-t.amount)} ni razporejeno",
                          "Označi ga kot prispevki / akontacija / DDV, da bo štelo v 'Državi do sedaj'.", "bank", t.id))

    # ❌ podvojeni prejeti računi
    seen: dict = {}
    for e in L.expenses:
        k1 = (e.supplier.strip().lower(), (e.invoice_number or "").strip().lower()) if e.invoice_number else None
        k2 = (e.supplier.strip().lower(), e.date, D(e.gross))
        for k in (k1, k2):
            if k is None:
                continue
            if k in seen and seen[k] != e.id:
                out.append(_f("error", "duplicate_expense", f"duplicate_expense:{min(seen[k], e.id)}:{max(seen[k], e.id)}",
                              f"Morda podvojen strošek: {e.supplier} {fmt_eur(e.gross)}",
                              f"Enak dobavitelj in {'številka računa' if k is k1 else 'datum in znesek'} "
                              f"kot strošek #{seen[k]}.", "expense", e.id))
                break
            seen[k] = e.id

    # ❌ zaporedje številk izdanih računov (zakon zahteva neprekinjeno številčenje)
    by_prefix = defaultdict(list)
    for i in L.invoices:
        m = re.match(r"^(.*?)(\d+)$", i.number.strip())
        if m:
            by_prefix[m.group(1)].append(int(m.group(2)))
    for prefix, nums in by_prefix.items():
        nums = sorted(nums)
        missing = sorted(set(range(nums[0], nums[-1] + 1)) - set(nums))
        if missing:
            out.append(_f("warning", "invoice_gap", f"invoice_gap:{prefix}:{','.join(map(str, missing[:20]))}",
                          f"Vrzel v številčenju računov ({prefix}…)",
                          f"Manjkajo številke: {', '.join(map(str, missing[:20]))}" + (" …" if len(missing) > 20 else ""),
                          "invoice", None))

    # ❌ nenavadno velik strošek
    amounts = [D(e.net) for e in L.business_expenses]
    if len(amounts) >= 5:
        med = statistics.median(amounts)
        for e in L.business_expenses:
            if med > 0 and D(e.net) > med * 5 and D(e.net) > 500:
                out.append(_f("info", "large_expense", f"large_expense:{e.id}",
                              f"Nenavadno velik strošek: {fmt_eur(e.net)}",
                              f"{e.supplier} — {round(D(e.net) / med, 1)}× mediana tvojih stroškov. "
                              "Če je osnovno sredstvo, ga morda amortiziraš (dejanski s.p.).", "expense", e.id))

    # ❌ DDV na računu
    for i in L.invoices:
        net, vat = D(i.net), D(i.vat)
        if L.bp.vat_registered and vat == 0 and not i.vat_note:
            out.append(_f("error", "invoice_missing_vat", f"invoice_missing_vat:{i.id}",
                          f"Račun {i.number} je brez DDV", "Si zavezanec za DDV. Če gre za oprostitev ali obrnjeno "
                          "davčno obveznost (76.a člen ZDDV-1), to navedi v opombi računa.", "invoice", i.id))
        if not L.bp.vat_registered and vat > 0:
            out.append(_f("error", "invoice_vat_not_registered", f"invoice_vat_not_registered:{i.id}",
                          f"Račun {i.number} ima DDV, čeprav nisi zavezanec", "Nezavezanec ne sme obračunati DDV.",
                          "invoice", i.id))
        if net > 0 and vat > 0 and not any(abs(vat - r2(net * r)) <= D("0.02") for r in VAT_RATES):
            out.append(_f("warning", "invoice_odd_vat", f"invoice_odd_vat:{i.id}",
                          f"Nenavaden DDV na računu {i.number}",
                          f"DDV {fmt_eur(vat)} ni 22 %, 9,5 % ali 5 % od {fmt_eur(net)}.", "invoice", i.id))
        if abs(D(i.gross) - net - vat) > D("0.02"):
            out.append(_f("error", "invoice_sum", f"invoice_sum:{i.id}", f"Račun {i.number}: neto + DDV ≠ bruto",
                          f"{fmt_eur(net)} + {fmt_eur(vat)} ≠ {fmt_eur(i.gross)}", "invoice", i.id))
    for e in L.expenses:
        net, vat = D(e.net), D(e.vat)
        if net > 0 and vat > 0 and not any(abs(vat - r2(net * r)) <= D("0.02") for r in VAT_RATES):
            out.append(_f("warning", "expense_odd_vat", f"expense_odd_vat:{e.id}",
                          f"Nenavaden DDV na strošku {e.supplier}",
                          f"DDV {fmt_eur(vat)} ni standardna stopnja od {fmt_eur(net)}.", "expense", e.id))
        if abs(D(e.gross) - net - vat) > D("0.02"):
            out.append(_f("error", "expense_sum", f"expense_sum:{e.id}", f"Strošek {e.supplier}: neto + DDV ≠ bruto",
                          f"{fmt_eur(net)} + {fmt_eur(vat)} ≠ {fmt_eur(e.gross)}", "expense", e.id))

    # ❌ manjkajoči podatki
    for i in L.invoices:
        if not i.customer.strip():
            out.append(_f("warning", "missing_data", f"missing_customer:{i.id}", f"Račun {i.number} nima kupca",
                          "Vpiši naziv kupca.", "invoice", i.id))
    for e in L.expenses:
        miss = [n for n, v in (("dobavitelj", e.supplier.strip()), ("številka računa", e.invoice_number),
                               ("kategorija", e.category), ("dokument", e.document_id)) if not v]
        if miss:
            out.append(_f("info", "missing_data", f"missing_expense:{e.id}",
                          f"Strošku {e.supplier or '#' + str(e.id)} manjka: {', '.join(miss)}",
                          "Brez računa (dokumenta) strošek pri inšpekciji ni dokazljiv.", "expense", e.id))

    # ❌ napačna kategorija / morda zasebno
    for e in L.expenses:
        text = f"{e.supplier} {e.notes or ''}".lower() + " "
        for cat, hints in CATEGORY_HINTS.items():
            if any(h in text for h in hints) and e.category and e.category != cat:
                out.append(_f("info", "category_mismatch", f"category_mismatch:{e.id}",
                              f"Kategorija morda napačna: {e.supplier}",
                              f"Označeno kot '{e.category}', pričakovano '{cat}'.", "expense", e.id))
                break
        if not e.private_flag and any(h in text for h in PRIVATE_HINTS):
            out.append(_f("info", "maybe_private", f"maybe_private:{e.id}", f"Morda zaseben strošek: {e.supplier}",
                          "Zasebni stroški niso davčno priznani in DDV ni odbiten. Preveri ali označi kot zasebno.",
                          "expense", e.id))

    # ❌ obveznosti, ki niso označene kot plačane
    from .calendar import build as build_calendar
    for it in build_calendar(L)["items"]:
        if it["status"] == "zamujeno":
            out.append(_f("error", "obligation_overdue", f"obligation_overdue:{it['kind']}:{it['period']}",
                          f"{it['title']} — rok je potekel {it['due_date']}",
                          f"Znesek {fmt_eur(it['amount'] or 0)}, plačano {fmt_eur(it['paid'])}. Če si plačal, "
                          "evidentiraj plačilo (ali uvozi izpisek).", "calendar", None))

    # ⚠️ pragovi za normirance
    if L.bp.regime == "normiran":
        from .forecast import build as build_forecast
        fc = build_forecast(L)
        cur = next((s for s in fc["scenarios"] if s["key"] == "CURRENT"), None)
        if cur:
            projected = D(cur["revenue"])
            limit = D(rules.p("normiran.odhodki", "full")[0]["upto"])
            if projected > limit:
                out.append(_f("warning", "normiran_over_60k", f"normiran_over_60k:{L.year}",
                              f"Napoved prihodkov {fmt_eur(projected)} presega {fmt_eur(limit)}",
                              "Nad to mejo ni več normiranih odhodkov — vsak evro nad mejo je obdavčen v celoti. "
                              "Primerjaj z dejanskimi stroški v What-if.", None, None))
            p = rules.p("normiran.vstopni_prag")
            this_full = L.bp.full_time and L.profile.activity_start <= date(L.year, 4, 1)
            prev_full = bool(L.bp.prev_year_insured_75)
            thr = D(p["both_years"] if (this_full and prev_full) else p["one_year"] if (this_full or prev_full) else p["none"])
            avg = (D(L.bp.prev_year_turnover or 0) + projected) / 2
            if avg > thr:
                out.append(_f("error", "normiran_exit", f"normiran_exit:{L.year + 1}",
                              f"V {L.year + 1} morda ne boš več normiranec",
                              f"Povprečje prihodkov {L.year - 1} in {L.year} (napoved) = {fmt_eur(avg)} > prag "
                              f"{fmt_eur(thr)}. Max letošnji prihodki za ostanek: "
                              f"{fmt_eur(thr * 2 - D(L.bp.prev_year_turnover or 0))}.", None, None))
            elif avg > thr * D("0.9"):
                out.append(_f("warning", "normiran_exit_near", f"normiran_exit_near:{L.year + 1}",
                              f"Blizu praga za normirance ({fmt_eur(avg)} od {fmt_eur(thr)})",
                              f"Max letošnji prihodki za ostanek v sistemu: "
                              f"{fmt_eur(thr * 2 - D(L.bp.prev_year_turnover or 0))}.", None, None))
    if not L.bp.vat_registered:
        thr = D(rules.p("ddv.prag", "threshold"))
        if L.revenue_ytd > thr * D("0.85"):
            out.append(_f("warning", "vat_threshold", f"vat_threshold:{L.year}",
                          f"Blizu praga za DDV: {fmt_eur(L.revenue_ytd)} / {fmt_eur(thr)}",
                          "Nad 60.000 € postaneš zavezanec s 1.1. naslednjega leta, nad 66.000 € takoj.", None, None))

    sev_order = {"error": 0, "warning": 1, "info": 2}
    out.sort(key=lambda f: sev_order[f["severity"]])
    return out
