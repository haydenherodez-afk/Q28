"""Scanner računov: PDF/JPG/PNG -> Claude prebere podatke -> uporabnik potrdi.
AI samo PREBERE dokument; zneske nato preveri determinističen kontrolor (neto + DDV = bruto)."""
from __future__ import annotations

import base64
import json
from decimal import Decimal

from ..engines.mistakes import VAT_RATES
from ..tax_engine.money import D, r2
from .claude_client import FALLBACK_BETA, client, model

CATEGORIES = ["material", "orodje in material", "gorivo", "programska oprema", "telekomunikacije", "storitve",
              "najemnina", "zavarovanje", "potni stroški", "izobraževanje", "oprema", "pisarna",
              "reprezentanca", "bančni stroški", "drugo"]

SCHEMA = {
    "type": "object",
    "properties": {
        "supplier": {"type": "string", "description": "Naziv izdajatelja računa"},
        "supplier_tax_number": {"type": ["string", "null"], "description": "ID za DDV / davčna številka izdajatelja"},
        "invoice_number": {"type": ["string", "null"]},
        "date": {"type": ["string", "null"], "description": "Datum računa YYYY-MM-DD"},
        "net": {"type": ["number", "null"], "description": "Znesek brez DDV v EUR"},
        "vat": {"type": ["number", "null"], "description": "Znesek DDV v EUR (0, če ga ni)"},
        "gross": {"type": ["number", "null"], "description": "Znesek za plačilo z DDV v EUR"},
        "vat_rate": {"type": ["number", "null"], "description": "Prevladujoča stopnja DDV kot delež, npr. 0.22"},
        "currency": {"type": "string"},
        "category": {"type": "string", "enum": CATEGORIES},
        "possibly_private": {"type": "boolean", "description": "Ali je nakup verjetno zaseben (hrana, oblačila …)"},
        "notes": {"type": "string", "description": "Kratke opombe: kaj ni bilo berljivo, več stopenj DDV …"},
    },
    "required": ["supplier", "supplier_tax_number", "invoice_number", "date", "net", "vat", "gross", "vat_rate",
                 "currency", "category", "possibly_private", "notes"],
    "additionalProperties": False,
}

PROMPT = """Iz priloženega računa (Slovenija, s.p.) preberi podatke za evidenco stroškov.
- Zneske piši kot števila v evrih (decimalna pika). Če račun ni v EUR, nastavi currency in pusti zneske kot so.
- Če podatek ni berljiv ali ga ni, uporabi null — ne ugibaj.
- Kategorijo izberi iz seznama. possibly_private = true za tipično zasebne nakupe.
- Ne računaj davkov; samo prepiši, kar piše na računu."""


def scan(data: bytes, content_type: str) -> dict:
    b64 = base64.standard_b64encode(data).decode()
    if content_type == "application/pdf":
        block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    elif content_type in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        block = {"type": "image", "source": {"type": "base64", "media_type": content_type, "data": b64}}
    else:
        raise ValueError("Podprti so PDF, JPG, PNG in WEBP.")
    resp = client().beta.messages.create(
        model=model(),
        max_tokens=16000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": [block, {"type": "text", "text": PROMPT}]}],
    )
    if resp.stop_reason == "refusal":
        raise ValueError("AI dokumenta ni prebral (zavrnjeno). Vnesi strošek ročno.")
    if resp.stop_reason == "max_tokens":
        raise ValueError("Odgovor AI je bil prekinjen. Poskusi znova ali vnesi ročno.")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if not text:
        raise ValueError("AI ni vrnil podatkov.")
    data_out = json.loads(text)
    return validate(data_out)


def validate(d: dict) -> dict:
    """Deterministična kontrola prebranih zneskov."""
    checks = []
    net, vat, gross = (None if d.get(k) is None else r2(D(d[k])) for k in ("net", "vat", "gross"))
    if net is not None and vat is None and gross is not None:
        vat = r2(gross - net)
    if net is None and vat is not None and gross is not None:
        net = r2(gross - vat)
    if gross is None and net is not None and vat is not None:
        gross = r2(net + vat)
    if None not in (net, vat, gross):
        ok = abs(net + vat - gross) <= Decimal("0.02")
        checks.append({"label": "neto + DDV = bruto", "ok": ok})
        if net > 0 and vat > 0:
            rate_ok = any(abs(vat - r2(net * r)) <= Decimal("0.05") for r in VAT_RATES)
            checks.append({"label": "DDV ustreza stopnji 22 / 9,5 / 5 %", "ok": rate_ok})
    else:
        checks.append({"label": "vsi zneski prebrani", "ok": False})
    if (d.get("currency") or "EUR").upper() != "EUR":
        checks.append({"label": "valuta EUR", "ok": False})
    d.update({"net": None if net is None else str(net), "vat": None if vat is None else str(vat),
              "gross": None if gross is None else str(gross)})
    return {"proposal": d, "checks": checks, "needs_review": not all(c["ok"] for c in checks)}
