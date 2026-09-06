"""Check 5 — Semantic entailment (blueprint §14.5). HIGH.

Checks 1-4 verify that every token in a sentence is INDIVIDUALLY grounded
in the evidence pack. None of them can catch the failure mode where every
name and number is real but the RELATIONSHIP asserted between them is
fabricated — "Rajesh Mehta transferred funds to external-party" when both
of those exist in evidence but no such transaction/relationship does.
That is exactly what this check is for.

Grounding lookup (per Part 5 kickoff context — never trust the LLM's own
`evidence_keys` as ground truth): for a given sentence, the EvidenceItems
it "actually draws from" are found the same way checks 1-3 do it — by
scanning the sentence TEXT for each item's `display_value`, not by
reading `evidence_keys`. Those grounded items are turned into short
factual clauses ("The legal_name is Rajesh Mehta.") and joined into a
premise; a local NLI model then scores whether that premise entails the
sentence. A sentence whose tokens are all individually real can still
fail here if the compound claim isn't entailed by the disconnected facts
behind it.

RUNTIME BUDGET (documented per the Part 5 brief's ask): entailment runs
PER SENTENCE, not once per whole narrative. A per-narrative single call
would need one premise covering the whole pack, which drowns exactly the
signal this check exists for (whether THIS sentence's specific relational
claim is supported) — a single generic "premise" built from dozens of
unrelated facts would trivially "entail" almost any sentence that reuses
a few of those facts. Per-sentence calls cost more wall-clock time
(one forward pass per sentence, typically ~15-30 sentences per narrative)
but are the only granularity that can actually catch a single fabricated
relationship in an otherwise-correct narrative. See test output / the
CLI report for measured per-call and per-narrative latency.

MODEL / DEVICE: `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` via
`transformers`, on GPU when `torch.cuda.is_available()` (the project has
an RTX 4060, already used for Ollama per Part 4) and CPU otherwise. This
model is lazy-loaded as a module-level singleton on first real use so
importing this module (or running the other five checks) never pays the
load cost. `check_entailment` accepts an injectable `classifier` callable
for tests and for any environment without model-download access — the
pipeline default is `None`, which lazy-loads the real model.
"""

import re
from collections.abc import Callable

from app.domain.evidence.schema import EvidenceItem, EvidencePack
from app.domain.verification.types import CheckResult, Violation

MODEL_NAME = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
ENTAILMENT_THRESHOLD = 0.5

Classifier = Callable[[str, str], tuple[str, float]]  # (premise, hypothesis) -> (label, entailment_probability)

_classifier_singleton: Classifier | None = None
_classifier_load_error: str | None = None


def _item_referenced(item: EvidenceItem, text: str) -> bool:
    """Excluding "." from the boundary (in addition to \\w) prevents a
    short numeric value from partially matching inside a longer decimal
    (e.g. "600" inside "8600.00") — but that exclusion must apply only
    when the value itself is numeric. Applied unconditionally, it also
    blocks a name from matching at the end of a sentence, since "." is
    almost always the character right after it (e.g. "... Rajesh Mehta."
    — the period is the sentence's full stop, not part of the name)."""
    if not item.display_value:
        return False
    value = item.display_value
    left = r"(?<![\w.])" if value[0].isdigit() else r"(?<!\w)"
    right = r"(?![\w.])" if value[-1].isdigit() else r"(?!\w)"
    pattern = left + re.escape(value) + right
    return re.search(pattern, text) is not None


def grounded_items(text: str, pack: EvidencePack) -> list[EvidenceItem]:
    """The EvidenceItems a sentence's TEXT actually references — found by
    scanning for each item's display_value, exactly like checks 1-3, never
    by trusting the sentence's self-reported `evidence_keys`."""
    return [item for item in pack.items if _item_referenced(item, text)]


def _item_to_clause(item: EvidenceItem) -> str:
    field = item.source_field.replace("computed:", "").replace("_", " ").strip() or item.key
    return f"The {field} is {item.display_value}."


def _build_premise(items: list[EvidenceItem]) -> str:
    seen: set[str] = set()
    clauses = []
    for item in items:
        clause = _item_to_clause(item)
        if clause not in seen:
            seen.add(clause)
            clauses.append(clause)
    return " ".join(clauses)


def _load_default_classifier() -> Classifier:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME).to(device)
    model.eval()
    id2label = {int(k): v.lower() for k, v in model.config.id2label.items()}

    def classify(premise: str, hypothesis: str) -> tuple[str, float]:
        inputs = tokenizer(premise, hypothesis, return_tensors="pt", truncation=True).to(device)
        with torch.no_grad():
            logits = model(**inputs).logits[0]
        probs = torch.softmax(logits, dim=-1)
        entail_idx = next((i for i, label in id2label.items() if "entail" in label), None)
        if entail_idx is None:
            entail_idx = 0
        label = id2label[int(probs.argmax())]
        return label, float(probs[entail_idx])

    return classify


def get_default_classifier() -> Classifier:
    """Raises on failure — callers that want graceful degradation (i.e.
    `check_entailment` below) must catch it themselves; this function's
    contract is just "give me a working classifier or tell me why not"."""
    global _classifier_singleton
    if _classifier_singleton is None:
        _classifier_singleton = _load_default_classifier()
    return _classifier_singleton


def check_entailment(sentences: list[dict], pack: EvidencePack, classifier: Classifier | None = None) -> CheckResult:
    """DEGRADATION CALL (documented explicitly, per the Part 5 brief):
    if no `classifier` is injected and the real model can't be loaded —
    no `transformers`/`torch`, no network access to fetch model weights,
    no GPU/CPU capacity — this check does NOT fail the narrative. It
    reports itself as unavailable with a neutral score (1.0, i.e. no
    penalty) and zero violations, and the failure reason is recorded in
    `details["error"]` for visibility. The blueprint's own cut-order note
    (§22: "keep the four regex checks" if scope must shrink) treats
    entailment as the one check that's acceptable to lose; a missing
    optional dependency in a given deployment environment shouldn't take
    down the four CRITICAL checks that share this same aggregation step.
    The failure is cached at module scope so a broken environment doesn't
    retry a slow model download/import on every single verify() call.
    """
    global _classifier_load_error

    active_classifier = classifier
    if active_classifier is None:
        if _classifier_load_error is not None:
            return CheckResult(
                name="entailment", severity="HIGH", passed=True, score=1.0, violations=[],
                details={"error": _classifier_load_error, "unavailable": True},
            )
        try:
            active_classifier = get_default_classifier()
        except Exception as exc:  # noqa: BLE001 - deliberately broad; see docstring
            _classifier_load_error = f"{type(exc).__name__}: {exc}"
            return CheckResult(
                name="entailment", severity="HIGH", passed=True, score=1.0, violations=[],
                details={"error": _classifier_load_error, "unavailable": True},
            )

    violations: list[Violation] = []
    scores: list[float] = []
    sentence_scores: dict[int, float] = {}

    for idx, sentence in enumerate(sentences):
        text = sentence.get("text", "")
        if not text.strip():
            continue

        items = grounded_items(text, pack)
        if not items:
            # Nothing in this sentence is grounded at all — checks 1-3
            # already own rejecting genuinely fabricated tokens; a static
            # sentence with no facts to entail (e.g. the fixed conclusion
            # boilerplate) has nothing for this check to score either way.
            continue

        premise = _build_premise(items)
        label, entail_prob = active_classifier(premise, text)
        scores.append(entail_prob)
        sentence_scores[idx] = entail_prob

        if entail_prob < ENTAILMENT_THRESHOLD:
            violations.append(
                Violation(
                    message=f"sentence not entailed by its grounded evidence (label={label}, entailment_prob={entail_prob:.3f})",
                    sentence_index=idx,
                    section=sentence.get("section"),
                )
            )

    score = sum(scores) / len(scores) if scores else 1.0
    passed = not violations
    return CheckResult(
        name="entailment", severity="HIGH", passed=passed, score=score, violations=violations,
        details={"sentence_scores": sentence_scores},
    )
