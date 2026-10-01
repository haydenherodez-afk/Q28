"""Nalaganje davčnih pravil iz YAML. Engine dobi parametre SAMO od tu."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from .money import D

RULES_DIR = Path(__file__).parent / "rules"


class RuleError(LookupError):
    pass


def _as_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    params: dict
    formula: str
    source: str
    source_url: str | None
    source_date: date | None
    effective_from: date | None
    effective_to: date | None
    taxpayer_type: tuple[str, ...]
    verified: bool
    verified_by: tuple[str, ...]
    note: str
    status: str

    def valid_on(self, day: date) -> bool:
        if self.effective_from and day < self.effective_from:
            return False
        if self.effective_to and day > self.effective_to:
            return False
        return True

    def period_value(self, day: date):
        """Za pravila s 'periods' (npr. OZP, min. osnova) vrne vrednost na dan."""
        for p in self.params.get("periods", []):
            if _as_date(p["from"]) <= day <= _as_date(p["to"]):
                return D(p["value"]), bool(p.get("verified", self.verified))
        raise RuleError(f"Pravilo {self.id} nima vrednosti za {day.isoformat()}")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "formula": self.formula,
            "params": self.params,
            "source": self.source,
            "source_url": self.source_url,
            "source_date": self.source_date.isoformat() if self.source_date else None,
            "effective_from": self.effective_from.isoformat() if self.effective_from else None,
            "effective_to": self.effective_to.isoformat() if self.effective_to else None,
            "taxpayer_type": list(self.taxpayer_type),
            "verified": self.verified,
            "verified_by": list(self.verified_by),
            "note": self.note,
            "status": self.status,
        }


class RuleSet:
    def __init__(self, year: int, rules: dict[str, Rule], checked_on: date | None, pending: dict[str, Rule]):
        self.year = year
        self._rules = rules
        self.checked_on = checked_on
        self.pending = pending

    def has(self, rule_id: str) -> bool:
        return rule_id in self._rules or rule_id in self.pending

    def get(self, rule_id: str) -> Rule:
        if rule_id in self._rules:
            return self._rules[rule_id]
        if rule_id in self.pending:
            return self.pending[rule_id]
        raise RuleError(f"Pravilo '{rule_id}' za leto {self.year} ne obstaja — engine ne bo ugibal.")

    def p(self, rule_id: str, *path):
        node = self.get(rule_id).params
        for key in path:
            node = node[key]
        return node

    def source_of(self, rule_id: str) -> dict:
        r = self.get(rule_id)
        return {
            "rule_id": r.id,
            "title": r.title,
            "source": r.source,
            "source_url": r.source_url,
            "verified": r.verified,
            "note": r.note,
        }

    def all(self) -> list[Rule]:
        return list(self._rules.values())


def _parse(raw: dict) -> Rule:
    return Rule(
        id=raw["id"],
        title=raw.get("title", raw["id"]),
        params=raw.get("params", {}),
        formula=raw.get("formula", ""),
        source=raw.get("source", ""),
        source_url=raw.get("source_url"),
        source_date=_as_date(raw.get("source_date")),
        effective_from=_as_date(raw.get("effective_from")),
        effective_to=_as_date(raw.get("effective_to")),
        taxpayer_type=tuple(raw.get("taxpayer_type", [])),
        verified=bool(raw.get("verified", False)),
        verified_by=tuple(raw.get("verified_by", [])),
        note=raw.get("note", ""),
        status=raw.get("status", "in_force"),
    )


@lru_cache(maxsize=8)
def load_rules(year: int) -> RuleSet:
    path = RULES_DIR / f"{year}.yaml"
    if not path.exists():
        raise RuleError(f"Za leto {year} ni davčnih pravil ({path.name}). Dodaj jih, preden računaš.")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = {}
    for raw in data["rules"]:
        rule = _parse(raw)
        if rule.id in rules:
            raise RuleError(f"Podvojeno pravilo {rule.id}")
        rules[rule.id] = rule
    pending = {}
    pending_path = RULES_DIR / "pending.yaml"
    if pending_path.exists():
        pdata = yaml.safe_load(pending_path.read_text(encoding="utf-8"))
        if pdata.get("year") == year:
            for raw in pdata["rules"]:
                rule = _parse(raw)
                pending[rule.id] = rule
    return RuleSet(year, rules, _as_date(data.get("checked_on")), pending)
