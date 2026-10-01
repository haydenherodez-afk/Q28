from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..auth import (create_token, current_user, decode_token, hash_password, new_totp_secret, totp_uri,
                    verify_password, verify_totp)
from ..db import get_db
from ..engines.ledger import ensure_profile
from ..models import User
from ..schemas import LoginIn, SetupIn, TokenOut, TotpCode, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return {"needs_setup": db.scalar(select(func.count(User.id))) == 0}


@router.post("/setup", response_model=TokenOut)
def setup(body: SetupIn, db: Session = Depends(get_db)):
    """Prvi uporabnik (lastnik). Ko obstaja, dodatnih registracij ni."""
    if db.scalar(select(func.count(User.id))):
        raise HTTPException(403, "Aplikacija je že nastavljena — prijavi se.")
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    ensure_profile(db, user)
    audit.log(db, user.id, "setup", "Ustvarjen lastniški račun")
    db.commit()
    return TokenOut(access_token=create_token(user.id))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Napačen e-naslov ali geslo")
    if user.totp_enabled:
        if not body.totp:
            return TokenOut(totp_required=True)
        if not verify_totp(user.totp_secret, body.totp):
            raise HTTPException(401, "Napačna 2FA koda")
    audit.log(db, user.id, "login", "Prijava")
    db.commit()
    return TokenOut(access_token=create_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post("/2fa/setup")
def totp_setup(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.totp_enabled:
        raise HTTPException(400, "2FA je že vklopljena")
    user.totp_secret = new_totp_secret()
    db.commit()
    return {"secret": user.totp_secret, "otpauth_uri": totp_uri(user.totp_secret, user.email)}


@router.post("/2fa/enable")
def totp_enable(body: TotpCode, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.totp_secret or not verify_totp(user.totp_secret, body.code):
        raise HTTPException(400, "Koda ni pravilna — preveri uro na telefonu in poskusi znova")
    user.totp_enabled = True
    audit.log(db, user.id, "2fa", "Vklopljena dvostopenjska prijava (2FA)")
    db.commit()
    return {"ok": True}


@router.post("/2fa/disable")
def totp_disable(body: TotpCode, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.totp_enabled or not verify_totp(user.totp_secret, body.code):
        raise HTTPException(400, "Koda ni pravilna")
    user.totp_enabled = False
    user.totp_secret = None
    audit.log(db, user.id, "2fa", "Izklopljena dvostopenjska prijava (2FA)")
    db.commit()
    return {"ok": True}
