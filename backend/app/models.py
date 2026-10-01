"""Podatkovni model HericR. Denar: Numeric(14,2), nikoli float."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Money = Numeric(14, 2)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    profile: Mapped["BusinessProfile"] = relationship(back_populates="user", uselist=False)


class BusinessProfile(Base):
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    business_name: Mapped[str] = mapped_column(String(255), default="Moj s.p.")
    tax_number: Mapped[str | None] = mapped_column(String(20))
    iban: Mapped[str | None] = mapped_column(String(40))
    regime: Mapped[str] = mapped_column(String(20), default="normiran")
    full_time: Mapped[bool] = mapped_column(Boolean, default=True)
    activity_start: Mapped[date] = mapped_column(Date, default=date(2026, 10, 1))
    first_registration_date: Mapped[date | None] = mapped_column(Date)
    vat_registered: Mapped[bool] = mapped_column(Boolean, default=True)
    vat_registration_date: Mapped[date | None] = mapped_column(Date)
    prev_year_turnover: Mapped[Decimal] = mapped_column(Money, default=0)   # prihodki preteklega leta
    prev_year_insured_75: Mapped[bool] = mapped_column(Boolean, default=False)  # lani ≥ 75 % polno zavarovan
    children: Mapped[int] = mapped_column(Integer, default=0)
    special_care_children: Mapped[int] = mapped_column(Integer, default=0)
    contribution_base_monthly: Mapped[Decimal | None] = mapped_column(Money)
    akontacija_annual: Mapped[Decimal] = mapped_column(Money, default=0)
    revenue_goal: Mapped[Decimal] = mapped_column(Money, default=90000)
    safety_buffer: Mapped[Decimal] = mapped_column(Money, default=2000)
    user: Mapped[User] = relationship(back_populates="profile")


class Invoice(Base):
    """Izdani račun (prihodek)."""
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    number: Mapped[str] = mapped_column(String(50))
    customer: Mapped[str] = mapped_column(String(255), default="")
    customer_tax_number: Mapped[str | None] = mapped_column(String(30))
    issue_date: Mapped[date] = mapped_column(Date, index=True)
    service_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    net: Mapped[Decimal] = mapped_column(Money)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.22"))
    vat: Mapped[Decimal] = mapped_column(Money, default=0)
    gross: Mapped[Decimal] = mapped_column(Money)
    vat_note: Mapped[str | None] = mapped_column(String(255))  # npr. obrnjena davčna obveznost
    paid_date: Mapped[date | None] = mapped_column(Date)
    paid_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "number", name="uq_invoice_number"),)


class Expense(Base):
    """Prejeti račun / strošek."""
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    supplier: Mapped[str] = mapped_column(String(255), default="")
    supplier_tax_number: Mapped[str | None] = mapped_column(String(30))
    invoice_number: Mapped[str | None] = mapped_column(String(80))
    date: Mapped[date] = mapped_column(Date, index=True)
    net: Mapped[Decimal] = mapped_column(Money)
    vat: Mapped[Decimal] = mapped_column(Money, default=0)
    gross: Mapped[Decimal] = mapped_column(Money)
    vat_deductible: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[str | None] = mapped_column(String(60))
    private_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    paid_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | scan | bank
    notes: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaxPayment(Base):
    """Plačilo državi: prispevki, akontacija, DDV, dohodnina."""
    __tablename__ = "tax_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(20))          # prispevki | akontacija | ddv | dohodnina | drugo
    period: Mapped[str | None] = mapped_column(String(20))  # npr. 2026-10 ali 2026-Q4 ali 2026
    amount: Mapped[Decimal] = mapped_column(Money)
    bank_tx_id: Mapped[int | None] = mapped_column(ForeignKey("bank_transactions.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Money)          # + priliv, − odliv
    counterparty: Mapped[str] = mapped_column(String(255), default="")
    counterparty_iban: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text, default="")
    reference: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(60))
    matched_invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"))
    matched_expense_id: Mapped[int | None] = mapped_column(ForeignKey("expenses.id", ondelete="SET NULL"))
    import_batch: Mapped[str | None] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("user_id", "fingerprint", name="uq_bank_tx_fp"),)


class BankBalance(Base):
    __tablename__ = "bank_balances"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    balance: Mapped[Decimal] = mapped_column(Money)
    source: Mapped[str] = mapped_column(String(20), default="manual")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    folder: Mapped[str] = mapped_column(String(30), default="stroski")
    year: Mapped[int] = mapped_column(Integer, index=True)
    bank_tx_id: Mapped[int | None] = mapped_column(ForeignKey("bank_transactions.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    action: Mapped[str] = mapped_column(String(40))
    entity: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    severity: Mapped[str] = mapped_column(String(10))   # info | warning | error
    code: Mapped[str] = mapped_column(String(60))
    key: Mapped[str] = mapped_column(String(120))       # stabilen ključ (brez podvajanja)
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text, default="")
    entity: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)  # uporabnik je ročno označil kot rešeno
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_alert_key"),)


class DailyReport(Base):
    __tablename__ = "daily_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    data: Mapped[dict] = mapped_column(JSON)
    ai_text: Mapped[str | None] = mapped_column(Text)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="Pogovor")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatMessage(Base):
    """Append-only zgodovina (vsebina bloka se shrani nespremenjena — potrebno za thinking bloke)."""
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[list] = mapped_column(JSON)
    visible_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    """Sistemske nastavitve (npr. hash pravil za zaznavo sprememb)."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
