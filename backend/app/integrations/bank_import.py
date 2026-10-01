"""Bančni uvoz: CSV (NLB, NKBM/OTP, SKB, Intesa, Revolut … — samodejno prepozna stolpce) in
ISO 20022 camt.053 XML (standardni izpisek slovenskih bank). Samodejna kategorizacija in povezava
prilivov z izdanimi računi."""
from __future__ import annotations

import csv
import hashlib
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from ..engines.mistakes import CATEGORY_HINTS, FURS_HINTS, PRIVATE_HINTS
from ..tax_engine.money import D, r2


@dataclass
class ParsedTx:
    date: date
    amount: Decimal
    counterparty: str = ""
    description: str = ""
    reference: str | None = None
    iban: str | None = None
    category: str | None = None
    tax_kind: str | None = None

    @property
    def fingerprint(self) -> str:
        raw = f"{self.date.isoformat()}|{self.amount}|{self.counterparty.strip().lower()}|" \
              f"{self.description.strip().lower()}|{(self.reference or '').strip()}"
        return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class ParseResult:
    transactions: list[ParsedTx] = field(default_factory=list)
    closing_balance: Decimal | None = None
    closing_date: date | None = None
    fmt: str = ""
    warnings: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ pretvorbe
def parse_amount(s: str) -> Decimal:
    s = (s or "").strip().replace(" ", "").replace(" ", "").replace("EUR", "").replace("€", "")
    if not s:
        raise InvalidOperation("prazen znesek")
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-()+")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    value = Decimal(s)
    return -value if neg else value


def parse_date(s: str) -> date:
    s = s.strip()
    for fmt in ("%d.%m.%Y", "%d. %m. %Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y", "%Y-%m-%dT%H:%M:%S", "%Y%m%d"):
        try:
            return datetime.strptime(s[:len(datetime.now().strftime(fmt))] if "T" in fmt else s, fmt).date()
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return date.fromisoformat(m.group(1))
    raise ValueError(f"Neprepoznan datum: {s}")


COLS = {
    "date": ["datum knjiženja", "datum knjizenja", "datum", "date", "booking date", "datum valute", "value date",
             "started date", "completed date"],
    "amount": ["znesek", "amount", "znesek v eur", "iznos"],
    "debit": ["v breme", "breme", "odliv", "debit", "izplačilo", "izplacilo"],
    "credit": ["v dobro", "dobro", "priliv", "credit", "vplačilo", "vplacilo"],
    "counterparty": ["naziv partnerja", "partner", "naziv", "prejemnik/plačnik", "prejemnik", "plačnik", "placnik",
                     "counterparty", "name", "naziv prejemnika", "naziv plačnika"],
    "description": ["namen plačila", "namen placila", "namen", "opis", "description", "purpose", "details"],
    "reference": ["sklic", "referenca", "reference", "sklic prejemnika"],
    "iban": ["iban", "račun partnerja", "racun partnerja", "trr", "iban partnerja"],
}


def _map_header(header: list[str]) -> dict[str, int]:
    norm = [h.strip().lower().replace("﻿", "") for h in header]
    out = {}
    for key, names in COLS.items():
        for name in names:
            if name in norm:
                out[key] = norm.index(name)
                break
    return out


def parse_csv(data: bytes) -> ParseResult:
    text = None
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), dialect))
    res = ParseResult(fmt="csv")
    header_idx = None
    for idx, row in enumerate(rows[:30]):
        cols = _map_header(row)
        if "date" in cols and ("amount" in cols or "debit" in cols or "credit" in cols):
            header_idx, mapping = idx, cols
            break
    if header_idx is None:
        raise ValueError("V CSV ni prepoznane glave (potrebna sta vsaj stolpca datum in znesek).")
    for row in rows[header_idx + 1:]:
        if not row or all(not c.strip() for c in row):
            continue
        try:
            def col(k):
                i = mapping.get(k)
                return row[i].strip() if i is not None and i < len(row) else ""
            d = parse_date(col("date"))
            if "amount" in mapping and col("amount"):
                amt = parse_amount(col("amount"))
            else:
                credit = parse_amount(col("credit")) if col("credit") else Decimal(0)
                debit = parse_amount(col("debit")) if col("debit") else Decimal(0)
                amt = abs(credit) - abs(debit)
            res.transactions.append(ParsedTx(d, r2(amt), col("counterparty"), col("description"),
                                             col("reference") or None, col("iban") or None))
        except (ValueError, InvalidOperation) as e:
            res.warnings.append(f"Vrstica preskočena: {';'.join(row)[:80]} ({e})")
    return res


def parse_camt053(data: bytes) -> ParseResult:
    root = ET.fromstring(data)
    ns = {"c": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {"c": ""}
    q = (lambda p: p.replace("c:", "c:") if ns["c"] else p.replace("c:", ""))

    def f(el, path):
        x = el.find(q(path), ns)
        return x.text.strip() if x is not None and x.text else ""

    res = ParseResult(fmt="camt.053")
    for stmt in root.iter(f"{{{ns['c']}}}Stmt" if ns["c"] else "Stmt"):
        for bal in stmt.findall(q("c:Bal"), ns):
            if f(bal, "c:Tp/c:CdOrPrtry/c:Cd") in ("CLBD", "CLAV"):
                amt = D(f(bal, "c:Amt"))
                if f(bal, "c:CdtDbtInd") == "DBIT":
                    amt = -amt
                d = f(bal, "c:Dt/c:Dt") or f(bal, "c:Dt/c:DtTm")[:10]
                if d and (res.closing_date is None or date.fromisoformat(d) >= res.closing_date):
                    res.closing_balance, res.closing_date = r2(amt), date.fromisoformat(d)
        for ntry in stmt.findall(q("c:Ntry"), ns):
            amt = D(f(ntry, "c:Amt"))
            credit = f(ntry, "c:CdtDbtInd") == "CRDT"
            d = f(ntry, "c:BookgDt/c:Dt") or f(ntry, "c:BookgDt/c:DtTm")[:10] or f(ntry, "c:ValDt/c:Dt")
            tx = ntry.find(q("c:NtryDtls/c:TxDtls"), ns)
            party, iban, desc, ref = "", None, "", None
            if tx is not None:
                side = "c:RltdPties/c:Dbtr" if credit else "c:RltdPties/c:Cdtr"
                party = f(tx, f"{side}/c:Nm") or f(tx, f"{side}/c:Pty/c:Nm")
                acct = "c:RltdPties/c:DbtrAcct/c:Id/c:IBAN" if credit else "c:RltdPties/c:CdtrAcct/c:Id/c:IBAN"
                iban = f(tx, acct) or None
                desc = " ".join(x.text.strip() for x in tx.findall(q("c:RmtInf/c:Ustrd"), ns) if x.text)
                ref = f(tx, "c:RmtInf/c:Strd/c:CdtrRefInf/c:Ref") or None
                desc = desc or f(tx, "c:AddtlTxInf")
            desc = desc or f(ntry, "c:AddtlNtryInf")
            res.transactions.append(ParsedTx(date.fromisoformat(d), r2(amt if credit else -amt), party, desc, ref, iban))
    return res


def parse(data: bytes, filename: str = "") -> ParseResult:
    head = data[:2000].decode("utf-8", errors="ignore")
    if filename.lower().endswith(".xml") or "camt.053" in head or "<BkToCstmrStmt" in head:
        return parse_camt053(data)
    return parse_csv(data)


# ------------------------------------------------------------------ kategorizacija
def categorize(tx: ParsedTx) -> ParsedTx:
    text = f"{tx.counterparty} {tx.description} {tx.reference or ''}".lower() + " "
    if tx.amount < 0 and any(h in text for h in FURS_HINTS):
        if "prispev" in text:
            tx.tax_kind = "prispevki"
        elif "akontac" in text:
            tx.tax_kind = "akontacija"
        elif "ddv" in text:
            tx.tax_kind = "ddv"
        elif "dohodnin" in text:
            tx.tax_kind = "dohodnina"
        else:
            tx.tax_kind = "drugo"
        tx.category = tx.tax_kind
        return tx
    if tx.amount > 0:
        tx.category = "prihodek"
        return tx
    for cat, hints in CATEGORY_HINTS.items():
        if any(h in text for h in hints):
            tx.category = cat
            return tx
    if any(h in text for h in PRIVATE_HINTS):
        tx.category = "zasebno?"
    return tx


def guess_period(tx: ParsedTx) -> str:
    """Prispevki/akontacija se plačujejo do 20. za pretekli mesec; DDV do konca meseca za pretekli mesec."""
    y, m = tx.date.year, tx.date.month - 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y}-{m:02d}"
