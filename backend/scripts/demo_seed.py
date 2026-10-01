"""Demo podatki za preizkus HericR (SINTETIČNI — ne uporabljaj na pravi bazi).

    HERICR_DATABASE_URL=sqlite:///./data/demo.db python -m scripts.demo_seed
Prijava: demo@hericr.si / demo-geslo-123
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.auth import hash_password
from app.db import SessionLocal, init_db
from app.models import BankBalance, BankTransaction, BusinessProfile, Expense, Invoice, TaxPayment, User
from app.tax_engine.money import r2

random.seed(28)


def main():
    init_db()
    db = SessionLocal()
    if db.scalar(select(func.count(User.id))):
        raise SystemExit("Baza že ima uporabnika — demo podatki se dodajo samo v prazno bazo.")
    u = User(email="demo@hericr.si", password_hash=hash_password("demo-geslo-123"))
    db.add(u)
    db.flush()
    db.add(BusinessProfile(user_id=u.id, business_name="Demo montaža, s.p.", regime="normiran", full_time=True,
                           activity_start=date(2025, 7, 10), vat_registered=True, vat_registration_date=date(2026, 1, 1),
                           prev_year_turnover=Decimal("58000"), prev_year_insured_75=False,
                           akontacija_annual=Decimal("2400"), revenue_goal=Decimal("90000"), safety_buffer=Decimal("2000")))
    customers = ["Gradbeništvo Novak d.o.o.", "Montaže Kranj d.o.o.", "Industrija Celje d.d.", "Strojna oprema Krajnc d.o.o."]
    n = 1
    for month in range(1, 10):
        for _ in range(random.randint(2, 3)):
            day = date(2026, month, random.randint(1, 26))
            net = r2(Decimal(random.randint(1800, 4200)))
            vat = r2(net * Decimal("0.22"))
            inv = Invoice(user_id=u.id, number=f"2026-{n}", customer=random.choice(customers), issue_date=day,
                          due_date=day + timedelta(days=15), net=net, vat=vat, gross=net + vat)
            if day < date(2026, 9, 1) or random.random() < 0.4:
                inv.paid_date, inv.paid_amount = day + timedelta(days=random.randint(5, 25)), net + vat
            db.add(inv)
            n += 1
    sup = [("Petrol d.d.", "gorivo", 85), ("Merkur trgovina d.o.o.", "orodje in material", 240), ("Würth d.o.o.", "orodje in material", 180),
           ("Telekom Slovenije d.d.", "telekomunikacije", 39), ("Adobe Systems", "programska oprema", 30)]
    for month in range(1, 10):
        for s, cat, base in sup:
            net = r2(Decimal(base) * Decimal(random.uniform(0.7, 1.4)))
            vat = r2(net * Decimal("0.22"))
            db.add(Expense(user_id=u.id, supplier=s, invoice_number=f"{s[:3].upper()}-{month}{random.randint(100, 999)}",
                           date=date(2026, month, random.randint(2, 27)), net=net, vat=vat, gross=net + vat, category=cat))
    db.add(Expense(user_id=u.id, supplier="Spar Slovenija d.o.o.", date=date(2026, 9, 12), net=Decimal("41.00"),
                   vat=Decimal("3.90"), gross=Decimal("44.90"), category="drugo"))
    for month in range(1, 9):
        due = date(2026, month + 1, 18)
        db.add(TaxPayment(user_id=u.id, date=due, kind="prispevki", period=f"2026-{month:02d}",
                          amount=Decimal("614.82") if month == 1 else Decimal("648.85") if month == 2 else Decimal("651.04")))
        db.add(TaxPayment(user_id=u.id, date=due, kind="akontacija", period=f"2026-{month:02d}", amount=Decimal("200.00")))
    db.commit()
    from app.engines.ledger import Ledger
    L = Ledger.load(db, u, 2026, date(2026, 9, 30))
    for vp in L.vat_periods():
        if vp.end < date(2026, 9, 1) and vp.payable > 0:
            db.add(TaxPayment(user_id=u.id, date=vp.due_date - timedelta(days=2), kind="ddv",
                              period=vp.start.strftime("%Y-%m"), amount=vp.payable))
    db.add(BankBalance(user_id=u.id, date=date(2026, 9, 30), balance=Decimal("18240.55"), source="manual"))
    db.add(BankTransaction(user_id=u.id, date=date(2026, 9, 28), amount=Decimal("1500.00"), counterparty="Neznan plačnik",
                           description="avans po dogovoru", fingerprint="demo-1"))
    db.commit()
    print("Demo podatki pripravljeni. Prijava: demo@hericr.si / demo-geslo-123")


if __name__ == "__main__":
    main()
