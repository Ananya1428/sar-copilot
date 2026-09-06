"""Check 2 — Entity grounding (blueprint §14.2). CRITICAL.

Every capitalised proper-noun sequence in the narrative TEXT (not the
LLM's `evidence_keys` — see numeric.py's module docstring for why) must
appear verbatim in `pack.allowed_entities()`.

Two exclusions, both named explicitly in §14.2:
  - stopwords: common capitalised words (sentence connectives, month
    names — dates are the temporal check's job — and short domain codes
    like currency/channel/rating values that are real facts but are never
    flattened as entity/location EvidenceItems by builder.py, so a bare
    code here would otherwise false-positive).
  - the sentence-initial word: capitalised only because it starts the
    sentence, not because it's a proper noun (e.g. "The activity ...").
    Only a single leading word is excluded — if it's the start of a
    longer capitalised run (a name at the very start of a sentence, e.g.
    "Rajesh Mehta conducted ..."), that whole run is still checked.

A reference code such as "TXN-0001" or "CUS-4471" is never mistaken for
an entity: the pattern's negative lookahead refuses to match a
capitalised token immediately followed by "-<digit>".

One more source of legitimate capitalised words that aren't in
`allowed_entities()`: a typology's `label` (e.g. "Structuring / smurfing
(deposits)") is `type="text"`, not `entity`/`location` (see builder.py) —
it's a fixed, evidence-backed string from a curated dictionary (blueprint
§12.2), not an LLM invention, and the deterministic template itself
quotes it verbatim (deterministic.py's `render_how`/`render_why`). Any
capitalised word appearing inside a real typology's own label is exempt
for the same reason stopwords are: it's real, just not flattened as an
entity item.
"""

import re

from app.domain.evidence.schema import EvidencePack
from app.domain.verification.types import CheckResult, Violation

CAPITALIZED_SEQUENCE = re.compile(r"\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*\b(?!-\d)")

STOPWORDS = {
    "The", "This", "That", "These", "Those", "A", "An", "It", "Its",
    "During", "Between", "Following", "Prior", "After", "Before", "Since",
    "Subsequently", "Furthermore", "Additionally", "However", "Therefore",
    "Given", "Based", "Due", "As", "In", "On", "At", "For", "With",
    "According", "Both", "Each", "No", "Multiple", "Several", "Over",
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
}


def _is_acronym_like(seq: str) -> bool:
    """A single, fully-uppercase word longer than a 2-letter country code
    (STRUCTURING, ACH, USD, HIGH, MEDIUM, ...) is a domain code, not a
    proper noun — those are never flattened as entity/location
    EvidenceItems (see builder.py), only the exact display values are
    (e.g. a subject's legal_name). 2-letter codes are NOT exempted here:
    those are exactly how country codes are represented as `location`
    EvidenceItems, so a fabricated one ("XX") must still be caught."""
    return " " not in seq and seq.isupper() and len(seq) > 2


def _typology_label_phrases(pack: EvidencePack) -> set[str]:
    phrases: set[str] = set()
    for typology in pack.typologies:
        phrases.update(match.group() for match in CAPITALIZED_SEQUENCE.finditer(typology.label))
    return phrases


def check_entities(sentences: list[dict], pack: EvidencePack) -> CheckResult:
    allowed = pack.allowed_entities()
    label_phrases = _typology_label_phrases(pack)

    violations: list[Violation] = []
    for idx, sentence in enumerate(sentences):
        text = sentence.get("text", "")
        for match in CAPITALIZED_SEQUENCE.finditer(text):
            seq = match.group()
            if seq in STOPWORDS:
                continue
            if match.start() == 0 and " " not in seq:
                continue  # sentence-initial single-word exclusion
            if _is_acronym_like(seq):
                continue
            if seq in label_phrases:
                continue
            if seq not in allowed:
                violations.append(
                    Violation(
                        message=f"entity {seq!r} does not appear in the evidence pack's allowed entities",
                        sentence_index=idx,
                        section=sentence.get("section"),
                        token=seq,
                        position=match.start(),
                    )
                )

    passed = not violations
    return CheckResult(name="entity", severity="CRITICAL", passed=passed, score=1.0 if passed else 0.0, violations=violations)
