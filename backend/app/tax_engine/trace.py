"""Explain: vsaka številka nosi svojo pot do rezultata (koraki, formula, pravila, viri)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .money import r2


@dataclass
class Step:
    label: str
    value: Decimal | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "value": None if self.value is None else str(r2(self.value)),
            "note": self.note,
        }


@dataclass
class Explained:
    key: str
    label: str
    value: Decimal
    formula: str = ""
    steps: list[Step] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def step(self, label: str, value=None, note: str = "") -> "Explained":
        self.steps.append(Step(label, value, note))
        return self

    def to_dict(self, rules=None) -> dict:
        out = {
            "key": self.key,
            "label": self.label,
            "value": str(r2(self.value)),
            "formula": self.formula,
            "steps": [s.to_dict() for s in self.steps],
            "rule_ids": self.rule_ids,
            "warnings": self.warnings,
        }
        if rules is not None:
            out["sources"] = [rules.source_of(rid) for rid in self.rule_ids if rules.has(rid)]
        return out
