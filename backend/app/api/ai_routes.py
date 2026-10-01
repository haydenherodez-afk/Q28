from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import get_settings
from ..db import get_db
from ..integrations import ai_analyst
from ..integrations.claude_client import AIUnavailable, friendly_error
from ..models import ChatMessage, Conversation, User
from ..schemas import ChatIn
from .deps import period

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status")
def ai_status(user: User = Depends(current_user)):
    s = get_settings()
    return {"enabled": bool(s.anthropic_api_key), "model": s.ai_model}


@router.post("/chat")
def ai_chat(body: ChatIn, p=Depends(period), user: User = Depends(current_user), db: Session = Depends(get_db)):
    year, as_of = p
    try:
        return ai_analyst.chat(db, user, body.message, body.conversation_id, year, as_of)
    except AIUnavailable as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, friendly_error(e)) from e


@router.get("/conversations")
def conversations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.id.desc()))
    return [{"id": c.id, "title": c.title, "created_at": c.created_at.isoformat()} for c in rows]


@router.get("/conversations/{cid}")
def conversation(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Conversation, cid)
    if c is None or c.user_id != user.id:
        raise HTTPException(404, "Ne obstaja")
    msgs = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == cid, ChatMessage.visible_text.is_not(None))
                      .order_by(ChatMessage.id))
    return {"id": c.id, "title": c.title,
            "messages": [{"role": m.role, "text": m.visible_text, "ts": m.created_at.isoformat()} for m in msgs]}
