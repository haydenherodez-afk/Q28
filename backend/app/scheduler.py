"""Dnevni pregledi (APScheduler, Europe/Ljubljana)."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import User
from .services import daily_check

log = logging.getLogger("hericr")
_sched: BackgroundScheduler | None = None


def _job():
    db = SessionLocal()
    try:
        for user in db.scalars(select(User)):
            try:
                daily_check(db, user)
            except Exception:  # noqa: BLE001
                log.exception("Dnevni pregled za uporabnika %s ni uspel", user.id)
    finally:
        db.close()


def start():
    global _sched
    s = get_settings()
    if not s.scheduler_enabled or _sched is not None:
        return
    _sched = BackgroundScheduler(timezone=s.timezone)
    _sched.add_job(_job, "cron", hour=s.daily_check_hour, minute=0, id="daily_check", replace_existing=True)
    _sched.start()
    log.info("Dnevni pregled nastavljen ob %02d:00 (%s)", s.daily_check_hour, s.timezone)


def stop():
    global _sched
    if _sched:
        _sched.shutdown(wait=False)
        _sched = None
