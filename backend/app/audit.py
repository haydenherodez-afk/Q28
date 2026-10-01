"""Audit log: vsaka sprememba podatkov ali pravil se zapiše (kdo, kdaj, prej → potem)."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from .models import AuditLog


def snapshot(obj) -> dict:
    out = {}
    for attr in inspect(obj).mapper.column_attrs:
        v = getattr(obj, attr.key)
        if isinstance(v, Decimal):
            v = str(v)
        elif isinstance(v, (date, datetime)):
            v = v.isoformat()
        out[attr.key] = v
    return out


def log(db: Session, user_id: int | None, action: str, message: str, entity: str | None = None,
        entity_id: int | None = None, before: dict | None = None, after: dict | None = None) -> AuditLog:
    if before and after:
        changed = {k for k in after if before.get(k) != after.get(k)}
        before = {k: before[k] for k in changed if k in before}
        after = {k: after[k] for k in changed}
    entry = AuditLog(user_id=user_id, action=action, entity=entity, entity_id=entity_id,
                     message=message, before=before, after=after)
    db.add(entry)
    return entry
