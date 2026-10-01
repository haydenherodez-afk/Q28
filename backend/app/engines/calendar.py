"""Smart Tax Calendar: vsi roki z zneski, statusom plačila in preverbo stanja na TRR."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from ..tax_engine import fmt_eur, load_rules
from ..tax_engine.money import ZERO, D, r2
from ..tax_engine.workdays import add_months, due_on_day, next_workday
from .dashboard import ytd_result
from .forecast import build as build_forecast
from .ledger import Ledger


def _status(amount: Decimal | None, paid: Decimal, due: date, today: date) -> str:
    if amount is not None and amount <= 0:
        return "ni_obveznosti"
    if amount is not None and paid >= amount - D("0.01"):
        return "placano"
    if due < today:
        return "zamujeno"
    return "odprto"


def build(L: Ledger) -> dict:
    rules = load_rules(L.year)
    today = L.as_of
    items = []
    res_full = ytd_result(L)

    # prispevki — vsak mesec (projekcija za vse mesece leta z isto osnovo)
    from ..tax_engine import monthly_contributions
    rows, _ = monthly_contributions(L.profile, L.year, rules)
    for r in rows:
        period = f"{L.year}-{r.month:02d}"
        paid = L.paid("prispevki", period)
        items.append({
            "kind": "prispevki", "title": f"Prispevki za {r.month:02d}/{L.year}", "period": period,
            "due_date": r.due_date.isoformat(), "amount": str(r.total), "paid": str(paid),
            "status": _status(r.total, paid, r.due_date, today),
            "explain": f"Osnova {fmt_eur(r.base)} × 40,20 %"
                       + (f" − PIZ olajšava {fmt_eur(r.piz_relief)}" if r.piz_relief else "") + f" + OZP {fmt_eur(r.ozp)}",
            "rule_ids": ["prispevki.stopnje", "prispevki.rok"],
        })

    # akontacija dohodnine (odmerjena iz lanskega obračuna)
    ak = D(L.bp.akontacija_annual or 0)
    if ak > 0:
        p = rules.p("akontacija.obroki")
        if ak > D(p["monthly_threshold"]):
            for m in range(1, 13):
                ny, nm = add_months(L.year, m, 1)
                due = due_on_day(ny, nm, int(p["monthly_due_day"]))
                amount = r2(ak / 12)
                period = f"{L.year}-{m:02d}"
                paid = L.paid("akontacija", period)
                items.append({"kind": "akontacija", "title": f"Akontacija dohodnine {m:02d}/{L.year}",
                              "period": period, "due_date": due.isoformat(), "amount": str(amount),
                              "paid": str(paid), "status": _status(amount, paid, due, today),
                              "explain": f"Letna akontacija {fmt_eur(ak)} / 12", "rule_ids": ["akontacija.obroki"]})
        else:
            for q in range(1, 5):
                ny, nm = add_months(L.year, q * 3, 1)
                due = due_on_day(ny, nm, int(p["quarterly_due_day"]))
                amount = r2(ak / 4)
                period = f"{L.year}-Q{q}"
                paid = L.paid("akontacija", period)
                items.append({"kind": "akontacija", "title": f"Akontacija dohodnine Q{q}/{L.year}",
                              "period": period, "due_date": due.isoformat(), "amount": str(amount),
                              "paid": str(paid), "status": _status(amount, paid, due, today),
                              "explain": f"Letna akontacija {fmt_eur(ak)} / 4", "rule_ids": ["akontacija.obroki"]})

    # DDV
    periods = L.vat_periods()
    known = [p for p in periods if p.end <= today]
    avg_vat = (sum((p.payable for p in known), ZERO) / len(known)) if known else None
    for p in periods:
        label = p.start.strftime("%m/%Y") if p.kind == "mesečno" else f"{p.start.strftime('%m')}–{p.end.strftime('%m/%Y')}"
        period = p.start.strftime("%Y-%m") if p.kind == "mesečno" else f"{p.start.year}-Q{(p.start.month - 1) // 3 + 1}"
        estimated = p.start > today
        amount = (r2(avg_vat) if (estimated and avg_vat is not None) else (None if estimated else p.payable))
        paid = L.paid("ddv", period)
        items.append({"kind": "ddv", "title": f"DDV-O {label}", "period": period,
                      "due_date": p.due_date.isoformat(), "amount": None if amount is None else str(amount),
                      "estimated": estimated or p.end > today, "paid": str(paid),
                      "status": _status(amount, paid, p.due_date, today) if amount is not None else "odprto",
                      "explain": ("ocena po povprečju preteklih obdobij" if estimated else
                                  f"izstopni {fmt_eur(p.output_vat)} − vstopni {fmt_eur(p.input_vat)}"),
                      "rule_ids": ["ddv.obdobje"]})

    # letni davčni obračun (31.3. naslednje leto) in doplačilo
    lo = rules.p("akontacija.letni_obracun")
    obr_due = next_workday(date(L.year + 1, int(lo["due_month"]), int(lo["due_day"])))
    fc = build_forecast(L)
    current = next((s for s in fc["scenarios"] if s["key"] == "CURRENT"), None)
    est_tax = D(current["dohodnina"]) if current else res_full.value("dohodnina")
    ak_scheduled = max(D(L.bp.akontacija_annual or 0), L.paid("akontacija"))
    doplacilo = r2(max(est_tax - ak_scheduled - L.paid("dohodnina"), ZERO))
    items.append({"kind": "obracun", "title": f"Davčni obračun akontacije dohodnine {L.year}",
                  "period": str(L.year), "due_date": obr_due.isoformat(), "amount": None, "paid": "0",
                  "status": "odprto", "explain": "oddaja na eDavkih", "rule_ids": ["akontacija.letni_obracun"]})
    pay_due = next_workday(obr_due + timedelta(days=int(lo["payment_days_after"])))
    items.append({"kind": "dohodnina", "title": f"Doplačilo dohodnine {L.year} (ocena)", "period": str(L.year),
                  "due_date": pay_due.isoformat(), "amount": str(doplacilo), "estimated": True,
                  "paid": str(L.paid("dohodnina", str(L.year))),
                  "status": _status(doplacilo, L.paid("dohodnina", str(L.year)), pay_due, today),
                  "explain": f"ocenjena letna dohodnina {fmt_eur(est_tax)} − akontacija za leto {fmt_eur(ak_scheduled)} "
                             f"(scenarij 'trenutno povprečje'; rok: 30 dni po oddaji, če oddaš zadnji dan)",
                  "rule_ids": ["akontacija.letni_obracun"]})

    items.sort(key=lambda i: i["due_date"])

    # preverba likvidnosti za prihajajoče odprte obveznosti
    balance, _ = L.latest_balance()
    buffer = D(L.bp.safety_buffer or 0)
    running = balance
    for it in items:
        due = date.fromisoformat(it["due_date"])
        it["days_until"] = (due - today).days
        if it["status"] in ("odprto", "zamujeno") and it["amount"] is not None and running is not None:
            open_amount = max(D(it["amount"]) - D(it["paid"]), ZERO)
            running = running - open_amount
            it["balance_after"] = str(r2(running))
            if running < 0:
                it["cash_warning"] = f"Na TRR ni dovolj denarja za to obveznost (manjka {fmt_eur(-running)})."
            elif running < buffer:
                it["cash_warning"] = (f"Po plačilu ostane {fmt_eur(running)}, kar je manj od tvoje "
                                      f"varnostne rezerve {fmt_eur(buffer)}.")
    upcoming = [i for i in items if i["status"] in ("odprto", "zamujeno")]
    return {
        "year": L.year,
        "today": today.isoformat(),
        "balance": None if balance is None else str(balance),
        "safety_buffer": str(buffer),
        "items": items,
        "next": upcoming[:5],
    }
