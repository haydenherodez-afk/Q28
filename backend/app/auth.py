"""Prijava: geslo (bcrypt) + TOTP 2FA (Google Authenticator / Authy / 1Password) + JWT."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pyotp
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)
ALGO = "HS256"


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int, purpose: str = "access", minutes: int | None = None) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes or s.token_minutes)
    return jwt.encode({"sub": str(user_id), "purpose": purpose, "exp": exp}, s.secret_key, algorithm=ALGO)


def decode_token(token: str, purpose: str = "access") -> int:
    try:
        data = jwt.decode(token, get_settings().secret_key, algorithms=[ALGO])
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Neveljavna ali potekla seja") from e
    if data.get("purpose") != purpose:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Napačen tip žetona")
    return int(data["sub"])


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="HericR")


def verify_totp(secret: str, code: str) -> bool:
    return bool(secret) and pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Prijava je obvezna")
    user = db.get(User, decode_token(cred.credentials))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Uporabnik ne obstaja")
    return user
