"""Home: 6 velikih številk, napredek, opozorila — vse z razlago (Explain)."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from ..models import Alert, DailyReport
from ..tax_engine import YearInput, calculate_year, fmt_eur
from ..tax_engine.money import ZERO, D, r2
from ..tax_engine.trace import Explained
from .ledger import Ledger


def ytd_result(L: Ledger):
    """Davčni izračun na podlagi podatkov DO DANES (prispevki do tekočega meseca)."""
    through = L.as_of.month if L.as_of.year == L.year else 12
    return calculate_year(L.profile, YearInput(L.year, L.revenue_ytd, L.expenses_ytd,
                                               contributions_through=through))


def vat_accrued(L: Ledger) -> tuple[Decimal, list]:
    periods = [p for p in L.vat_periods() if p.start <= L.as_of]
    return r2(sum((p.payable for p in periods), ZERO)), periods


def build(L: Ledger) -> dict:
    res = ytd_result(L)
    rules = res.rules
    prispevki = res.value("prispevki")
    dohodnina = res.value("dohodnina")
    vat_total, vat_p = vat_accrued(L)

    paid_prisp = L.paid("prispevki")
    paid_ak = L.paid("akontacija") + L.paid("dohodnina")
    paid_ddv = L.paid("ddv")
    paid_other = L.paid("drugo")

    e_paid = Explained("drzavi_do_sedaj", "Državi do sedaj", r2(paid_prisp + paid_ak + paid_ddv + paid_other),
                       formula="vsa evidentirana plačila FURS v letu (prispevki + akontacija + DDV)")
    e_paid.step("Prispevki", paid_prisp).step("Akontacija / dohodnina", paid_ak).step("DDV", paid_ddv)
    if paid_other:
        e_paid.step("Drugo", paid_other)
    e_paid.step("Skupaj", e_paid.value)

    owe_prisp = max(prispevki - paid_prisp, ZERO)
    owe_doh = max(dohodnina - paid_ak, ZERO)
    owe_ddv = max(vat_total - paid_ddv, ZERO)
    e_owe = Explained("se_dolgujes", "Še dolguješ", r2(owe_prisp + owe_doh + owe_ddv),
                      formula="(nastale obveznosti do danes) − (že plačano), po vrstah")
    e_owe.step(f"Prispevki: {fmt_eur(prispevki)} nastalo − {fmt_eur(paid_prisp)} plačano", owe_prisp)
    e_owe.step(f"Dohodnina: {fmt_eur(dohodnina)} nastalo − {fmt_eur(paid_ak)} plačano", owe_doh)
    e_owe.step(f"DDV: {fmt_eur(vat_total)} nastalo − {fmt_eur(paid_ddv)} plačano", owe_ddv)
    e_owe.step("Skupaj", e_owe.value)
    e_owe.rule_ids = ["prispevki.stopnje", "akontacija.letni_obracun", "ddv.obdobje"]

    revenue = L.revenue_ytd
    goal = D(L.bp.revenue_goal or 0)
    progress = [{
        "key": "goal", "label": "Letni cilj prihodkov", "value": str(revenue), "max": str(goal),
        "ratio": float(revenue / goal) if goal else 0.0,
    }]
    if L.bp.regime == "normiran":
        limit = D(rules.p("normiran.odhodki", "full")[0]["upto"] if res.scheme == "full"
                  else rules.p("normiran.odhodki", "partial")[0]["upto"])
        progress.append({"key": "normiran_limit", "label": "Meja normiranih odhodkov 80 %",
                         "value": str(revenue), "max": str(limit), "ratio": float(revenue / limit) if limit else 0.0,
                         "note": "Nad to mejo se odhodki priznajo v nižjem deležu ali sploh ne."})
    if not L.bp.vat_registered:
        thr = D(rules.p("ddv.prag", "threshold"))
        progress.append({"key": "vat_threshold", "label": "Prag za DDV", "value": str(revenue), "max": str(thr),
                         "ratio": float(revenue / thr)})
    else:
        progress.append({"key": "vat", "label": "Zavezanec za DDV", "value": str(vat_total), "max": None,
                         "ratio": None, "note": f"DDV nastal letos: {fmt_eur(vat_total)}"})

    from . import mistakes
    findings = mistakes.find(L)  # živo, ne iz zadnjega dnevnega pregleda
    dismissed = set(L.db.scalars(select(Alert.key).where(Alert.user_id == L.user_id, Alert.dismissed.is_(True))))
    findings = [f for f in findings if f["key"] not in dismissed]
    important = [f for f in findings if f["severity"] in ("error", "warning")]
    minor = len(findings) - len(important)
    report = L.db.scalar(select(DailyReport).where(DailyReport.user_id == L.user_id)
                         .order_by(DailyReport.created_at.desc()))

    def card(key, label, e: Explained, icon):
        d = e.to_dict(rules)
        d.update({"key": key, "label": label, "icon": icon})
        return d

    cards = [
        card("prihodki", "Prihodki letos", res.items["prihodki"], "💰"),
        card("stroski", "Stroški", res.items["stroski"], "💸"),
        card("davcna_osnova", "Davčna osnova", res.items["davcna_osnova"], "📊"),
        card("drzavi_do_sedaj", "Državi do sedaj", e_paid, "🏛️"),
        card("se_dolgujes", "Še dolguješ", e_owe, "📅"),
        card("neto", "Realno ti ostane", res.items["neto"], "💵"),
    ]
    return {
        "year": L.year,
        "as_of": L.as_of.isoformat(),
        "business_name": L.bp.business_name,
        "regime": L.bp.regime,
        "scheme": res.scheme,
        "cards": cards,
        "details": {k: v.to_dict(rules) for k, v in res.items.items()},
        "vat_periods": [p.to_dict(rules) for p in vat_p],
        "progress": progress,
        "attention": [{"key": f["key"], "severity": f["severity"], "title": f["title"], "detail": f["detail"],
                       "code": f["code"], "entity": f["entity"]} for f in important],
        "attention_minor": minor,
        "warnings": res.warnings,
        "daily_report": None if report is None else {
            "day": report.day.isoformat(), "ai_text": report.ai_text, "data": report.data},
        "rules_checked_on": rules.checked_on.isoformat() if rules.checked_on else None,
    }
