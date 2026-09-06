"""Check 3 — Temporal grounding (blueprint §14.3). CRITICAL.

Every date in the narrative TEXT must appear in `pack.allowed_dates()`
(grounding — checked everywhere in the narrative). The aggregate-period
bound and the chronological-order rule are both scoped to the
`what_when` section only, not the whole narrative: a subject's
`relationship_start` (onboarding date) is routinely, legitimately
*outside* the case's flagged aggregate period — every real narrative
mentions it in the "who" section (see deterministic.py's `render_who`)
— so a blanket period check would reject correct, grounded template
output. The `what_when` section is specifically the flagged activity's
timeline, which is what §14.3's period-bound and chronology rules are
actually about.

The system prompt tells the model to "reproduce dates exactly in the
format given" (ISO `YYYY-MM-DD`, per `fmt_date` in evidence/schema.py), so
ISO is the primary form matched. A "Month D, YYYY" natural-language form
is matched too, defensively, in case the model paraphrases anyway — see
numeric.py/entity.py's module docstrings for why this scans TEXT rather
than trusting the LLM's own `evidence_keys`.
"""

import re
from datetime import date, datetime

from app.domain.evidence.schema import EvidencePack
from app.domain.verification.types import CheckResult, Violation

ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

_MONTHS = {
    name: i
    for i, name in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}
NATURAL_DATE = re.compile(r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),?\s+(\d{4})\b")


def _find_dates(text: str) -> list[tuple[str, date, int]]:
    found: list[tuple[str, date, int]] = []
    for match in ISO_DATE.finditer(text):
        try:
            found.append((match.group(), datetime.strptime(match.group(), "%Y-%m-%d").date(), match.start()))
        except ValueError:
            continue
    for match in NATURAL_DATE.finditer(text):
        month_name, day, year = match.group(1), int(match.group(2)), int(match.group(3))
        try:
            found.append((match.group(), date(year, _MONTHS[month_name], day), match.start()))
        except ValueError:
            continue
    return found


def check_temporal(sentences: list[dict], pack: EvidencePack) -> CheckResult:
    allowed_dates: set[date] = set()
    for raw in pack.allowed_dates():
        try:
            allowed_dates.add(datetime.strptime(raw, "%Y-%m-%d").date())
        except ValueError:
            continue

    period_start = pack.aggregates.period_start
    period_end = pack.aggregates.period_end

    violations: list[Violation] = []
    what_when_dates: list[date] = []

    for idx, sentence in enumerate(sentences):
        text = sentence.get("text", "")
        section = sentence.get("section")
        for token, parsed, position in _find_dates(text):
            if parsed not in allowed_dates:
                violations.append(
                    Violation(
                        message=f"date {token!r} does not appear in the evidence pack's allowed dates",
                        sentence_index=idx, section=section, token=token, position=position,
                    )
                )
                continue
            if section == "what_when":
                if not (period_start <= parsed <= period_end):
                    violations.append(
                        Violation(
                            message=f"date {token!r} falls outside the evidence period ({period_start} to {period_end})",
                            sentence_index=idx, section=section, token=token, position=position,
                        )
                    )
                what_when_dates.append(parsed)

    if what_when_dates != sorted(what_when_dates):
        violations.append(
            Violation(message="dates in the what_when section are not in chronological order", section="what_when")
        )

    passed = not violations
    return CheckResult(name="temporal", severity="CRITICAL", passed=passed, score=1.0 if passed else 0.0, violations=violations)
