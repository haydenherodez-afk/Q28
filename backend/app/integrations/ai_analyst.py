"""AI nadzornik / analitik (Claude).

Načelo: Claude je ANALITIK, ne kalkulator. Vsako številko dobi iz orodij, ki kličejo
deterministični Tax Engine in podatke iz baze; davčnih pravil si ne sme izmišljevati.
Zgodovina pogovora je append-only (bloki se shranijo nespremenjeni, tudi thinking)."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..engines import cash, dashboard, forecast, mistakes
from ..engines import calendar as tax_calendar
from ..engines.ledger import Ledger
from ..models import ChatMessage, Conversation, User
from ..tax_engine import YearInput, calculate_year, load_rules, what_if
from ..tax_engine.money import D, r2
from .claude_client import FALLBACK_BETA, client, model

SYSTEM = """Si HericR — osebni finančni direktor (CFO) in davčni nadzornik za slovenskega samostojnega podjetnika (s.p.).

Pravila, ki jih ne smeš kršiti:
1. Nikoli sam ne računaš davkov, prispevkov, akontacije ali DDV in si ne izmišljuješ stopenj, pragov ali rokov. Vsako številko dobiš z orodjem (tax engine in podatki iz baze). Če orodje česa ne vrne, povej, da podatka ni.
2. Ko navedeš obveznost, povej tudi, iz katerega pravila izhaja (rule_id / vir), in ali je pravilo označeno kot preverjeno (verified). Neverificirana pravila jasno označi z "preveri pri FURS/računovodji".
3. Zakoni s statusom pending (npr. ZIURS) še ne veljajo — omeni jih samo kot možen scenarij.
4. Odgovarjaj v slovenščini, jedrnato in v normalnem jeziku. Najprej odgovor (številke), nato kratka razlaga in konkretni naslednji koraki.
5. Zneske piši v slovenskem zapisu (1.234,56 €). Ne ponavljaj vseh vmesnih korakov, razen če uporabnik vpraša "zakaj" ali "kako je izračunano".
6. Za mejne primere (npr. prehod iz normiranca, zaposlovanje, tujina) priporoči posvet z računovodjo."""


def _j(obj) -> str:
    def default(o):
        if isinstance(o, Decimal):
            return str(r2(o))
        if isinstance(o, date):
            return o.isoformat()
        raise TypeError(type(o))
    return json.dumps(obj, ensure_ascii=False, default=default)


def _tool(name, description, props, required=None):
    return {
        "name": name, "description": description, "strict": True,
        "input_schema": {"type": "object", "properties": props, "required": required or list(props),
                         "additionalProperties": False},
    }


TOOLS = [
    _tool("get_overview", "Trenutno stanje letos do danes: prihodki, stroški, davčna osnova, plačano državi, "
          "še dolguješ, realno ostane, napredek in opozorila. Vsaka številka ima razlago (steps) in vire.", {}),
    _tool("compare_extra_revenue",
          "Kaj se zgodi, če letos ustvarim DODATNE prihodke (in stroške). Vrne obveznosti pred in po ter razlike "
          "(prispevki, dohodnina, neto, akontacija za naslednje leto, pragovi). base='ytd' = od današnjega stanja, "
          "base='forecast' = od napovedi do konca leta.",
          {"additional_revenue": {"type": "number"}, "additional_expenses": {"type": "number"},
           "base": {"type": "string", "enum": ["ytd", "forecast"]}}),
    _tool("calculate_year", "Celoten davčni izračun za podan letni prihodek in stroške (z razlago vsakega koraka). "
          "regime: 'profile' = uporabnikov režim, ali 'normiran' / 'dejanski'.",
          {"revenue": {"type": "number"}, "expenses": {"type": "number"},
           "regime": {"type": "string", "enum": ["profile", "normiran", "dejanski"]},
           "simulate_pending_laws": {"type": "boolean"}}),
    _tool("what_if", "Primerjava normiranec vs dejanski stroški za več letnih prihodkov naenkrat.",
          {"revenues": {"type": "array", "items": {"type": "number"}},
           "expense_ratio": {"type": "number", "description": "delež dejanskih stroškov v prihodkih, npr. 0.15"}}),
    _tool("get_forecast", "Napoved letnih prihodkov (LOW / CURRENT / HIGH / TARGET) in davki za vsak scenarij.", {}),
    _tool("get_calendar", "Prihajajoči davčni roki z zneski, statusom plačila in stanjem na TRR po plačilu.", {}),
    _tool("get_tax_reserve", "Koliko denarja mora ostati na TRR za davke in koliko je razpoložljivega.", {}),
    _tool("get_profit_vs_cash", "Ustvarjeno (izdani računi) vs dejansko prejeto (denar) in odprte terjatve.", {}),
    _tool("find_mistakes", "Seznam najdenih napak in tveganj v podatkih (neplačani računi, podvojeni stroški, "
          "napačen DDV, manjkajoči podatki, zamujeni roki, pragovi).", {}),
    _tool("get_rules", "Davčna pravila z viri, formulami in statusom preverjenosti. query filtrira po id/naslovu "
          "(prazno = vsa).", {"query": {"type": "string"}}),
]


class ToolRunner:
    def __init__(self, db: Session, user: User, year: int, as_of: date):
        self.db, self.user, self.year, self.as_of = db, user, year, as_of

    def ledger(self) -> Ledger:
        return Ledger.load(self.db, self.user, self.year, self.as_of)

    def run(self, name: str, args: dict) -> str:
        L = self.ledger()
        if name == "get_overview":
            d = dashboard.build(L)
            return _j({k: d[k] for k in ("as_of", "regime", "scheme", "cards", "progress", "attention", "warnings")})
        if name == "compare_extra_revenue":
            if args["base"] == "forecast":
                cur = next(s for s in forecast.build(L)["scenarios"] if s["key"] == "CURRENT")
                rev, exp = D(cur["revenue"]), D(cur["expenses"])
            else:
                rev, exp = L.revenue_ytd, L.expenses_ytd
            before = calculate_year(L.profile, YearInput(self.year, rev, exp))
            after = calculate_year(L.profile, YearInput(self.year, rev + D(args["additional_revenue"]),
                                                        exp + D(args["additional_expenses"])))
            keys = ["prihodki", "stroski", "davcna_osnova", "prispevki", "dohodnina", "drzavi_skupaj", "neto",
                    "akontacija_naslednje_leto"]
            return _j({
                "base": args["base"],
                "before": {k: before.value(k) for k in keys},
                "after": {k: after.value(k) for k in keys},
                "difference": {k: after.value(k) - before.value(k) for k in keys},
                "kept_from_extra_revenue": after.value("neto") - before.value("neto"),
                "after_explain": {k: after.items[k].to_dict(after.rules) for k in ("dohodnina", "prispevki")},
                "warnings_after": after.warnings,
                "note": "Prispevki se med letom ne spremenijo z višjim prihodkom; višji dobiček zviša osnovo za "
                        "prispevke v naslednjem letu (glej next_year).",
                "next_year_after": after.next_year,
            })
        if name == "calculate_year":
            p = L.profile
            if args["regime"] != "profile":
                from ..tax_engine import Profile
                p = Profile(**{**p.__dict__, "regime": args["regime"]})
            res = calculate_year(p, YearInput(self.year, D(args["revenue"]), D(args["expenses"]),
                                              simulate_pending=args["simulate_pending_laws"]))
            return _j(res.to_dict())
        if name == "what_if":
            return _j(what_if(L.profile, self.year, args["revenues"], expense_ratio=D(args["expense_ratio"])))
        if name == "get_forecast":
            return _j(forecast.build(L))
        if name == "get_calendar":
            c = tax_calendar.build(L)
            c["items"] = [i for i in c["items"] if i["status"] in ("odprto", "zamujeno")][:15]
            return _j(c)
        if name == "get_tax_reserve":
            return _j(cash.reserve(L))
        if name == "get_profit_vs_cash":
            return _j(cash.profit_vs_cash(L))
        if name == "find_mistakes":
            return _j(mistakes.find(L))
        if name == "get_rules":
            rules = load_rules(self.year)
            q = args["query"].lower().strip()
            items = [r.to_dict() for r in list(rules.all()) + list(rules.pending.values())
                     if not q or q in r.id.lower() or q in r.title.lower()]
            return _j({"year": self.year, "checked_on": rules.checked_on, "rules": items})
        raise ValueError(f"Neznano orodje {name}")


def _context_note(L: Ledger) -> str:
    bp = L.bp
    return (f"[Kontekst] Danes je {L.as_of.isoformat()}. Leto {L.year}. Podjetje: {bp.business_name}. "
            f"Režim: {bp.regime}, {'polni' if bp.full_time else 'popoldanski'} s.p., začetek dejavnosti "
            f"{bp.activity_start.isoformat()}, zavezanec za DDV: {'da' if bp.vat_registered else 'ne'}.")


def chat(db: Session, user: User, message: str, conversation_id: int | None, year: int, as_of: date,
         max_rounds: int = 10) -> dict:
    conv = db.get(Conversation, conversation_id) if conversation_id else None
    if conv is None or conv.user_id != user.id:
        conv = Conversation(user_id=user.id, title=message[:80])
        db.add(conv)
        db.commit()
    history = list(db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conv.id)
                              .order_by(ChatMessage.id)))
    runner = ToolRunner(db, user, year, as_of)
    first = not history
    text = (_context_note(runner.ledger()) + "\n\n" + message) if first else message
    user_msg = ChatMessage(conversation_id=conv.id, role="user", content=[{"type": "text", "text": text}],
                           visible_text=message)
    db.add(user_msg)
    db.commit()
    messages = [{"role": m.role, "content": m.content} for m in history] + [{"role": "user", "content": user_msg.content}]

    used_tools = []
    final_text = ""
    for _ in range(max_rounds):
        resp = client().beta.messages.create(
            model=model(), max_tokens=16000, system=SYSTEM, tools=TOOLS, messages=messages,
            betas=[FALLBACK_BETA], fallbacks="default", output_config={"effort": "medium"},
            cache_control={"type": "ephemeral"},
        )
        content = [b.to_dict() for b in resp.content]
        visible = "\n".join(b.text for b in resp.content if b.type == "text").strip()
        db.add(ChatMessage(conversation_id=conv.id, role="assistant", content=content, visible_text=visible or None))
        db.commit()
        messages.append({"role": "assistant", "content": content})
        if resp.stop_reason == "refusal":
            final_text = visible or "Na to vprašanje ne morem odgovoriti."
            break
        if resp.stop_reason != "tool_use":
            final_text = visible
            if resp.stop_reason == "max_tokens":
                final_text += "\n\n(Odgovor je bil prekinjen zaradi dolžine.)"
            break
        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            used_tools.append(b.name)
            try:
                out = runner.run(b.name, dict(b.input))
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
            except Exception as e:  # napaka orodja gre nazaj Claudu, ne pade cel pogovor
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": f"Napaka: {e}",
                                "is_error": True})
        db.add(ChatMessage(conversation_id=conv.id, role="user", content=results))
        db.commit()
        messages.append({"role": "user", "content": results})
    else:
        final_text = final_text or "Analiza je presegla največje število korakov. Poskusi bolj specifično vprašanje."
    return {"conversation_id": conv.id, "answer": final_text, "tools_used": used_tools}


def daily_review_text(data: dict) -> str:
    """Kratko AI besedilo za "Današnji pregled" (številke so že izračunane — AI jih samo razloži)."""
    resp = client().beta.messages.create(
        model=model(), max_tokens=4000, system=SYSTEM,
        betas=[FALLBACK_BETA], fallbacks="default", output_config={"effort": "low"},
        messages=[{"role": "user", "content":
                   "Napiši 'Današnji pregled' (največ 8 vrstic) za podjetnika iz spodnjih, ŽE IZRAČUNANIH podatkov. "
                   "Ne računaj ničesar novega — uporabi samo te številke. Na koncu navedi najpomembnejše opozorilo "
                   "in naslednji rok.\n\n" + _j(data)}],
    )
    if resp.stop_reason == "refusal":
        return ""
    return "\n".join(b.text for b in resp.content if b.type == "text").strip()
