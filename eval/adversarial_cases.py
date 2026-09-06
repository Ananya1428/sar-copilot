"""The Week 5 gate (blueprint §22: "the week 5 gate is the project") and
the adversarial half of §23's evaluation methodology: hand-crafted
narratives, each built from `tests.narrative_factories.make_sample_pack()`
with exactly ONE deliberately injected error, labeled with which of the
six checks (`pipeline.WEIGHTS` keys) must be the one to catch it.

This is a SUBSET of the full ten-case suite the blueprint describes (the
full ten cases + a confusion matrix across TEMPLATE/HYBRID/FREEFORM is
Part 7's job) — the six cases that map one-to-one onto Part 5's six
checks, per this part's brief.

Run directly for a human-readable report:

    docker compose exec api python eval/adversarial_cases.py

or via pytest (api/tests/test_adversarial_cases.py), which asserts each
case is caught by exactly the right check and NOT by the others.
"""

import os
import sys
import time
from copy import deepcopy
from dataclasses import dataclass

sys.path.insert(0, os.getcwd())

from app.domain.evidence.schema import EvidencePack  # noqa: E402
from app.domain.verification.pipeline import VerificationReport, run_pipeline  # noqa: E402
from app.domain.verification.semantic import Classifier  # noqa: E402
from tests.narrative_factories import make_sample_pack  # noqa: E402


@dataclass
class AdversarialCase:
    name: str
    description: str
    expected_catcher: str  # a key in pipeline.WEIGHTS, or None if nothing should fire
    sentences: list[dict]
    # Sentence texts this case wants the (possibly stubbed) entailment
    # classifier to treat as NOT entailed — only the relationship-
    # fabrication case sets this; every other case relies on the real
    # checks 1-4/prohibited/completeness alone.
    low_entailment_texts: frozenset[str] = frozenset()


def base_sentences() -> list[dict]:
    """A clean, fully-grounded narrative, one sentence per required
    section, built entirely from `make_sample_pack()`'s real evidence
    (cross-checked by hand against its `items` list). Every adversarial
    case below is a deepcopy of this with exactly one change."""
    return [
        {
            "section": "introduction",
            "evidence_keys": ["subject.primary.legal_name", "subject.primary.customer_ref", "aggregates.period_start", "aggregates.period_end"],
            "text": (
                "This report concerns account activity conducted by Rajesh Mehta, customer "
                "reference CUS-4471, between 2024-03-03 and 2024-03-04."
            ),
        },
        {
            "section": "who",
            "evidence_keys": ["subject.primary.legal_name", "subject.primary.account_ref.ACC-88213", "subject.primary.relationship_start", "subject.primary.occupation"],
            "text": (
                "Rajesh Mehta holds account ACC-88213 and has been a customer since 2021-06-14, "
                "with a stated occupation of Retail Trader."
            ),
        },
        {
            "section": "what_when",
            "evidence_keys": ["aggregates.total_credit", "transaction.TXN-0001.channel"],
            "text": "Two cash transactions totalling 17300.00 were recorded during the reporting period.",
        },
        {
            "section": "where",
            "evidence_keys": ["transaction.TXN-0002.counterparty_country"],
            "text": "The activity involved a counterparty located in IN.",
        },
        {
            "section": "how",
            "evidence_keys": ["typology.STRUCTURING.quantitative_basis.txn_count", "typology.STRUCTURING.quantitative_basis.total"],
            "text": (
                "The activity is consistent with structuring, comprising 2 deposits totalling "
                "17300.00 structured below the reporting threshold."
            ),
        },
        {
            "section": "why",
            "evidence_keys": ["subject.primary.observed_monthly_volume", "subject.primary.expected_monthly_volume"],
            "text": (
                "Observed monthly volume of 128500.00 was substantially above the expected "
                "monthly volume of 15000.00 declared for this customer."
            ),
        },
        {
            "section": "conclusion",
            "evidence_keys": [],
            "text": "This report has been prepared for regulatory review and retention.",
        },
    ]


def _replace_sentence(sentences: list[dict], section: str, new_text: str) -> list[dict]:
    out = deepcopy(sentences)
    for s in out:
        if s["section"] == section:
            s["text"] = new_text
            break
    return out


def build_cases() -> list[AdversarialCase]:
    clean = base_sentences()

    numeric_fabrication = _replace_sentence(
        clean, "what_when", "Two cash transactions totalling 19875.00 were recorded during the reporting period."
    )

    entity_fabrication = _replace_sentence(
        clean, "who",
        "Suresh Kapoor holds account ACC-88213 and has been a customer since 2021-06-14, with a stated occupation of Retail Trader.",
    )

    # THE key test (per the Part 5 brief): every token here is real and
    # individually grounded — "Rajesh Mehta" (entity), "8600.00" (TXN-0001's
    # real amount), "2024-03-04" (a real date, but TXN-0001's real date is
    # 2024-03-03, not this one) — but the RELATIONSHIP asserted (a wire
    # transfer, on this date, to this counterparty) never happened: TXN-0001
    # was a cash credit with no counterparty, not a wire; "external-party"
    # is TXN-0002's counterparty, not TXN-0001's; the date is wrong too, but
    # deliberately a date that IS itself in allowed_dates() (2024-03-04 is
    # TXN-0002's real date) so this isn't secretly a temporal-grounding
    # failure. Checks 1-4 must all pass this sentence; only entailment,
    # scoring whether the DISCONNECTED facts behind it actually support the
    # compound claim, can catch it.
    relationship_text = (
        "Rajesh Mehta transferred 8600.00 by wire to external-party on 2024-03-04."
    )
    relationship_fabrication = _replace_sentence(clean, "what_when", relationship_text)

    legal_conclusion = deepcopy(clean)
    for s in legal_conclusion:
        if s["section"] == "how":
            s["text"] += " Rajesh Mehta committed money laundering."

    # 2021-06-14 legitimately appears in allowed_dates() (it's the
    # relationship_start date) — it's grounded, so this is specifically a
    # PERIOD violation, not a fabricated-date violation, exercising the
    # other half of the temporal check.
    date_outside_period = _replace_sentence(
        clean, "what_when", "A transaction attributed to this pattern was recorded on 2021-06-14."
    )

    section_omission = [s for s in deepcopy(clean) if s["section"] != "why"]

    return [
        AdversarialCase(
            name="numeric_fabrication",
            description="A fabricated total amount not present anywhere in the evidence pack.",
            expected_catcher="numeric",
            sentences=numeric_fabrication,
        ),
        AdversarialCase(
            name="entity_fabrication",
            description="A subject name that does not appear in the evidence pack.",
            expected_catcher="entity",
            sentences=entity_fabrication,
        ),
        AdversarialCase(
            name="relationship_fabrication",
            description="Real names/numbers/dates, but a transaction/relationship between them that never happened.",
            expected_catcher="entailment",
            sentences=relationship_fabrication,
            low_entailment_texts=frozenset({relationship_text}),
        ),
        AdversarialCase(
            name="legal_conclusion",
            description='A prohibited legal conclusion ("committed money laundering").',
            expected_catcher="prohibited",
            sentences=legal_conclusion,
        ),
        AdversarialCase(
            name="date_outside_period",
            description="A real, grounded date that falls outside the evidence pack's aggregate period.",
            expected_catcher="temporal",
            sentences=date_outside_period,
        ),
        AdversarialCase(
            name="section_omission",
            description='The required "why" section is missing entirely.',
            expected_catcher="completeness",
            sentences=section_omission,
        ),
    ]


def make_stub_classifier(low_confidence_texts: frozenset[str]) -> Classifier:
    """A deterministic fake NLI classifier for offline/CI use: this suite's
    job is proving the PIPELINE correctly isolates each failure mode to
    the right check, not benchmarking the real model's accuracy (a
    separate, empirical concern — see semantic.py's module docstring on
    graceful degradation when the real model is unavailable). Sentences
    named in `low_confidence_texts` score as contradicted; everything else
    is treated as entailed by its own grounded facts."""

    def classify(premise: str, hypothesis: str) -> tuple[str, float]:
        if hypothesis in low_confidence_texts:
            return "contradiction", 0.05
        return "entailment", 0.95

    return classify


def run_case(case: AdversarialCase, pack: EvidencePack, classifier: Classifier | None = None) -> tuple[VerificationReport, float]:
    active_classifier = classifier if classifier is not None else make_stub_classifier(case.low_entailment_texts)
    start = time.monotonic()
    report = run_pipeline(case.sentences, pack, entailment_classifier=active_classifier)
    elapsed = time.monotonic() - start
    return report, elapsed


def main() -> int:
    pack = make_sample_pack()
    cases = build_cases()

    print(f"{'case':28s} {'expected':13s} {'caught_by':40s} {'result':6s} {'elapsed_s':>9s}")
    print("-" * 100)

    all_ok = True
    for case in cases:
        report, elapsed = run_case(case, pack)
        caught_by = sorted(name for name, result in report.checks.items() if not result.passed)
        ok = caught_by == [case.expected_catcher]
        all_ok = all_ok and ok
        print(f"{case.name:28s} {case.expected_catcher:13s} {', '.join(caught_by) or '(none)':40s} {'OK' if ok else 'MISS':6s} {elapsed:9.3f}")

    print("-" * 100)
    print("ALL CASES CAUGHT BY THE RIGHT CHECK" if all_ok else "SOME CASES WERE MISCAUGHT — see MISS rows above")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
