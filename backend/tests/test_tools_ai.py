"""AI orodja in zanka (brez pravega API klica): vsa orodja vrnejo veljaven JSON iz engina,
zanka pravilno izvede tool_use -> tool_result -> končni odgovor in shrani append-only zgodovino."""
import json
from datetime import date
from types import SimpleNamespace

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.integrations import ai_analyst
from app.models import ChatMessage, Invoice, User


def _user(db):
    u = db.scalar(select(User).where(User.email == "ai@example.com"))
    if u is None:
        u = User(email="ai@example.com", password_hash="x")
        db.add(u)
        db.commit()
        db.add(Invoice(user_id=u.id, number="A-1", customer="K", issue_date=date(2026, 3, 1), net=10000, vat=2200,
                       gross=12200))
        db.commit()
    return u


def test_every_tool_returns_json():
    init_db()
    db = SessionLocal()
    u = _user(db)
    r = ai_analyst.ToolRunner(db, u, 2026, date(2026, 6, 30))
    args = {
        "compare_extra_revenue": {"additional_revenue": 20000, "additional_expenses": 0, "base": "forecast"},
        "calculate_year": {"revenue": 80000, "expenses": 5000, "regime": "profile", "simulate_pending_laws": False},
        "what_if": {"revenues": [70000, 90000], "expense_ratio": 0.1},
        "get_rules": {"query": "normiran"},
    }
    for tool in ai_analyst.TOOLS:
        out = json.loads(r.run(tool["name"], args.get(tool["name"], {})))
        assert out is not None, tool["name"]
    diff = json.loads(r.run("compare_extra_revenue", args["compare_extra_revenue"]))
    assert float(diff["difference"]["prihodki"]) == 20000
    db.close()


class FakeBlock(SimpleNamespace):
    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}


class FakeClient:
    def __init__(self):
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        if len(self.calls) == 1:
            return SimpleNamespace(stop_reason="tool_use", content=[
                FakeBlock(type="thinking", thinking="", signature="sig"),
                FakeBlock(type="tool_use", id="tu_1", name="get_overview", input={})])
        return SimpleNamespace(stop_reason="end_turn", content=[FakeBlock(type="text", text="Prihodki so 10.000,00 €.")])


def test_chat_loop_with_tools(monkeypatch):
    init_db()
    fake = FakeClient()
    monkeypatch.setattr(ai_analyst, "client", lambda: fake)
    db = SessionLocal()
    u = _user(db)
    out = ai_analyst.chat(db, u, "Koliko sem zaslužil?", None, 2026, date(2026, 6, 30))
    assert out["answer"] == "Prihodki so 10.000,00 €." and out["tools_used"] == ["get_overview"]
    second = fake.calls[1]
    # append-only: thinking blok gre nazaj nespremenjen, tool_result se ujema s tool_use id
    assert second["messages"][1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig"}
    assert second["messages"][2]["content"][0]["tool_use_id"] == "tu_1"
    assert second["fallbacks"] == "default" and all(t["strict"] for t in second["tools"])
    rows = list(db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == out["conversation_id"])))
    assert [m.role for m in rows] == ["user", "assistant", "user", "assistant"]
    db.close()
