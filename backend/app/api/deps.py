from datetime import date

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..engines.ledger import Ledger
from ..models import User
from ..services import today
from ..tax_engine.rules import RuleError, load_rules


def period(year: int | None = Query(None, ge=2020, le=2100), as_of: date | None = None) -> tuple[int, date]:
    t = today()
    year = year or t.year
    if as_of is None:
        as_of = t if year == t.year else date(year, 12, 31)
    return year, as_of


def ledger(p=Depends(period), db: Session = Depends(get_db), user: User = Depends(current_user)) -> Ledger:
    year, as_of = p
    try:
        load_rules(year)
    except RuleError as e:
        raise HTTPException(422, str(e)) from e
    return Ledger.load(db, user, year, as_of)
