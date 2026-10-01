"""Profil, izdani računi, stroški, plačila državi, stanje TRR — vse z audit logom."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit
from ..auth import current_user
from ..db import get_db
from ..engines.ledger import ensure_profile
from ..models import BankBalance, Expense, Invoice, TaxPayment, User
from ..schemas import (BalanceIn, ExpenseIn, ExpenseOut, InvoiceIn, InvoiceOut, PaymentIn, PaymentOut, ProfileIO)
from ..tax_engine import fmt_eur, r2

router = APIRouter(tags=["data"])


def _own(db: Session, model, oid: int, user: User):
    obj = db.get(model, oid)
    if obj is None or obj.user_id != user.id:
        raise HTTPException(404, "Ne obstaja")
    return obj


def _recalc_note(db, user):
    audit.log(db, user.id, "recalc", "Davčni engine ponovno izračunan (spremenjeni podatki)")


# ---------------------------------------------------------------- profil
@router.get("/profile", response_model=ProfileIO)
def get_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return ensure_profile(db, user)


@router.put("/profile", response_model=ProfileIO)
def put_profile(body: ProfileIO, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bp = ensure_profile(db, user)
    before = audit.snapshot(bp)
    for k, v in body.model_dump().items():
        setattr(bp, k, v)
    db.flush()
    audit.log(db, user.id, "update", "Spremenjene nastavitve podjetja", "profile", bp.id, before, audit.snapshot(bp))
    _recalc_note(db, user)
    db.commit()
    return bp


@router.post("/profile/apply", response_model=ProfileIO)
def apply_profile_updates(updates: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Uporabi predlog iz uvoza FURS dokumenta (po potrditvi uporabnika)."""
    bp = ensure_profile(db, user)
    data = ProfileIO.model_validate(bp).model_dump()
    allowed = set(data)
    for k, v in updates.items():
        if k not in allowed:
            raise HTTPException(400, f"Polja '{k}' ni mogoče nastaviti")
        data[k] = v
    return put_profile(ProfileIO(**data), user, db)


# ---------------------------------------------------------------- izdani računi
def _invoice_amounts(body: InvoiceIn) -> dict:
    d = body.model_dump()
    if d["vat"] is None:
        d["vat"] = r2(d["net"] * d["vat_rate"])
    if d["gross"] is None:
        d["gross"] = r2(d["net"] + d["vat"])
    return d


@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(year: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Invoice).where(Invoice.user_id == user.id)
    if year:
        q = q.where(Invoice.issue_date.between(date(year, 1, 1), date(year, 12, 31)))
    return list(db.scalars(q.order_by(Invoice.issue_date.desc(), Invoice.id.desc())))


@router.post("/invoices", response_model=InvoiceOut, status_code=201)
def create_invoice(body: InvoiceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = Invoice(user_id=user.id, **_invoice_amounts(body))
    db.add(inv)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"Račun s številko {body.number} že obstaja")
    audit.log(db, user.id, "create", f"Dodan prihodek {fmt_eur(inv.net)} (račun {inv.number}, {inv.customer})",
              "invoice", inv.id, after=audit.snapshot(inv))
    _recalc_note(db, user)
    db.commit()
    return inv


@router.put("/invoices/{iid}", response_model=InvoiceOut)
def update_invoice(iid: int, body: InvoiceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = _own(db, Invoice, iid, user)
    before = audit.snapshot(inv)
    for k, v in _invoice_amounts(body).items():
        setattr(inv, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"Račun s številko {body.number} že obstaja")
    audit.log(db, user.id, "update", f"Spremenjen račun {inv.number}: {fmt_eur(before['net'])} → {fmt_eur(inv.net)}"
              if Decimal(before["net"]) != inv.net else f"Spremenjen račun {inv.number}",
              "invoice", inv.id, before, audit.snapshot(inv))
    _recalc_note(db, user)
    db.commit()
    return inv


@router.post("/invoices/{iid}/pay", response_model=InvoiceOut)
def pay_invoice(iid: int, paid_date: date, amount: Decimal | None = None, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    inv = _own(db, Invoice, iid, user)
    before = audit.snapshot(inv)
    inv.paid_date = paid_date
    inv.paid_amount = amount if amount is not None else inv.gross
    audit.log(db, user.id, "update", f"Račun {inv.number} označen kot plačan ({fmt_eur(inv.paid_amount)})",
              "invoice", inv.id, before, audit.snapshot(inv))
    db.commit()
    return inv


@router.delete("/invoices/{iid}", status_code=204)
def delete_invoice(iid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = _own(db, Invoice, iid, user)
    audit.log(db, user.id, "delete", f"Izbrisan račun {inv.number} ({fmt_eur(inv.net)})", "invoice", inv.id,
              before=audit.snapshot(inv))
    db.delete(inv)
    _recalc_note(db, user)
    db.commit()


# ---------------------------------------------------------------- stroški
def _expense_amounts(body: ExpenseIn) -> dict:
    d = body.model_dump()
    net, vat, gross = d["net"], d["vat"], d["gross"]
    if net is None and gross is None:
        raise HTTPException(422, "Vpiši vsaj neto ali bruto znesek")
    if vat is None:
        vat = (gross - net) if (net is not None and gross is not None) else Decimal(0)
    if net is None:
        net = gross - vat
    if gross is None:
        gross = net + vat
    d.update(net=r2(net), vat=r2(vat), gross=r2(gross))
    return d


@router.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(year: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Expense).where(Expense.user_id == user.id)
    if year:
        q = q.where(Expense.date.between(date(year, 1, 1), date(year, 12, 31)))
    return list(db.scalars(q.order_by(Expense.date.desc(), Expense.id.desc())))


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(body: ExpenseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = Expense(user_id=user.id, **_expense_amounts(body))
    db.add(e)
    db.flush()
    audit.log(db, user.id, "create", f"Dodan strošek {fmt_eur(e.net)} ({e.supplier})", "expense", e.id,
              after=audit.snapshot(e))
    _recalc_note(db, user)
    db.commit()
    return e


@router.put("/expenses/{eid}", response_model=ExpenseOut)
def update_expense(eid: int, body: ExpenseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = _own(db, Expense, eid, user)
    before = audit.snapshot(e)
    for k, v in _expense_amounts(body).items():
        setattr(e, k, v)
    db.flush()
    msg = (f"Spremenjen strošek {e.supplier}: {fmt_eur(before['net'])} → {fmt_eur(e.net)}"
           if Decimal(before["net"]) != e.net else f"Spremenjen strošek {e.supplier}")
    audit.log(db, user.id, "update", msg, "expense", e.id, before, audit.snapshot(e))
    _recalc_note(db, user)
    db.commit()
    return e


@router.delete("/expenses/{eid}", status_code=204)
def delete_expense(eid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = _own(db, Expense, eid, user)
    audit.log(db, user.id, "delete", f"Izbrisan strošek {e.supplier} ({fmt_eur(e.net)})", "expense", e.id,
              before=audit.snapshot(e))
    db.delete(e)
    _recalc_note(db, user)
    db.commit()


# ---------------------------------------------------------------- plačila državi
@router.get("/payments", response_model=list[PaymentOut])
def list_payments(year: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(TaxPayment).where(TaxPayment.user_id == user.id)
    if year:
        q = q.where(TaxPayment.date.between(date(year, 1, 1), date(year + 1, 3, 31)))
    return list(db.scalars(q.order_by(TaxPayment.date.desc())))


@router.post("/payments", response_model=PaymentOut, status_code=201)
def create_payment(body: PaymentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = TaxPayment(user_id=user.id, **body.model_dump())
    db.add(p)
    db.flush()
    audit.log(db, user.id, "create", f"Evidentirano plačilo {p.kind} {p.period or ''} {fmt_eur(p.amount)}",
              "payment", p.id, after=audit.snapshot(p))
    db.commit()
    return p


@router.delete("/payments/{pid}", status_code=204)
def delete_payment(pid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _own(db, TaxPayment, pid, user)
    audit.log(db, user.id, "delete", f"Izbrisano plačilo {p.kind} {fmt_eur(p.amount)}", "payment", p.id,
              before=audit.snapshot(p))
    db.delete(p)
    db.commit()


@router.post("/balances", status_code=201)
def add_balance(body: BalanceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = BankBalance(user_id=user.id, date=body.date, balance=body.balance, source="manual")
    db.add(b)
    audit.log(db, user.id, "create", f"Stanje na TRR {body.date.isoformat()}: {fmt_eur(body.balance)}", "balance")
    db.commit()
    return {"ok": True}
