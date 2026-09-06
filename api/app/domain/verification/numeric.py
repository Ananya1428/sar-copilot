"""Check 1 — Numeric grounding (blueprint §14.1). CRITICAL.

Every numeric token in the narrative TEXT must appear in
`pack.allowed_numbers()`, once both sides are normalised for currency
symbols, thousands separators, and decimal precision.

IMPORTANT (see Part 5 kickoff context): this scans sentence TEXT, never
the LLM's self-reported `evidence_keys` — those are decoration for the UI
and the completeness check, not a grounding mechanism. A wrong
evidence_key on a correct number must still PASS here; a plausible-looking
evidence_key on a fabricated number must still FAIL here.
"""

import re
from decimal import Decimal, InvalidOperation

from app.domain.evidence.schema import EvidencePack
from app.domain.verification.temporal import ISO_DATE, NATURAL_DATE
from app.domain.verification.types import CheckResult, Violation

# Matches an optional leading '$', digit groups with optional ',' thousands
# separators, an optional decimal part, and an optional trailing '%'.
NUMBER_PATTERN = re.compile(r"\$?-?\d[\d,]*(?:\.\d+)?%?")


def _date_spans(text: str) -> list[tuple[int, int]]:
    """Character ranges covered by a date in this text (ISO or natural
    form) — NUMBER_PATTERN would otherwise partially match a date's digit
    runs (e.g. "2024" out of "2024-03-03") as a spurious, ungrounded
    numeric token. Dates are the temporal check's job (temporal.py); the
    numeric check must not double-police the same characters."""
    return [m.span() for m in ISO_DATE.finditer(text)] + [m.span() for m in NATURAL_DATE.finditer(text)]


def _overlaps_any(position: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


# Small integers used as structural counters ("the first two transactions",
# "three deposits") rather than cited facts are exempt — per §14.1's own
# carve-out for "structural numbers (ordinals ... and small counters 1-10)".
# Ordinal words ("first", "second") never match NUMBER_PATTERN at all since
# it only matches digit sequences, so no separate handling is needed for them.
STRUCTURAL_EXEMPT_MAX = 10


def _normalize(token: str) -> Decimal | None:
    cleaned = token.strip().lstrip("$").rstrip("%").replace(",", "")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def check_numeric(sentences: list[dict], pack: EvidencePack) -> CheckResult:
    allowed: set[Decimal] = set()
    for raw in pack.allowed_numbers():
        value = _normalize(raw)
        if value is not None:
            allowed.add(value)

    violations: list[Violation] = []
    for idx, sentence in enumerate(sentences):
        text = sentence.get("text", "")
        date_spans = _date_spans(text)
        for match in NUMBER_PATTERN.finditer(text):
            if _overlaps_any(match.start(), date_spans):
                continue
            token = match.group()
            value = _normalize(token)
            if value is None:
                continue
            if value == value.to_integral_value() and 0 <= value <= STRUCTURAL_EXEMPT_MAX:
                continue
            if value not in allowed:
                violations.append(
                    Violation(
                        message=f"numeric token {token!r} does not appear in the evidence pack's allowed numbers",
                        sentence_index=idx,
                        section=sentence.get("section"),
                        token=token,
                        position=match.start(),
                    )
                )

    passed = not violations
    return CheckResult(name="numeric", severity="CRITICAL", passed=passed, score=1.0 if passed else 0.0, violations=violations)
