"""Check 7 — Aggregation (blueprint §14.7), and the `Verifier` the
narrative engine (Part 4) actually calls.

Weighted aggregate: numeric 0.25, entity 0.25, temporal 0.15, prohibited
0.20, entailment 0.10, completeness 0.05. A single CRITICAL failure
(numeric/entity/temporal/prohibited) blocks release regardless of the
weighted score — "there is no averaging away a fabricated account
number" (§14). Passing requires no CRITICAL failure AND overall >= 0.85.
"""

from dataclasses import dataclass, field

from app.domain.evidence.schema import EvidencePack
from app.domain.verification.completeness import check_completeness
from app.domain.verification.entity import check_entities
from app.domain.verification.numeric import check_numeric
from app.domain.verification.prohibited import check_prohibited
from app.domain.verification.semantic import Classifier, check_entailment
from app.domain.verification.temporal import check_temporal
from app.domain.verification.types import CheckResult

WEIGHTS: dict[str, float] = {
    "numeric": 0.25,
    "entity": 0.25,
    "temporal": 0.15,
    "prohibited": 0.20,
    "entailment": 0.10,
    "completeness": 0.05,
}
PASS_THRESHOLD = 0.85


@dataclass
class VerificationReport:
    passed: bool
    overall_score: float
    checks: dict[str, CheckResult] = field(default_factory=dict)

    @property
    def critical_failures(self) -> list[str]:
        return [name for name, result in self.checks.items() if result.severity == "CRITICAL" and not result.passed]

    def to_jsonable(self) -> dict:
        """The `checks` JSONB shape persisted on `VerificationReport` rows
        (models/verification.py) — per-check pass/fail/score plus enough
        detail per violation to point a UI at the offending token."""
        return {
            name: {
                "severity": result.severity,
                "passed": result.passed,
                "score": result.score,
                "violations": [
                    {
                        "message": v.message,
                        "sentence_index": v.sentence_index,
                        "section": v.section,
                        "token": v.token,
                        "position": v.position,
                    }
                    for v in result.violations
                ],
            }
            for name, result in self.checks.items()
        }

    def __str__(self) -> str:  # for engine.py's retry-loop diagnostic notes
        if self.passed:
            return f"PASSED (score={self.overall_score:.3f})"
        reasons = []
        if self.critical_failures:
            reasons.append(f"critical failures: {', '.join(self.critical_failures)}")
        reasons.append(f"overall score {self.overall_score:.3f} (threshold {PASS_THRESHOLD})")
        return f"FAILED ({'; '.join(reasons)})"


def run_pipeline(sentences: list[dict], pack: EvidencePack, entailment_classifier: Classifier | None = None) -> VerificationReport:
    checks: dict[str, CheckResult] = {
        "numeric": check_numeric(sentences, pack),
        "entity": check_entities(sentences, pack),
        "temporal": check_temporal(sentences, pack),
        "prohibited": check_prohibited(sentences, pack),
        "entailment": check_entailment(sentences, pack, classifier=entailment_classifier),
        "completeness": check_completeness(sentences, pack),
    }

    overall_score = sum(WEIGHTS[name] * result.score for name, result in checks.items())
    has_critical_failure = any(result.severity == "CRITICAL" and not result.passed for result in checks.values())
    passed = (not has_critical_failure) and overall_score >= PASS_THRESHOLD

    return VerificationReport(passed=passed, overall_score=overall_score, checks=checks)


class Verifier:
    """Thin wrapper the engine calls via `self.verifier.verify(...)`
    (engine.py already has this call site from Part 4; it just had
    nothing real plugged into it). `entailment_classifier=None` means the
    real local NLI model lazy-loads on first use (semantic.py); tests pass
    a stub classifier so they never need model-download access."""

    def __init__(self, entailment_classifier: Classifier | None = None):
        self.entailment_classifier = entailment_classifier

    def verify(self, sentences: list[dict], pack: EvidencePack) -> VerificationReport:
        return run_pipeline(sentences, pack, entailment_classifier=self.entailment_classifier)
