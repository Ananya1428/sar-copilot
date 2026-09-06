"""Check 4 — Prohibited content (blueprint §14.4). CRITICAL.

Regex families matching the system prompt's own absolute constraints
(`prompts/v1.0.0/system.txt`, constraints 4-6): legal conclusions,
intent/motive speculation, system self-reference, and judgemental
language. This check exists precisely because the prompt asking nicely is
not enforcement — it's the deterministic backstop for when the model
ignores its own instructions.

Plain "suspicious" is deliberately NOT banned: a SAR narrative's entire
purpose is describing suspicious activity ("basis for suspicion" is a
required section, per sections.py's "why" section), so banning the word
itself would make every real narrative fail. Only the judgemental
*intensifier* combinations ("clearly suspicious", "obviously suspicious")
are prohibited.
"""

import re

from app.domain.verification.types import CheckResult, Violation

PATTERN_FAMILIES: dict[str, list[str]] = {
    "legal_conclusion": [
        r"\bcommitted (money )?laundering\b",
        r"\bis guilty of\b",
        r"\blaundered (the |its )?funds\b",
        r"\bviolated the law\b",
        r"\bcommitted (a |the )?crime\b",
        r"\bengaged in (money )?laundering\b",
        r"\billegally?\b",
        r"\bcriminal(ly)? (activity|conduct|enterprise)\b",
        r"\bfraudulent(ly)?\b",
    ],
    "speculation": [
        r"\blikely\b",
        r"\bwe believe\b",
        r"\bintended to conceal\b",
        r"\bappears to (be|have)\b",
        r"\bmay have\b",
        r"\bprobably\b",
        r"\bseems? to\b",
        r"\bin order to (evade|avoid|conceal)\b",
        r"\bin an attempt to\b",
    ],
    "system_self_reference": [
        r"\bthe model\b",
        r"\bisolation forest\b",
        r"\banomaly score\b",
        r"\bmachine learning\b",
        r"\bthe algorithm\b",
        r"\bthe system detected\b",
        r"\bthis (report|narrative) was generated (by|using)\b",
        r"\bneural network\b",
        r"\blarge language model\b",
    ],
    "judgemental_language": [
        r"\begregious(ly)?\b",
        r"\bclearly suspicious\b",
        r"\bobviously suspicious\b",
        r"\bblatant(ly)?\b",
        r"\bshocking(ly)?\b",
        r"\balarming(ly)?\b",
        r"\bobvious(ly)?\b",
        r"\bdisturbing(ly)?\b",
    ],
}

_COMPILED: dict[str, list[re.Pattern]] = {
    category: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for category, patterns in PATTERN_FAMILIES.items()
}


def check_prohibited(sentences: list[dict], pack=None) -> CheckResult:
    """`pack` is accepted (unused) so this check has the same call
    signature as every other check for `pipeline.py`'s uniform dispatch."""
    violations: list[Violation] = []
    for idx, sentence in enumerate(sentences):
        text = sentence.get("text", "")
        for category, patterns in _COMPILED.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    violations.append(
                        Violation(
                            message=f"prohibited language ({category}): {match.group()!r}",
                            sentence_index=idx,
                            section=sentence.get("section"),
                            token=match.group(),
                            position=match.start(),
                        )
                    )

    passed = not violations
    return CheckResult(name="prohibited", severity="CRITICAL", passed=passed, score=1.0 if passed else 0.0, violations=violations)
