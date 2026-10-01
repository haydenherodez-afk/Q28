"""Uvoz računov za nazaj (Evelope izvoz): eSLOG 2.0, UBL, ZIP ovojnica s PDF, Excel."""
import io
import zipfile
from datetime import date
from decimal import Decimal

from app.integrations.einvoice_import import parse_file

ESLOG = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:eslog:2.00"><M_INVOIC Id="data">
 <S_BGM><C_C002><D_1001>380</D_1001></C_C002><C_C106><D_1004>{num}</D_1004></C_C106></S_BGM>
 <S_DTM><C_C507><D_2005>137</D_2005><D_2380>2025-11-03</D_2380></C_C507></S_DTM>
 <S_DTM><C_C507><D_2005>35</D_2005><D_2380>2025-10-31</D_2380></C_C507></S_DTM>
 <G_SG2><S_NAD><D_3035>SE</D_3035><C_C080><D_3036>Moj s.p.</D_3036></C_C080></S_NAD>
  <G_SG3><S_RFF><C_C506><D_1153>VA</D_1153><D_1154>SI11111111</D_1154></C_C506></S_RFF></G_SG3></G_SG2>
 <G_SG2><S_NAD><D_3035>BY</D_3035><C_C080><D_3036>Kupec d.o.o.</D_3036></C_C080></S_NAD>
  <G_SG3><S_RFF><C_C506><D_1153>VA</D_1153><D_1154>SI22222222</D_1154></C_C506></S_RFF></G_SG3></G_SG2>
 <G_SG8><S_PAT><D_4279>1</D_4279></S_PAT><S_DTM><C_C507><D_2005>13</D_2005><D_2380>2025-11-18</D_2380></C_C507></S_DTM></G_SG8>
 <G_SG26><S_LIN><D_1082>1</D_1082></S_LIN><G_SG27><S_MOA><C_C516><D_5025>203</D_5025><D_5004>999.99</D_5004></C_C516></S_MOA></G_SG27></G_SG26>
 <G_SG50><S_MOA><C_C516><D_5025>79</D_5025><D_5004>1000.00</D_5004></C_C516></S_MOA></G_SG50>
 <G_SG50><S_MOA><C_C516><D_5025>389</D_5025><D_5004>1000.00</D_5004></C_C516></S_MOA></G_SG50>
 <G_SG50><S_MOA><C_C516><D_5025>176</D_5025><D_5004>220.00</D_5004></C_C516></S_MOA></G_SG50>
 <G_SG50><S_MOA><C_C516><D_5025>388</D_5025><D_5004>1220.00</D_5004></C_C516></S_MOA></G_SG50>
 <G_SG52><S_TAX><D_5283>7</D_5283><C_C243><D_5278>22.00</D_5278></C_C243></S_TAX>
  <S_MOA><C_C516><D_5025>125</D_5025><D_5004>1000.00</D_5004></C_C516></S_MOA>
  <S_MOA><C_C516><D_5025>124</D_5025><D_5004>220.00</D_5004></C_C516></S_MOA></G_SG52>
</M_INVOIC></Invoice>"""

UBL = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cbc:ID>U-7</cbc:ID><cbc:IssueDate>2026-02-01</cbc:IssueDate><cbc:DueDate>2026-02-16</cbc:DueDate>
 <cac:AccountingSupplierParty><cac:Party><cac:PartyTaxScheme><cbc:CompanyID>SI33333333</cbc:CompanyID></cac:PartyTaxScheme>
  <cac:PartyLegalEntity><cbc:RegistrationName>Dobavitelj d.o.o.</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party></cac:AccountingSupplierParty>
 <cac:AccountingCustomerParty><cac:Party><cac:PartyTaxScheme><cbc:CompanyID>SI11111111</cbc:CompanyID></cac:PartyTaxScheme></cac:Party></cac:AccountingCustomerParty>
 <cac:TaxTotal><cbc:TaxAmount currencyID="EUR">9.50</cbc:TaxAmount><cac:TaxSubtotal><cac:TaxCategory><cbc:Percent>9.5</cbc:Percent></cac:TaxCategory></cac:TaxSubtotal></cac:TaxTotal>
 <cac:LegalMonetaryTotal><cbc:TaxExclusiveAmount currencyID="EUR">100.00</cbc:TaxExclusiveAmount>
  <cbc:TaxInclusiveAmount currencyID="EUR">109.50</cbc:TaxInclusiveAmount><cbc:PayableAmount currencyID="EUR">109.50</cbc:PayableAmount></cac:LegalMonetaryTotal>
</Invoice>"""


def test_eslog_ignores_line_amounts_and_reads_totals():
    b = parse_file(ESLOG.format(num="2025-17").encode(), "2025-17.xml")
    inv = b.invoices[0]
    assert (inv.number, inv.issue_date, inv.due_date) == ("2025-17", date(2025, 11, 3), date(2025, 11, 18))
    assert (inv.net, inv.vat, inv.gross, inv.vat_rate) == (Decimal("1000.00"), Decimal("220.00"), Decimal("1220.00"), Decimal("0.22"))
    assert inv.buyer_name == "Kupec d.o.o." and inv.seller_tax == "SI11111111" and not inv.warnings


def test_ubl_received():
    inv = parse_file(UBL.encode(), "u.xml").invoices[0]
    assert inv.seller_name == "Dobavitelj d.o.o." and inv.vat == Decimal("9.50") and inv.vat_rate == Decimal("0.095")


def test_zip_envelope_with_pdfs():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in ("2025-1", "2025-2"):
            z.writestr(f"{n}.xml", ESLOG.format(num=n))
            z.writestr(f"{n}.pdf", b"%PDF-1.4 " + n.encode())
        z.writestr("ovojnica.xml", "<package><envelope/></package>")
    b = parse_file(buf.getvalue(), "evelope.zip")
    assert [i.number for i in b.invoices] == ["2025-1", "2025-2"]
    assert [i.pdf_name for i in b.invoices] == ["2025-1.pdf", "2025-2.pdf"]
    assert not b.warnings


def test_excel_export():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["Seznam računov"])
    ws.append(["Številka računa", "Datum izdaje", "Kupec", "Znesek brez DDV", "DDV", "Skupaj", "Rok plačila", "Plačano"])
    ws.append(["2025-1", date(2025, 7, 15), "A d.o.o.", 1000, 220, 1220, date(2025, 7, 30), "DA"])
    ws.append(["2025-2", "02.08.2025", "B d.o.o.", "2.000,00", "440,00", "2.440,00", "17.08.2025", ""])
    ws.append(["Skupaj", None, None, 3000, 660, 3660, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    b = parse_file(buf.getvalue(), "racuni.xlsx")
    assert [i.number for i in b.invoices] == ["2025-1", "2025-2"]
    assert b.invoices[0].paid_amount == Decimal("1220.00") and b.invoices[1].paid_amount is None
    assert b.invoices[1].net == Decimal("2000.00") and b.invoices[1].issue_date == date(2025, 8, 2)
