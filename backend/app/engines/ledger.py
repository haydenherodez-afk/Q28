"""Knjiga: zbere podatke uporabnika iz baze za izbrano leto (en vir resnice za vse engine)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cached_property

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BankBalance, BankTransaction, BusinessProfile, Expense, Invoice, TaxPayment, User
from ..tax_engine import D, Profile, VatLine, vat_periods
from ..tax_engine.money import ZERO, r2


def tax_profile(bp: BusinessProfile) -> Profile:
    return Profile(
        regime=bp.regime,
        full_time=bp.full_time,
        activity_start=bp.activity_start,
        first_registration_date=bp.first_registration_date,
        vat_registered=bp.vat_registered,
        vat_registration_date=bp.vat_registration_date,
        children=bp.children,
        special_care_children=bp.special_care_children,
        contribution_base_monthly=bp.contribution_base_monthly,
        akontacija_annual=bp.akontacija_annual or ZERO,
    )


def ensure_profile(db: Session, user: User) -> BusinessProfile:
    bp = db.scalar(select(BusinessProfile).where(BusinessProfile.user_id == user.id))
    if bp is None:
        bp = BusinessProfile(user_id=user.id)
        db.add(bp)
        db.commit()
    return bp


@dataclass
class Ledger:
    db: Session
    user_id: int
    year: int
    as_of: date
    bp: BusinessProfile

    @classmethod
    def load(cls, db: Session, user: User, year: int, as_of: date) -> "Ledger":
        return cls(db, user.id, year, as_of, ensure_profile(db, user))

    @property
    def profile(self) -> Profile:
        return tax_profile(self.bp)

    def _year_range(self):
        return date(self.year, 1, 1), date(self.year, 12, 31)

    @cached_property
    def invoices(self) -> list[Invoice]:
        a, b = self._year_range()
        return list(self.db.scalars(select(Invoice).where(Invoice.user_id == self.user_id,
                                                          Invoice.issue_date.between(a, b))
                                    .order_by(Invoice.issue_date, Invoice.id)))

    @cached_property
    def all_invoices(self) -> list[Invoice]:
        return list(self.db.scalars(select(Invoice).where(Invoice.user_id == self.user_id)))

    @cached_property
    def expenses(self) -> list[Expense]:
        a, b = self._year_range()
        return list(self.db.scalars(select(Expense).where(Expense.user_id == self.user_id,
                                                          Expense.date.between(a, b))
                                    .order_by(Expense.date, Expense.id)))

    @cached_property
    def payments(self) -> list[TaxPayment]:
        a, b = date(self.year, 1, 1), date(self.year + 1, 12, 31)
        return list(self.db.scalars(select(TaxPayment).where(TaxPayment.user_id == self.user_id,
                                                             TaxPayment.date.between(a, b))
                                    .order_by(TaxPayment.date)))

    @cached_property
    def bank(self) -> list[BankTransaction]:
        return list(self.db.scalars(select(BankTransaction).where(BankTransaction.user_id == self.user_id)
                                    .order_by(BankTransaction.date, BankTransaction.id)))

    # ----------------------------------------------------------------- vsote
    def _upto(self, d: date) -> bool:
        return d <= self.as_of

    @property
    def revenue_ytd(self) -> Decimal:
        return r2(sum((D(i.net) for i in self.invoices if self._upto(i.issue_date)), ZERO))

    @property
    def business_expenses(self) -> list[Expense]:
        return [e for e in self.expenses if not e.private_flag]

    @property
    def expenses_ytd(self) -> Decimal:
        return r2(sum((D(e.net) for e in self.business_expenses if self._upto(e.date)), ZERO))

    @property
    def received_ytd(self) -> Decimal:
        return r2(sum((D(i.paid_amount) for i in self.all_invoices
                       if i.paid_date and i.paid_date.year == self.year and self._upto(i.paid_date)), ZERO))

    def monthly_revenue(self) -> dict[int, Decimal]:
        out: dict[int, Decimal] = defaultdict(lambda: ZERO)
        for i in self.invoices:
            if self._upto(i.issue_date):
                out[i.issue_date.month] += D(i.net)
        return dict(out)

    def monthly_expenses(self) -> dict[int, Decimal]:
        out: dict[int, Decimal] = defaultdict(lambda: ZERO)
        for e in self.business_expenses:
            if self._upto(e.date):
                out[e.date.month] += D(e.net)
        return dict(out)

    def _payment_in_year(self, p: TaxPayment) -> bool:
        if p.period:
            return p.period.startswith(str(self.year))
        return p.date.year == self.year

    def paid(self, kind: str, period: str | None = None) -> Decimal:
        """Plačano za vrsto obveznosti (za točno obdobje ali za celo leto)."""
        return r2(sum((D(p.amount) for p in self.payments
                       if p.kind == kind and (p.period == period if period else self._payment_in_year(p))), ZERO))

    def paid_total_in_year(self) -> Decimal:
        return r2(sum((D(p.amount) for p in self.payments if p.date.year == self.year and self._upto(p.date)), ZERO))

    def vat_lines(self) -> list[VatLine]:
        lines = [VatLine(i.issue_date, D(i.net), D(i.vat), "out") for i in self.invoices]
        lines += [VatLine(e.date, D(e.net), D(e.vat), "in", e.vat_deductible and not e.private_flag)
                  for e in self.expenses]
        return lines

    def vat_periods(self):
        if not self.bp.vat_registered:
            return []
        reg = self.bp.vat_registration_date or self.bp.activity_start
        return vat_periods(self.year, reg, self.vat_lines(), D(self.bp.prev_year_turnover))

    def latest_balance(self) -> tuple[Decimal | None, date | None]:
        bal = self.db.scalar(select(BankBalance).where(BankBalance.user_id == self.user_id,
                                                       BankBalance.date <= self.as_of)
                             .order_by(BankBalance.date.desc(), BankBalance.id.desc()))
        if bal is None:
            if not self.bank:
                return None, None
            return r2(sum((D(t.amount) for t in self.bank if t.date <= self.as_of), ZERO)), self.as_of
        after = sum((D(t.amount) for t in self.bank if bal.date < t.date <= self.as_of), ZERO)
        return r2(D(bal.balance) + after), self.as_of
