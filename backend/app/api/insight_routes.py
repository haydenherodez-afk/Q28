"""Pregledi: Home, davki z razlago, What-if, napoved, koledar, rezerva, cash, napake, audit, pravila."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit as audit_mod
from ..auth import current_user
from ..db import get_db
from ..engines import calendar as tax_calendar
from ..engines import cash, dashboard, forecast, mistakes
from ..engines.ledger import Ledger
from ..models import Alert, AuditLog, DailyReport, User
from ..schemas import CalcIn, WhatIfIn
from ..services import daily_check, sync_alerts
from ..tax_engine import Profile, YearInput, calculate_year, golden, load_rules, what_if
from ..tax_engine.rules import RuleError
from .deps import ledger

router = APIRouter(tags=["insights"])


@router.get("/dashboard")
def get_dashboard(L: Ledger = Depends(ledger)):
    return dashboard.build(L)


@router.get("/tax/annual")
def tax_annual(L: Ledger = Depends(ledger)):
    """Davčni izračun: do danes (YTD) in napoved celega leta, z razlago vsake številke."""
    ytd = dashboard.ytd_result(L)
    cur = next(s for s in forecast.build(L)["scenarios"] if s["key"] == "CURRENT")
    projected = calculate_year(L.profile, YearInput(L.year, cur["revenue"], cur["expenses"]))
    return {"ytd": ytd.to_dict(), "projected": projected.to_dict(),
            "vat_periods": [p.to_dict(ytd.rules) for p in L.vat_periods()]}


@router.post("/tax/calculate")
def tax_calculate(body: CalcIn, L: Ledger = Depends(ledger)):
    p = L.profile if body.regime == "profile" else Profile(**{**L.profile.__dict__, "regime": body.regime})
    return calculate_year(p, YearInput(L.year, body.revenue, body.expenses, body.investments,
                                       simulate_pending=body.simulate_pending)).to_dict()


@router.post("/tax/whatif")
def tax_whatif(body: WhatIfIn, L: Ledger = Depends(ledger)):
    rows = what_if(L.profile, L.year, body.revenues, expense_ratio=body.expense_ratio, expenses=body.expenses,
                   simulate_pending=body.simulate_pending)
    return {"year": L.year, "current_regime": L.bp.regime, "rows": rows}


@router.get("/forecast")
def get_forecast(L: Ledger = Depends(ledger)):
    return forecast.build(L)


@router.get("/calendar")
def get_calendar(L: Ledger = Depends(ledger)):
    return tax_calendar.build(L)


@router.get("/reserve")
def get_reserve(L: Ledger = Depends(ledger)):
    return cash.reserve(L)


@router.get("/cash")
def get_cash(L: Ledger = Depends(ledger)):
    return cash.profit_vs_cash(L)


@router.get("/mistakes")
def get_mistakes(L: Ledger = Depends(ledger), db: Session = Depends(get_db), user: User = Depends(current_user)):
    findings = mistakes.find(L)
    if L.year == date.today().year:
        sync_alerts(db, user, findings)
    dismissed = set(db.scalars(select(Alert.key).where(Alert.user_id == user.id, Alert.dismissed.is_(True))))
    findings = [f for f in findings if f["key"] not in dismissed]
    return {"count": len(findings), "items": findings}


@router.post("/alerts/dismiss")
def dismiss_by_key(key: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.scalar(select(Alert).where(Alert.user_id == user.id, Alert.key == key))
    if a is None:
        raise HTTPException(404, "Opozorilo ne obstaja (najprej odpri Napake)")
    return resolve_alert(a.id, user, db)


@router.post("/alerts/{aid}/resolve")
def resolve_alert(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Alert, aid)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Ne obstaja")
    a.resolved = True
    a.dismissed = True
    audit_mod.log(db, user.id, "resolve", f"Opozorilo označeno kot rešeno: {a.title}", "alert", a.id)
    db.commit()
    return {"ok": True}


@router.get("/audit")
def get_audit(limit: int = 200, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).where((AuditLog.user_id == user.id) | (AuditLog.user_id.is_(None)))
                      .order_by(AuditLog.ts.desc(), AuditLog.id.desc()).limit(min(limit, 1000)))
    return [{"id": r.id, "ts": r.ts.isoformat(), "action": r.action, "entity": r.entity, "entity_id": r.entity_id,
             "message": r.message, "before": r.before, "after": r.after} for r in rows]


@router.get("/rules")
def get_rules(year: int | None = None, user: User = Depends(current_user)):
    year = year or date.today().year
    try:
        rules = load_rules(year)
    except RuleError as e:
        raise HTTPException(404, str(e)) from e
    return {"year": year, "checked_on": rules.checked_on.isoformat() if rules.checked_on else None,
            "rules": [r.to_dict() for r in rules.all()],
            "pending": [r.to_dict() for r in rules.pending.values()]}


@router.get("/rules/selftest")
def rules_selftest(user: User = Depends(current_user)):
    return golden.run()


@router.get("/daily")
def latest_daily(user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.scalar(select(DailyReport).where(DailyReport.user_id == user.id).order_by(DailyReport.created_at.desc()))
    return None if r is None else {"day": r.day.isoformat(), "data": r.data, "ai_text": r.ai_text,
                                   "created_at": r.created_at.isoformat()}


@router.post("/daily/run")
def run_daily(with_ai: bool = True, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = daily_check(db, user, with_ai=with_ai)
    return {"day": r.day.isoformat(), "data": r.data, "ai_text": r.ai_text}
