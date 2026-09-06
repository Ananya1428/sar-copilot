"""Shared result types for the six verification checks (blueprint §14) and
their aggregation (§14.7). Every check module returns one `CheckResult`;
`pipeline.py` collects six of them into a `VerificationReport`.

Kept separate from `pipeline.py` so each check module can import just the
tiny shared vocabulary here without importing the aggregator itself.
"""

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["CRITICAL", "HIGH"]


@dataclass
class Violation:
    """One offending token/entity/date/phrase, with enough position
    information for a UI to point at the exact spot in the narrative."""

    message: str
    sentence_index: int | None = None
    section: str | None = None
    token: str | None = None
    position: int | None = None  # character offset of `token` within the sentence text


@dataclass
class CheckResult:
    name: str
    severity: Severity
    passed: bool
    score: float  # 1.0 = fully clean; checks may report partial credit (completeness) or binary (numeric/entity/temporal/prohibited)
    violations: list[Violation] = field(default_factory=list)
    # Check-specific extras that don't belong on every check. Currently
    # only `entailment` populates `details["sentence_scores"]` (a
    # {sentence_index: entailment_probability} map) so `persist_narrative`
    # can backfill `NarrativeSentence.grounding_score` per sentence.
    details: dict = field(default_factory=dict)
