"""Dnevni nadzor: preveri podatke, osveži opozorila, pripravi dnevni pregled, spremlja pravila."""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit
from .config import get_settings
from .engines import calendar as tax_calendar
from .engines import cash, forecast, mistakes
from .engines.ledger import Ledger
from .models import Alert, DailyReport, Invoice, Setting, User
from .tax_engine import golden
from .tax_engine.money import D, ZERO, r2
from .tax_engine.rules import RULES_DIR, load_rules

log = logging.getLogger("hericr")


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().timezone)).date()


def sync_alerts(db: Session, user: User, findings: list[dict]) -> dict:
    existing = {a.key: a for a in db.scalars(select(Alert).where(Alert.user_id == user.id))}
    current = set()
    created = 0
    for f in findings:
        current.add(f["key"])
        a = existing.get(f["key"])
        if a is None:
            db.add(Alert(user_id=user.id, severity=f["severity"], code=f["code"], key=f["key"], title=f["title"],
                         detail=f["detail"], entity=f["entity"], entity_id=f["entity_id"]))
            created += 1
        elif not a.dismissed:
            # samodejno razrešeno opozorilo, ki se ponovno pojavi, se ponovno odpre
            a.title, a.detail, a.severity, a.resolved = f["title"], f["detail"], f["severity"], False
    auto_resolved = 0
    for key, a in existing.items():
        if key not in current and not a.resolved:
            a.resolved = True
            auto_resolved += 1
    db.commit()
    return {"created": created, "auto_resolved": auto_resolved, "open": len(current)}


def daily_check(db: Session, user: User, day: date | None = None, with_ai: bool = True) -> DailyReport:
    day = day or today()
    L = Ledger.load(db, user, day.year, day)
    findings = mistakes.find(L)
    sync = sync_alerts(db, user, findings)

    month_rev = r2(sum((D(i.net) for i in L.invoices if i.issue_date.month == day.month and i.issue_date <= day), ZERO))
    today_rev = r2(sum((D(i.net) for i in db.scalars(select(Invoice).where(Invoice.user_id == user.id,
                                                                          Invoice.issue_date == day))), ZERO))
    fc = forecast.build(L)
    cur = next(s for s in fc["scenarios"] if s["key"] == "CURRENT")
    res = cash.reserve(L)
    cal = tax_calendar.build(L)
    paid_ak = L.paid("akontacija")
    final_tax = D(cur["dohodnina"])
    data = {
        "day": day.isoformat(),
        "prihodki_danes": str(today_rev),
        "prihodki_ta_mesec": str(month_rev),
        "prihodki_letos": str(L.revenue_ytd),
        "napoved_letos_trenutni_tempo": cur["revenue"],
        "predvidena_dohodnina_letos": cur["dohodnina"],
        "predvideni_prispevki_letos": cur["prispevki"],
        "akontacija_odmerjena_letno": str(D(L.bp.akontacija_annual or 0)),
        "akontacija_placana": str(paid_ak),
        "razlika_dohodnina_vs_akontacija": str(r2(final_tax - D(L.bp.akontacija_annual or 0))),
        "davcna_rezerva": res["reserve"]["value"],
        "stanje_trr": res["balance"],
        "razpolozljivo": (res.get("available") or {}).get("value"),
        "naslednji_roki": [{k: i.get(k) for k in ("title", "due_date", "amount", "days_until", "cash_warning")}
                           for i in cal["next"][:3]],
        "opozorila": [{"severity": f["severity"], "title": f["title"]} for f in findings[:6]],
        "opozorila_skupaj": len(findings),
    }
    ai_text = None
    if with_ai and get_settings().anthropic_api_key:
        try:
            from .integrations.ai_analyst import daily_review_text
            ai_text = daily_review_text(data)
        except Exception as e:  # noqa: BLE001
            log.warning("AI dnevni pregled ni uspel: %s", e)
    report = DailyReport(user_id=user.id, day=day, data=data, ai_text=ai_text)
    db.add(report)
    audit.log(db, user.id, "daily_check", f"Dnevni pregled: {len(findings)} opozoril "
              f"({sync['created']} novih, {sync['auto_resolved']} samodejno rešenih)")
    db.commit()
    return report


def rules_fingerprint() -> str:
    h = hashlib.sha256()
    for p in sorted(RULES_DIR.glob("*.yaml")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def watch_rules(db: Session) -> dict | None:
    """Ob zagonu: če so se pravila spremenila, zapiši v audit log in poženi zlate teste."""
    fp = rules_fingerprint()
    row = db.get(Setting, "rules_hash")
    if row is not None and row.value == fp:
        return None
    load_rules.cache_clear()
    result = golden.run()
    msg = ("Davčna pravila naložena prvič" if row is None else "Davčna pravila posodobljena") + \
          f" — zlati testi: {result['passed']}/{result['total']} uspešnih"
    if result["failed"]:
        msg += f" ❌ {result['failed']} TESTOV NI USPELO — preveri izračune!"
    audit.log(db, None, "rules_changed", msg, after={"hash": fp, "failed": [r["id"] for r in result["results"]
                                                                           if not r["passed"]]})
    if row is None:
        db.add(Setting(key="rules_hash", value=fp))
    else:
        row.value = fp
    db.commit()
    log.info(msg)
    return result
