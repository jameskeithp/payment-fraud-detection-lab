"""Risk scoring engine: evaluates rules, aggregates findings,
and produces a 0-100 score with an allow / step-up-auth / block decision."""

from __future__ import annotations

from dataclasses import dataclass

from fraudlab.models import Finding, Transaction
from fraudlab.rules import DEFAULT_RULES, Rule
from fraudlab.state import StateStore

# Score at or above this blocks the transfer outright.
BLOCK_THRESHOLD = 70.0
# Score at or above this (but below block) triggers step-up auth.
STEP_UP_THRESHOLD = 30.0


@dataclass(frozen=True)
class ScoreResult:
    transaction: Transaction
    score: float
    decision: str  # allow | step_up_auth | block
    findings: list[Finding]


class FraudEngine:
    def __init__(self, rules: list[Rule] | None = None) -> None:
        self.rules = list(rules) if rules is not None else list(DEFAULT_RULES)
        self.store = StateStore()

    def evaluate(self, tx: Transaction) -> ScoreResult:
        findings: list[Finding] = []
        for rule in self.rules:
            findings.extend(rule.evaluate(tx, self.store))

        raw = sum(f.score_weight for f in findings)
        score = min(100.0, raw)

        if score >= BLOCK_THRESHOLD:
            decision = "block"
        elif score >= STEP_UP_THRESHOLD:
            decision = "step_up_auth"
        else:
            decision = "allow"

        self.store.record(tx)
        return ScoreResult(transaction=tx, score=score, decision=decision, findings=findings)

    def evaluate_batch(self, txs: list[Transaction]) -> list[ScoreResult]:
        return [self.evaluate(tx) for tx in txs]
