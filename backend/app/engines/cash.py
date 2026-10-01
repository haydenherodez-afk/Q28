"""Cash Engine: davčna rezerva ("ne dotikaj se") in Profit vs Cash."""
from __future__ import annotations

from decimal import Decimal

from ..tax_engine import fmt_eur
from ..tax_engine.money import ZERO, D, r2
from ..tax_engine.trace import Explained
from .dashboard import vat_accrued, ytd_result
from .ledger import Ledger


def reserve(L: Ledger) -> dict:
    res = ytd_result(L)
    rules = res.rules
    balance, bal_date = L.latest_balance()

    prisp = max(res.value("prispevki") - L.paid("prispevki"), ZERO)

    # akontacija: obroki, ki so do danes že zapadli v plačilo ali tečejo, pa niso plačani
    ak_annual = D(L.bp.akontacija_annual or 0)
    months_passed = L.as_of.month if L.as_of.year == L.year else 12
    ak_accrued = r2(ak_annual * months_passed / 12)
    ak = max(ak_accrued - L.paid("akontacija"), ZERO)

    # dohodnina: končna obveznost od že zasluženega − akontacija (plačana + rezervirana zgoraj)
    doh_final = res.value("dohodnina")
    doh = max(doh_final - L.paid("akontacija") - L.paid("dohodnina") - ak, ZERO)

    vat_total, _ = vat_accrued(L)
    vat = max(vat_total - L.paid("ddv"), ZERO)

    total = r2(prisp + ak + doh + vat)
    e = Explained("davcna_rezerva", "Davčna rezerva", total,
                  formula="neplačani prispevki + zapadla akontacija + preostanek dohodnine + neplačan DDV",
                  rule_ids=["prispevki.stopnje", "akontacija.obroki", "ddv.obdobje"])
    e.step("Prispevki (nastali, neplačani)", prisp)
    e.step("Akontacija (zapadli obroki, neplačani)", ak)
    e.step("Dohodnina — razlika do končne obveznosti od letošnjega zaslužka", doh)
    e.step("DDV (nastal, neplačan)", vat)
    e.step("Davčna rezerva", total)

    buffer = D(L.bp.safety_buffer or 0)
    out = {
        "as_of": L.as_of.isoformat(),
        "balance": None if balance is None else str(balance),
        "balance_date": None if bal_date is None else bal_date.isoformat(),
        "components": {"prispevki": str(r2(prisp)), "akontacija": str(r2(ak)),
                       "dohodnina": str(r2(doh)), "ddv": str(r2(vat))},
        "reserve": e.to_dict(rules),
        "safety_buffer": str(buffer),
    }
    if balance is not None:
        available = r2(balance - total)
        e2 = Explained("razpolozljivo", "Razpoložljivo", available, formula="stanje na TRR − davčna rezerva")
        e2.step("Stanje na TRR", balance).step("Davčna rezerva", -total).step("Razpoložljivo", available)
        out["available"] = e2.to_dict()
        out["available_after_buffer"] = str(r2(available - buffer))
        if available < 0:
            out["warning"] = f"Na TRR je {fmt_eur(-available)} premalo za pokritje vseh davčnih obveznosti!"
        elif available < buffer:
            out["warning"] = (f"Po rezervaciji davkov ostane {fmt_eur(available)}, manj od tvoje varnostne "
                              f"rezerve {fmt_eur(buffer)}.")
    else:
        out["warning"] = "Ni podatka o stanju na TRR — uvozi bančni izpisek ali vnesi stanje ročno."
    return out


def profit_vs_cash(L: Ledger) -> dict:
    issued_net = L.revenue_ytd
    issued_gross = r2(sum((D(i.gross) for i in L.invoices if i.issue_date <= L.as_of), ZERO))
    paid_gross = r2(sum((D(i.paid_amount) for i in L.invoices if i.issue_date <= L.as_of), ZERO))
    open_items = []
    for i in L.all_invoices:
        due = D(i.gross) - D(i.paid_amount)
        if due > D("0.01"):
            overdue = (L.as_of - i.due_date).days if i.due_date else None
            open_items.append({"id": i.id, "number": i.number, "customer": i.customer,
                               "issue_date": i.issue_date.isoformat(),
                               "due_date": i.due_date.isoformat() if i.due_date else None,
                               "open": str(r2(due)), "days_overdue": overdue if overdue and overdue > 0 else 0})
    open_items.sort(key=lambda x: -x["days_overdue"])
    inflow = r2(sum((D(t.amount) for t in L.bank if t.amount > 0 and t.date.year == L.year and t.date <= L.as_of), ZERO))
    outflow = r2(sum((-D(t.amount) for t in L.bank if t.amount < 0 and t.date.year == L.year and t.date <= L.as_of), ZERO))
    balance, _ = L.latest_balance()
    acc = Explained("accounting", "Ustvarjeno (računovodsko)", issued_net,
                    formula="izdani računi brez DDV (obdavčuje se po izdaji, ne po plačilu)")
    acc.step("Izdani računi z DDV", issued_gross).step("Izdani računi brez DDV", issued_net)
    cash = Explained("cash", "Dejansko prejeto (denar)", paid_gross, formula="plačila kupcev z DDV")
    cash.step("Plačano od izdanih računov", paid_gross).step("Še neplačano", issued_gross - paid_gross)
    return {
        "as_of": L.as_of.isoformat(),
        "accounting": acc.to_dict(),
        "cash": cash.to_dict(),
        "unpaid_total": str(r2(issued_gross - paid_gross)),
        "bank_inflow": str(inflow),
        "bank_outflow": str(outflow),
        "balance": None if balance is None else str(balance),
        "open_invoices": open_items,
        "note": "Davek se plača od izdanih računov, tudi če kupec še ni plačal — zato je rezerva pomembna.",
    }
