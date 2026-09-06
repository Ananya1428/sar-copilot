"""Check 6 — Completeness (blueprint §14.6). HIGH.

Every required `NARRATIVE_SECTIONS` section must be present (a section
with at least one non-empty sentence carrying its `section` tag), and
every typology detected on the case must be mentioned somewhere in the
prose — by code or by its human-readable label, either is acceptable
since the prompt asks the model to describe typologies in its own words
rather than quote the raw code.

HIGH, not CRITICAL: a narrative missing one section is a real quality
defect worth flagging, but — unlike a fabricated number — it is not the
same category of regulatory risk, so it contributes to the weighted
score rather than an automatic block (§14.7's aggregation).
"""

from app.domain.evidence.schema import EvidencePack
from app.domain.narrative.sections import NARRATIVE_SECTIONS
from app.domain.verification.types import CheckResult, Violation


def check_completeness(sentences: list[dict], pack: EvidencePack) -> CheckResult:
    violations: list[Violation] = []

    present_sections = {s.get("section") for s in sentences if s.get("text", "").strip()}
    for section in NARRATIVE_SECTIONS:
        if section["id"] not in present_sections:
            violations.append(
                Violation(message=f"required section {section['id']!r} is missing from the narrative", section=section["id"])
            )

    full_text = " ".join(s.get("text", "") for s in sentences).lower()
    for typology in pack.typologies:
        code_mentioned = typology.code.lower().replace("_", " ") in full_text
        label_mentioned = typology.label.lower() in full_text
        if not (code_mentioned or label_mentioned):
            violations.append(
                Violation(message=f"typology {typology.code!r} ({typology.label!r}) is not mentioned anywhere in the narrative")
            )

    total_checked = len(NARRATIVE_SECTIONS) + len(pack.typologies)
    score = 1.0 if not violations else max(0.0, 1.0 - len(violations) / max(total_checked, 1))
    passed = not violations
    return CheckResult(name="completeness", severity="HIGH", passed=passed, score=score, violations=violations)
