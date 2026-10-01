from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TaxKind = Literal["prispevki", "akontacija", "ddv", "dohodnina", "drugo"]
Folder = Literal["racuni", "stroski", "FURS", "OPSV", "DDV", "pogodbe", "izpiski", "letni", "drugo"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth
class SetupIn(BaseModel):
    email: str
    password: str = Field(min_length=10)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Neveljaven e-naslov")
        return v.lower().strip()


class LoginIn(BaseModel):
    email: str
    password: str
    totp: str | None = None


class TokenOut(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"
    totp_required: bool = False


class TotpCode(BaseModel):
    code: str


class UserOut(ORM):
    id: int
    email: str
    totp_enabled: bool


# ---------------------------------------------------------------- profil
class ProfileIO(ORM):
    business_name: str = "Moj s.p."
    tax_number: str | None = None
    iban: str | None = None
    regime: Literal["normiran", "dejanski"] = "normiran"
    full_time: bool = True
    activity_start: date
    first_registration_date: date | None = None
    vat_registered: bool = True
    vat_registration_date: date | None = None
    prev_year_turnover: Decimal = Decimal(0)
    prev_year_insured_75: bool = False
    children: int = Field(0, ge=0, le=20)
    special_care_children: int = Field(0, ge=0, le=20)
    contribution_base_monthly: Decimal | None = None
    akontacija_annual: Decimal = Decimal(0)
    revenue_goal: Decimal = Decimal(90000)
    safety_buffer: Decimal = Decimal(2000)


# ---------------------------------------------------------------- računi / stroški / plačila
class InvoiceIn(BaseModel):
    number: str = Field(min_length=1, max_length=50)
    customer: str = ""
    customer_tax_number: str | None = None
    issue_date: date
    service_date: date | None = None
    due_date: date | None = None
    net: Decimal = Field(ge=0)
    vat_rate: Decimal = Decimal("0.22")
    vat: Decimal | None = None
    gross: Decimal | None = None
    vat_note: str | None = None
    paid_date: date | None = None
    paid_amount: Decimal = Decimal(0)
    notes: str | None = None
    document_id: int | None = None


class InvoiceOut(ORM, InvoiceIn):
    id: int
    vat: Decimal
    gross: Decimal


class ExpenseIn(BaseModel):
    supplier: str = ""
    supplier_tax_number: str | None = None
    invoice_number: str | None = None
    date: date
    net: Decimal | None = None
    vat: Decimal | None = None
    gross: Decimal | None = None
    vat_deductible: bool = True
    category: str | None = None
    private_flag: bool = False
    paid_date: date | None = None
    source: Literal["manual", "scan", "bank"] = "manual"
    notes: str | None = None
    document_id: int | None = None


class ExpenseOut(ORM, ExpenseIn):
    id: int
    net: Decimal
    vat: Decimal
    gross: Decimal


class PaymentIn(BaseModel):
    date: date
    kind: TaxKind
    period: str | None = None
    amount: Decimal = Field(gt=0)
    bank_tx_id: int | None = None
    notes: str | None = None


class PaymentOut(ORM, PaymentIn):
    id: int


class BalanceIn(BaseModel):
    date: date
    balance: Decimal


class BankTxOut(ORM):
    id: int
    date: date
    amount: Decimal
    counterparty: str
    counterparty_iban: str | None
    description: str
    reference: str | None
    category: str | None
    matched_invoice_id: int | None
    matched_expense_id: int | None


class BankTxPatch(BaseModel):
    category: str | None = None
    matched_invoice_id: int | None = None
    matched_expense_id: int | None = None
    tax_kind: TaxKind | None = None
    tax_period: str | None = None


class DocumentOut(ORM):
    id: int
    filename: str
    content_type: str
    size: int
    folder: str
    year: int
    uploaded_at: object
    bank_tx_id: int | None


class WhatIfIn(BaseModel):
    revenues: list[Decimal] = Field(default_factory=lambda: [Decimal(x) for x in (70000, 80000, 90000, 100000, 120000)],
                                    max_length=30)
    expense_ratio: Decimal | None = Decimal("0.10")
    expenses: Decimal | None = None
    simulate_pending: bool = False


class CalcIn(BaseModel):
    revenue: Decimal = Field(ge=0)
    expenses: Decimal = Field(Decimal(0), ge=0)
    investments: Decimal = Field(Decimal(0), ge=0)
    regime: Literal["profile", "normiran", "dejanski"] = "profile"
    simulate_pending: bool = False


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None
