"""Document Vault, skener računov, uvoz FURS dokumentov, bančni uvoz."""
import hashlib
import re
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..auth import current_user
from ..db import get_db
from ..integrations import bank_import, einvoice_import, furs_import, invoice_scanner
from ..integrations.claude_client import AIUnavailable, friendly_error
from ..models import BankBalance, BankTransaction, Document, Expense, Invoice, TaxPayment, User
from ..schemas import BankTxOut, BankTxPatch, DocumentOut, ExpenseIn, ExpenseOut
from ..storage import get_storage
from ..tax_engine import fmt_eur
from ..tax_engine.money import D, r2
from .data_routes import _own, create_expense

router = APIRouter(tags=["files"])
MAX_BYTES = 25 * 1024 * 1024
FOLDERS = {"racuni", "stroski", "FURS", "OPSV", "DDV", "pogodbe", "izpiski", "letni", "drugo"}


def _store(db: Session, user: User, data: bytes, filename: str, content_type: str, folder: str, year: int) -> Document:
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Datoteka je večja od 25 MB")
    if folder not in FOLDERS:
        raise HTTPException(400, f"Neznana mapa {folder}")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)[-120:] or "dokument"
    key = f"{user.id}/{year}/{folder}/{uuid.uuid4().hex}_{safe}"
    get_storage().put(key, data, content_type)
    doc = Document(user_id=user.id, filename=filename, content_type=content_type or "application/octet-stream",
                   size=len(data), storage_key=key, sha256=hashlib.sha256(data).hexdigest(), folder=folder, year=year)
    db.add(doc)
    db.flush()
    audit.log(db, user.id, "upload", f"Naložen dokument {filename} v {year}/{folder}", "document", doc.id)
    return doc


# ---------------------------------------------------------------- dokumenti
@router.get("/documents", response_model=list[DocumentOut])
def list_documents(year: int | None = None, folder: str | None = None, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    q = select(Document).where(Document.user_id == user.id)
    if year:
        q = q.where(Document.year == year)
    if folder:
        q = q.where(Document.folder == folder)
    return list(db.scalars(q.order_by(Document.uploaded_at.desc())))


@router.post("/documents", response_model=DocumentOut, status_code=201)
async def upload_document(file: UploadFile = File(...), folder: str = Form("stroski"), year: int | None = Form(None),
                          expense_id: int | None = Form(None), invoice_id: int | None = Form(None),
                          bank_tx_id: int | None = Form(None), user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    data = await file.read()
    doc = _store(db, user, data, file.filename or "dokument", file.content_type or "", folder, year or date.today().year)
    if expense_id:
        _own(db, Expense, expense_id, user).document_id = doc.id
    if invoice_id:
        _own(db, Invoice, invoice_id, user).document_id = doc.id
    if bank_tx_id:
        _own(db, BankTransaction, bank_tx_id, user)
        doc.bank_tx_id = bank_tx_id
    db.commit()
    return doc


@router.get("/documents/{did}/download")
def download_document(did: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = _own(db, Document, did, user)
    data = get_storage().get(doc.storage_key)
    return Response(data, media_type=doc.content_type,
                    headers={"Content-Disposition": f'inline; filename="{re.sub(r"[^A-Za-z0-9._-]", "_", doc.filename)}"'})


@router.delete("/documents/{did}", status_code=204)
def delete_document(did: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = _own(db, Document, did, user)
    audit.log(db, user.id, "delete", f"Izbrisan dokument {doc.filename}", "document", doc.id)
    get_storage().delete(doc.storage_key)
    db.delete(doc)
    db.commit()


# ---------------------------------------------------------------- skener računov
@router.post("/scan/{did}")
def scan_document(did: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = _own(db, Document, did, user)
    try:
        out = invoice_scanner.scan(get_storage().get(doc.storage_key), doc.content_type)
    except AIUnavailable as e:
        raise HTTPException(503, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, friendly_error(e)) from e
    out["document_id"] = doc.id
    return out


@router.post("/scan/confirm", response_model=ExpenseOut, status_code=201)
def confirm_scan(body: ExpenseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    body.source = "scan"
    return create_expense(body, user, db)


# ---------------------------------------------------------------- FURS dokumenti
@router.post("/furs/import")
async def furs_import_route(file: UploadFile = File(...), user: User = Depends(current_user),
                            db: Session = Depends(get_db)):
    data = await file.read()
    try:
        result = furs_import.import_pdf(data)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    pf = result["document"].get("period_from")
    year = int(pf[:4]) if pf else date.today().year
    doc = _store(db, user, data, file.filename or "furs.pdf", "application/pdf", "FURS", year)
    audit.log(db, user.id, "furs_import", f"Uvožen FURS dokument {result['document']['doc_type']} — engine vs FURS: "
              f"{sum(c['match'] for c in result['checks'])}/{len(result['checks'])} ujemanj", "document", doc.id)
    db.commit()
    result["document_id"] = doc.id
    return result


# ---------------------------------------------------------------- banka
@router.post("/bank/import")
async def bank_import_route(file: UploadFile = File(...), user: User = Depends(current_user),
                            db: Session = Depends(get_db)):
    data = await file.read()
    try:
        parsed = bank_import.parse(data, file.filename or "")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"Izpiska ni mogoče prebrati: {e}") from e
    batch = uuid.uuid4().hex[:12]
    existing = set(db.scalars(select(BankTransaction.fingerprint).where(BankTransaction.user_id == user.id)))
    unpaid = list(db.scalars(select(Invoice).where(Invoice.user_id == user.id)))
    added = matched = tax = 0
    for ptx in parsed.transactions:
        fp = ptx.fingerprint
        if fp in existing:
            continue
        existing.add(fp)
        bank_import.categorize(ptx)
        tx = BankTransaction(user_id=user.id, date=ptx.date, amount=ptx.amount, counterparty=ptx.counterparty,
                             counterparty_iban=ptx.iban, description=ptx.description, reference=ptx.reference,
                             category=ptx.category, import_batch=batch, fingerprint=fp)
        db.add(tx)
        db.flush()
        added += 1
        if ptx.amount > 0:
            inv = _match_invoice(ptx, unpaid)
            if inv is not None:
                tx.matched_invoice_id = inv.id
                inv.paid_amount = D(inv.paid_amount) + ptx.amount
                inv.paid_date = ptx.date
                matched += 1
        elif ptx.tax_kind:
            db.add(TaxPayment(user_id=user.id, date=ptx.date, kind=ptx.tax_kind, period=bank_import.guess_period(ptx),
                              amount=-ptx.amount, bank_tx_id=tx.id, notes="samodejno iz bančnega izpiska"))
            tax += 1
    if parsed.closing_balance is not None:
        db.add(BankBalance(user_id=user.id, date=parsed.closing_date, balance=parsed.closing_balance, source="import"))
    doc = _store(db, user, data, file.filename or "izpisek", file.content_type or "text/plain", "izpiski",
                 parsed.transactions[0].date.year if parsed.transactions else date.today().year)
    audit.log(db, user.id, "bank_import", f"Uvoženih {added} transakcij ({parsed.fmt}), povezanih {matched} računov, "
              f"{tax} plačil FURS", "document", doc.id)
    db.commit()
    return {"format": parsed.fmt, "added": added, "skipped_duplicates": len(parsed.transactions) - added,
            "matched_invoices": matched, "tax_payments": tax,
            "closing_balance": None if parsed.closing_balance is None else str(parsed.closing_balance),
            "warnings": parsed.warnings[:20]}


def _match_invoice(ptx, invoices: list[Invoice]) -> Invoice | None:
    text = f"{ptx.description} {ptx.reference or ''}".lower()
    open_inv = [i for i in invoices if D(i.gross) - D(i.paid_amount) > Decimal("0.01")]
    same_amount = [i for i in open_inv if abs(D(i.gross) - D(i.paid_amount) - ptx.amount) <= Decimal("0.01")]
    for i in same_amount:
        if i.number.lower() in text:
            return i
    for i in same_amount:
        if i.customer and i.customer.lower()[:10] in ptx.counterparty.lower():
            return i
    return same_amount[0] if len(same_amount) == 1 else None


@router.get("/bank/transactions", response_model=list[BankTxOut])
def list_transactions(year: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(BankTransaction).where(BankTransaction.user_id == user.id)
    if year:
        q = q.where(BankTransaction.date.between(date(year, 1, 1), date(year, 12, 31)))
    return list(db.scalars(q.order_by(BankTransaction.date.desc(), BankTransaction.id.desc())))


@router.patch("/bank/transactions/{tid}", response_model=BankTxOut)
def patch_transaction(tid: int, body: BankTxPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    tx = _own(db, BankTransaction, tid, user)
    before = audit.snapshot(tx)
    if body.category is not None:
        tx.category = body.category
    if body.matched_invoice_id is not None:
        inv = _own(db, Invoice, body.matched_invoice_id, user)
        tx.matched_invoice_id = inv.id
        if tx.amount > 0:
            inv.paid_amount = D(inv.paid_amount) + tx.amount
            inv.paid_date = tx.date
    if body.matched_expense_id is not None:
        exp = _own(db, Expense, body.matched_expense_id, user)
        tx.matched_expense_id = exp.id
        exp.paid_date = tx.date
    if body.tax_kind is not None and tx.amount < 0:
        tx.category = body.tax_kind
        exists = db.scalar(select(TaxPayment).where(TaxPayment.bank_tx_id == tx.id))
        if exists is None:
            db.add(TaxPayment(user_id=user.id, date=tx.date, kind=body.tax_kind, amount=-tx.amount, bank_tx_id=tx.id,
                              period=body.tax_period or bank_import.guess_period(
                                  bank_import.ParsedTx(tx.date, tx.amount))))
        else:
            exists.kind = body.tax_kind
            if body.tax_period:
                exists.period = body.tax_period
    audit.log(db, user.id, "update", f"Razporejena transakcija {tx.date.isoformat()} {fmt_eur(tx.amount)}",
              "bank", tx.id, before, audit.snapshot(tx))
    db.commit()
    return tx


# ---------------------------------------------------------------- uvoz računov za nazaj (Evelope, e-računi)
def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


@router.post("/import/invoices")
async def import_invoices(file: UploadFile = File(...), kind: str = Form("auto"), dry_run: bool = Form(True),
                          assume_paid_until: date | None = Form(None), vat_mode: str = Form(""),
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Uvoz izdanih (ali prejetih) računov iz izvoza Evelope / drugega programa.
    dry_run=true vrne predogled; dry_run=false shrani. Podvojeni računi se preskočijo."""
    from ..engines.ledger import ensure_profile
    if kind not in ("auto", "issued", "received"):
        raise HTTPException(400, "kind mora biti auto, issued ali received")
    data = await file.read()
    if len(data) > 60 * 1024 * 1024:
        raise HTTPException(413, "Datoteka je večja od 60 MB")
    try:
        bundle = einvoice_import.parse_file(data, file.filename or "uvoz")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"Datoteke ni mogoče prebrati: {e}") from e
    needs_vat_mode = any(not i.vat_known for i in bundle.invoices)
    if needs_vat_mode and vat_mode:
        try:
            for i in bundle.invoices:
                einvoice_import.apply_vat_mode(i, vat_mode)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
    elif needs_vat_mode and not dry_run:
        raise HTTPException(422, "Izvoz nima ločenega DDV — izberi način DDV (nezavezanec / 76.a / vključen DDV).")
    bp = ensure_profile(db, user)
    me = _digits(bp.tax_number)
    existing_issued = {n.lower() for n in db.scalars(select(Invoice.number).where(Invoice.user_id == user.id))}
    existing_received = {(s.lower(), (n or "").lower()) for s, n in db.execute(
        select(Expense.supplier, Expense.invoice_number).where(Expense.user_id == user.id))}
    rows, by_year = [], {}
    created_inv = created_exp = skipped = 0
    for inv in bundle.invoices:
        direction = kind
        if kind == "auto":
            if me and me in _digits(inv.seller_tax):
                direction = "issued"
            elif me and me in _digits(inv.buyer_tax):
                direction = "received"
            else:
                direction = "issued"
        dup = (inv.number.lower() in existing_issued) if direction == "issued" else \
            ((inv.seller_name.lower(), inv.number.lower()) in existing_received)
        paid_amount, paid_date = inv.paid_amount, inv.paid_date
        if paid_date and paid_date > date.today():
            paid_date = date.today()   # ocenjen datum plačila ne sme biti v prihodnosti
        if direction == "issued" and paid_amount is None and assume_paid_until and \
                (inv.due_date or inv.issue_date) <= assume_paid_until:
            paid_amount, paid_date = inv.gross, inv.due_date or inv.issue_date
        row = inv.to_dict() | {"direction": direction, "duplicate": dup,
                               "paid_amount": None if paid_amount is None else str(paid_amount),
                               "paid_date": None if paid_date is None else paid_date.isoformat()}
        rows.append(row)
        if dup:
            skipped += 1
            continue
        y = by_year.setdefault(str(inv.issue_date.year), {"issued_net": Decimal(0), "received_net": Decimal(0), "count": 0})
        y["issued_net" if direction == "issued" else "received_net"] += inv.net
        y["count"] += 1
        if dry_run:
            continue
        doc_id = None
        if inv.pdf_name and inv.pdf_name in bundle.pdfs:
            doc = _store(db, user, bundle.pdfs[inv.pdf_name], inv.pdf_name.split("/")[-1], "application/pdf",
                         "racuni" if direction == "issued" else "stroski", inv.issue_date.year)
            doc_id = doc.id
        if direction == "issued":
            vat_rate = inv.vat_rate if inv.vat_rate is not None else (
                (inv.vat / inv.net).quantize(Decimal("0.0001")) if inv.net else Decimal(0))
            db.add(Invoice(user_id=user.id, number=inv.number, customer=inv.buyer_name, customer_tax_number=inv.buyer_tax,
                           issue_date=inv.issue_date, service_date=inv.service_date, due_date=inv.due_date, net=inv.net,
                           vat_rate=vat_rate, vat=inv.vat, gross=inv.gross, paid_date=paid_date,
                           paid_amount=paid_amount or 0, document_id=doc_id,
                           vat_note=("DDV ni obračunan v skladu s 76.a členom ZDDV-1" if vat_mode == "76a"
                                     else "nezavezanec za DDV" if vat_mode == "nezavezanec" and inv.vat == 0 else None),
                           notes="; ".join(x for x in (f"uvoz: {inv.source}", "dobropis" if inv.credit_note else "",
                                                       inv.note) if x)))
            existing_issued.add(inv.number.lower())
            created_inv += 1
        else:
            db.add(Expense(user_id=user.id, supplier=inv.seller_name, supplier_tax_number=inv.seller_tax,
                           invoice_number=inv.number, date=inv.issue_date, net=inv.net, vat=inv.vat, gross=inv.gross,
                           source="manual", document_id=doc_id, notes=f"uvoz: {inv.source}"))
            existing_received.add((inv.seller_name.lower(), inv.number.lower()))
            created_exp += 1
    checks = []
    for y, v in sorted(by_year.items()):
        if int(y) == date.today().year - 1 and bp.prev_year_turnover and v["issued_net"]:
            diff = v["issued_net"] - D(bp.prev_year_turnover)
            checks.append({"label": f"Prihodki {y}: uvoz vs davčni obračun (nastavitve)",
                           "import": str(r2(v["issued_net"])), "profile": str(r2(D(bp.prev_year_turnover))),
                           "match": abs(diff) <= Decimal("1"), "difference": str(r2(diff))})
    if not dry_run:
        audit.log(db, user.id, "invoice_import", f"Uvoz računov ({', '.join(sorted(bundle.formats))}): "
                  f"{created_inv} izdanih, {created_exp} prejetih, {skipped} podvojenih preskočenih")
        db.commit()
    return {"dry_run": dry_run, "formats": sorted(bundle.formats), "found": len(bundle.invoices),
            "created_invoices": created_inv, "created_expenses": created_exp, "skipped_duplicates": skipped,
            "needs_vat_mode": needs_vat_mode and not vat_mode, "vat_modes": einvoice_import.VAT_MODES,
            "vat_mode": vat_mode or None,
            "pdfs": len(bundle.pdfs), "by_year": {y: {k: str(r2(val)) if isinstance(val, Decimal) else val
                                                      for k, val in v.items()} for y, v in by_year.items()},
            "checks": checks, "warnings": bundle.warnings[:50], "rows": rows[:300]}
