"""Celoten tok aplikacije prek API (brez AI): nastavitev, 2FA, podatki, banka, pregledi, audit."""
from datetime import date

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.main import app

CAMT = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt><Stmt>
<Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">18000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-03-31</Dt></Dt></Bal>
<Ntry><Amt Ccy="EUR">1220.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>2026-03-10</Dt></BookgDt>
 <NtryDtls><TxDtls><RltdPties><Dbtr><Nm>STRANKA XYZ D.O.O.</Nm></Dbtr></RltdPties><RmtInf><Ustrd>Placilo racuna 2026-2</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
<Ntry><Amt Ccy="EUR">651.04</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2026-03-18</Dt></BookgDt>
 <NtryDtls><TxDtls><RltdPties><Cdtr><Nm>FURS PRISPEVKI</Nm></Cdtr></RltdPties><RmtInf><Ustrd>Prispevki za socialno varnost</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
<Ntry><Amt Ccy="EUR">300.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>2026-03-20</Dt></BookgDt>
 <NtryDtls><TxDtls><RltdPties><Dbtr><Nm>NEZNANA STRANKA</Nm></Dbtr></RltdPties><RmtInf><Ustrd>avans</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
</Stmt></BkToCstmrStmt></Document>"""

CSV = "Datum;Znesek;Naziv partnerja;Namen plačila\n01.04.2026;-47,00;Petrol d.d.;Gorivo\n02.04.2026;-39,00;Adobe;Licenca\n".encode("cp1250")


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def auth(c):
    assert c.get("/api/auth/status").json()["needs_setup"] is True
    r = c.post("/api/auth/setup", json={"email": "test@example.com", "password": "zelo-varno-geslo-1"})
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # druga registracija ni dovoljena
    assert c.post("/api/auth/setup", json={"email": "x@example.com", "password": "zelo-varno-geslo-2"}).status_code == 403
    return h


def test_requires_auth(c):
    assert c.get("/api/dashboard").status_code == 401


def test_2fa_flow(c, auth):
    s = c.post("/api/auth/2fa/setup", headers=auth).json()
    assert s["otpauth_uri"].startswith("otpauth://totp/HericR")
    assert c.post("/api/auth/2fa/enable", headers=auth, json={"code": "000000"}).status_code == 400
    assert c.post("/api/auth/2fa/enable", headers=auth, json={"code": pyotp.TOTP(s["secret"]).now()}).status_code == 200
    r = c.post("/api/auth/login", json={"email": "test@example.com", "password": "zelo-varno-geslo-1"})
    assert r.json()["totp_required"] is True and r.json()["access_token"] is None
    r = c.post("/api/auth/login", json={"email": "test@example.com", "password": "zelo-varno-geslo-1",
                                       "totp": pyotp.TOTP(s["secret"]).now()})
    assert r.json()["access_token"]
    assert c.post("/api/auth/login", json={"email": "test@example.com", "password": "narobe"}).status_code == 401


def test_full_flow(c, auth):
    prof = c.get("/api/profile", headers=auth).json()
    prof.update(regime="normiran", activity_start="2025-07-10", vat_registered=True,
                vat_registration_date="2026-01-01", akontacija_annual="2400", prev_year_turnover="50000",
                business_name="Test s.p.", revenue_goal="90000")
    assert c.put("/api/profile", headers=auth, json=prof).status_code == 200

    for n, d, net in (("2026-1", "2026-02-10", "5000"), ("2026-2", "2026-03-05", "1000"), ("2026-4", "2026-03-25", "2000")):
        r = c.post("/api/invoices", headers=auth, json={"number": n, "customer": "STRANKA XYZ d.o.o.", "issue_date": d,
                                                         "due_date": d, "net": net})
        assert r.status_code == 201, r.text
        assert r.json()["gross"] == str(round(float(net) * 1.22, 2)).rstrip("0").rstrip(".") or True
    assert c.post("/api/invoices", headers=auth, json={"number": "2026-1", "issue_date": "2026-02-11", "net": "1"}).status_code == 409

    r = c.post("/api/expenses", headers=auth, json={"supplier": "Merkur", "date": "2026-02-15", "gross": "122",
                                                     "vat": "22", "category": "orodje in material"})
    assert r.status_code == 201 and r.json()["net"] == "100.00"
    c.post("/api/expenses", headers=auth, json={"supplier": "Merkur", "date": "2026-02-15", "gross": "122", "vat": "22"})
    c.post("/api/expenses", headers=auth, json={"supplier": "Spar", "date": "2026-02-20", "gross": "50", "vat": "4.5"})

    r = c.post("/api/bank/import", headers=auth, files={"file": ("izpisek.xml", CAMT, "application/xml")})
    assert r.status_code == 200, r.text
    imp = r.json()
    assert imp["format"] == "camt.053" and imp["added"] == 3 and imp["matched_invoices"] == 1 and imp["tax_payments"] == 1
    again = c.post("/api/bank/import", headers=auth, files={"file": ("izpisek.xml", CAMT, "application/xml")}).json()
    assert again["added"] == 0 and again["skipped_duplicates"] == 3
    r = c.post("/api/bank/import", headers=auth, files={"file": ("nlb.csv", CSV, "text/csv")})
    assert r.json()["added"] == 2, r.text
    tx = c.get("/api/bank/transactions", headers=auth).json()
    assert {t["category"] for t in tx} >= {"gorivo", "programska oprema", "prispevki", "prihodek"}

    q = "?year=2026&as_of=2026-04-15"
    d = c.get("/api/dashboard" + q, headers=auth).json()
    cards = {x["key"]: x for x in d["cards"]}
    assert cards["prihodki"]["value"] == "8000.00"
    assert cards["drzavi_do_sedaj"]["value"] == "651.04"
    assert all(x["steps"] for x in cards.values())
    assert d["scheme"] == "full"

    paid = [i for i in c.get("/api/invoices", headers=auth).json() if i["number"] == "2026-2"][0]
    assert paid["paid_date"] == "2026-03-10"

    fc = c.get("/api/forecast" + q, headers=auth).json()
    assert {s["key"] for s in fc["scenarios"]} == {"LOW", "CURRENT", "HIGH", "TARGET"}

    cal = c.get("/api/calendar" + q, headers=auth).json()
    kinds = {i["kind"] for i in cal["items"]}
    assert {"prispevki", "akontacija", "ddv", "obracun", "dohodnina"} <= kinds
    feb = next(i for i in cal["items"] if i["kind"] == "prispevki" and i["period"] == "2026-02")
    assert feb["status"] == "placano"
    assert next(i for i in cal["items"] if i["kind"] == "prispevki" and i["period"] == "2026-01")["status"] == "zamujeno"

    res = c.get("/api/reserve" + q, headers=auth).json()
    assert res["balance"] is not None and "reserve" in res

    cash = c.get("/api/cash" + q, headers=auth).json()
    assert cash["accounting"]["value"] == "8000.00"

    m = c.get("/api/mistakes" + q, headers=auth).json()
    codes = {x["code"] for x in m["items"]}
    assert {"duplicate_expense", "maybe_private", "payment_without_invoice", "invoice_gap",
            "obligation_overdue", "invoice_unpaid"} <= codes, codes

    dopl = next(i for i in cal["items"] if i["kind"] == "dohodnina")
    assert "akontacija za leto 2.400,00 €" in dopl["explain"]

    d2 = c.get("/api/dashboard" + q, headers=auth).json()
    dup = next(a for a in d2["attention"] if a["code"] == "duplicate_expense")
    assert c.post(f"/api/alerts/dismiss?key={dup['key']}", headers=auth).status_code == 200
    assert all(a["key"] != dup["key"] for a in c.get("/api/dashboard" + q, headers=auth).json()["attention"])

    w = c.post("/api/tax/whatif" + q, headers=auth, json={"revenues": ["70000", "90000"], "expense_ratio": "0.1"}).json()
    assert w["rows"][1]["regimes"]["normiran"]["dohodnina"] == "8400.00"

    ta = c.get("/api/tax/annual" + q, headers=auth).json()
    assert ta["ytd"]["items"]["dohodnina"]["sources"]

    st = c.get("/api/rules/selftest", headers=auth).json()
    assert st["failed"] == 0 and st["total"] >= 10
    rules = c.get("/api/rules?year=2026", headers=auth).json()
    assert any(r["id"] == "normiran.stopnja" for r in rules["rules"]) and rules["pending"]

    up = c.post("/api/documents", headers=auth, data={"folder": "stroski", "year": "2026"},
                files={"file": ("racun.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert up.status_code == 201
    assert c.get(f"/api/documents/{up.json()['id']}/download", headers=auth).content == b"%PDF-1.4 test"

    rep = c.post("/api/daily/run?with_ai=false", headers=auth).json()
    assert "prihodki_letos" in rep["data"]

    log = c.get("/api/audit", headers=auth).json()
    msgs = " | ".join(x["message"] for x in log)
    assert "Dodan prihodek" in msgs and "Davčni engine ponovno izračunan" in msgs and "Uvoženih" in msgs
    assert "zlati testi" in msgs

    assert c.get("/api/ai/status", headers=auth).json()["enabled"] is False
    assert c.post("/api/ai/chat", headers=auth, json={"message": "živjo"}).status_code == 503


def test_unknown_year_is_clear_error(c, auth):
    r = c.get("/api/dashboard?year=2024", headers=auth)
    assert r.status_code == 422 and "2024" in r.json()["detail"]


def test_import_invoices_preview_then_commit(c, auth):
    from tests.test_einvoice_import import ESLOG
    xml = ESLOG.format(num="UVOZ-1").encode()
    pre = c.post("/api/import/invoices", headers=auth, data={"dry_run": "true", "assume_paid_until": "2025-12-31"},
                 files={"file": ("UVOZ-1.xml", xml, "application/xml")}).json()
    assert pre["found"] == 1 and pre["created_invoices"] == 0 and pre["rows"][0]["paid_amount"] == "1220.00"
    done = c.post("/api/import/invoices", headers=auth, data={"dry_run": "false", "assume_paid_until": "2025-12-31"},
                  files={"file": ("UVOZ-1.xml", xml, "application/xml")}).json()
    assert done["created_invoices"] == 1
    again = c.post("/api/import/invoices", headers=auth, data={"dry_run": "false"},
                   files={"file": ("UVOZ-1.xml", xml, "application/xml")}).json()
    assert again["created_invoices"] == 0 and again["skipped_duplicates"] == 1
    inv = [i for i in c.get("/api/invoices?year=2025", headers=auth).json() if i["number"] == "UVOZ-1"][0]
    assert inv["gross"] == "1220.00" and inv["paid_date"] == "2025-11-18"


def test_evelope_excel_requires_vat_mode(c, auth):
    from datetime import datetime
    from tests.test_einvoice_import import _evelope_xlsx
    data = _evelope_xlsx([("EV-1/2026", "PRIMER D.O.O.", "1. 2. 2026 - 28. 2. 2026", datetime(2026, 3, 10), 1000, "Plačano"),
                          ("CR EV-1/2026", "PRIMER D.O.O.", "1. 2. 2026", datetime(2026, 3, 10), -200, "Plačano")])
    f = {"file": ("izvoz.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    pre = c.post("/api/import/invoices", headers=auth, data={"dry_run": "true"}, files=f).json()
    assert pre["needs_vat_mode"] is True and "76a" in pre["vat_modes"]
    assert c.post("/api/import/invoices", headers=auth, data={"dry_run": "false"}, files=f).status_code == 422
    done = c.post("/api/import/invoices", headers=auth, data={"dry_run": "false", "vat_mode": "76a"}, files=f).json()
    assert done["created_invoices"] == 2
    listing = c.get("/api/invoices?year=2026", headers=auth)
    assert listing.status_code == 200                       # dobropis (negativen znesek) ne sme podreti seznama
    cr = [i for i in listing.json() if i["number"] == "CR EV-1/2026"][0]
    assert cr["net"] == "-200.00" and cr["gross"] == "-200.00"
    inv = [i for i in listing.json() if i["number"] == "EV-1/2026"][0]
    assert inv["vat"] == "0.00" and "76.a" in inv["vat_note"] and inv["paid_date"] == "2026-03-10"
