"""Skupni Claude odjemalec. Brez ANTHROPIC ključa so AI funkcije izklopljene (aplikacija deluje naprej)."""
from __future__ import annotations

import anthropic

from ..config import get_settings

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AIUnavailable(RuntimeError):
    pass


_client = None


def client() -> anthropic.Anthropic:
    global _client
    s = get_settings()
    if not s.anthropic_api_key:
        raise AIUnavailable("AI ni nastavljen: dodaj HERICR_ANTHROPIC_API_KEY v .env")
    if _client is None:
        _client = anthropic.Anthropic(api_key=s.anthropic_api_key, max_retries=3)
    return _client


def model() -> str:
    return get_settings().ai_model


def friendly_error(e: Exception) -> str:
    if isinstance(e, AIUnavailable):
        return str(e)
    if isinstance(e, anthropic.AuthenticationError):
        return "Neveljaven Anthropic API ključ."
    if isinstance(e, anthropic.RateLimitError):
        return "AI je trenutno preobremenjen (rate limit) — poskusi čez minuto."
    if isinstance(e, anthropic.BadRequestError):
        return f"AI zahteva ni veljavna: {e.message}"
    if isinstance(e, anthropic.APIStatusError):
        return f"Napaka AI storitve ({e.status_code}) — poskusi znova."
    if isinstance(e, anthropic.APIConnectionError):
        return "Ni povezave z AI storitvijo."
    return f"AI napaka: {e}"
