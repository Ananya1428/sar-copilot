"""The Week 5 gate (blueprint §22: "the week 5 gate is the project") and
the adversarial half of §23's evaluation methodology: hand-crafted
narratives, each built from `tests.narrative_factories.make_sample_pack()`
with exactly ONE deliberately injected error, labeled with which check(s)
(`pipeline.WEIGHTS` keys) must be the one(s) to catch it.

The full ten-case suite blueprint §23.3 describes: six cases added in
Part 5 that map one-to-one onto Part 5's six checks, plus four more added
in Part 7 (intent_speculation, silent_rounding, system_disclosure,
single_digit_account) to reach the blueprint's complete list. See
EVALUATION.md for the full confusion matrix and what it actually found
(including a real, currently unaddressed blind spot —
single_digit_account).

Run directly for a human-readable report + full confusion matrix, saved
to eval/results/:

    docker compose exec api python eval/adversarial_cases.py           # real local NLI model
    docker compose exec api python eval/adversarial_cases.py --stub    # deterministic stub (fast)

or via pytest (api/tests/test_adversarial_cases.py), which always uses
the stub and asserts each case is caught by exactly the right check(s)
and NOT by the others.
"""

import json
import os
import sys
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, os.getcwd())

from app.domain.evidence.schema import EvidencePack  # noqa: E402
from app.domain.verification.pipeline import VerificationReport, run_pipeline  # noqa: E402
from app.domain.verification.semantic import Classifier  # noqa: E402
from tests.narrative_factories import make_sample_pack  # noqa: E402


@dataclass
class AdversarialCase:
    name: str
    description: str
    expected_catcher: str | None  # a key in pipeline.WEIGHTS, or None if NO check is expected to fire
    sentences: list[dict]
    # Sentence texts this case wants the (possibly stubbed) entailment
    # classifier to treat as NOT entailed — only the relationship-
    # fabrication case sets this; every other case relies on the real
    # checks 1-4/prohibited/completeness alone.
    low_entailment_texts: frozenset[str] = frozenset()
    # Additional checks legitimately expected to ALSO fail alongside
    # expected_catcher — e.g. system_disclosure's fabricated score is both
    # a prohibited self-reference AND an ungrounded number; forcing that
    # into a single-check isolation would mean rewriting away the task's
    # own literal example text for no honest benefit. Empty for every case
    # that genuinely does isolate to one check.
    also_catchers: frozenset[str] = frozenset()


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

    # blueprint §23.3's remaining four cases (Part 7). All four reuse the
    # same base pack/sentences as the six above; only one sentence changes
    # per case, same discipline.

    # "appears to have been done in order to conceal" — prohibited.py's
    # SPECULATION family (r"\bappears to (be|have)\b", r"\bin order to
    # (evade|avoid|conceal)\b"), not a numeric/entity/temporal issue at all.
    intent_speculation = deepcopy(clean)
    for s in intent_speculation:
        if s["section"] == "why":
            s["text"] += " This appears to have been done in order to conceal the source of funds."

    # The real observed_monthly_volume is 128500.00 (see
    # narrative_factories.make_sample_pack) — "approximately 130,000.00" is
    # a small, plausible-sounding rounding that is still a fabricated
    # number: the numeric check has zero tolerance for "close enough",
    # which is the entire point of this case (blueprint's "silent
    # rounding" attack — the kind of drift a human reviewer skimming past
    # a big number would very plausibly wave through).
    silent_rounding = _replace_sentence(
        clean, "why",
        "Observed monthly volume of approximately 130,000.00 was substantially above the "
        "expected monthly volume of 15000.00 declared for this customer.",
    )

    # "anomaly score" is a literal entry in prohibited.py's
    # SYSTEM_SELF_REFERENCE family — this is the narrative naming its own
    # detection machinery, which blueprint §14.4/§26 both flag as an
    # absolute prohibition regardless of whether the number itself is real.
    system_disclosure = deepcopy(clean)
    for s in system_disclosure:
        if s["section"] == "how":
            s["text"] += " An anomaly score of 0.87 was assigned by the detection system."

    # The real account is ACC-88213 (narrative_factories.make_sample_pack);
    # this case substitutes ACC-88214 — a single digit off. Deliberately
    # NOT expected to be caught by any of the six checks: numeric.py's
    # REFERENCE_CODE regex (`[A-Za-z]+-\d+`) excludes an entire reference
    # code's digit run from numeric grounding by design (so a real account
    # ref's digits are never flagged as an "ungrounded number"), and
    # entity.py's CAPITALIZED_SEQUENCE pattern has a negative lookahead
    # `(?!-\d)` that refuses to treat "ACC" followed by "-88214" as a
    # candidate entity at all — both exclusions exist specifically to avoid
    # false-positiving on legitimate reference codes, and a single-digit
    # substitution exploits exactly that blind spot. See eval/results/ for
    # whether the real entailment model catches it anyway (it wasn't
    # designed to, but semantic dissonance is possible); the stub
    # classifier used by the pytest suite below will not.
    single_digit_account_text = "Rajesh Mehta holds account ACC-88214 and has been a customer since 2021-06-14, with a stated occupation of Retail Trader."
    single_digit_account = _replace_sentence(clean, "who", single_digit_account_text)

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
        AdversarialCase(
            name="intent_speculation",
            description="Unfounded speculation about intent/motive, phrased plausibly.",
            expected_catcher="prohibited",
            sentences=intent_speculation,
        ),
        AdversarialCase(
            name="silent_rounding",
            description="A materially-rounded figure presented as the real one (128500.00 -> ~130,000.00).",
            expected_catcher="numeric",
            sentences=silent_rounding,
        ),
        AdversarialCase(
            name="system_disclosure",
            description="The narrative discloses its own detection system's internal output (an anomaly score).",
            expected_catcher="prohibited",
            sentences=system_disclosure,
            # The disclosed score ("0.87") is itself a number absent from
            # the evidence pack, so numeric legitimately fails too — two
            # independent checks both catching the same fabrication is a
            # real defense-in-depth result, not a test design flaw.
            also_catchers=frozenset({"numeric"}),
        ),
        AdversarialCase(
            name="single_digit_account",
            description="A single-digit account-number substitution (ACC-88213 -> ACC-88214) — a known pipeline blind spot, see module docstring.",
            expected_catcher=None,
            sentences=single_digit_account,
            # Deliberately NOT added to low_entailment_texts: the stub
            # classifier (used by the fast pytest suite) should behave like
            # an agreeable baseline here, same as every other clean
            # sentence, so that suite honestly demonstrates "checks 1-4
            # plus a non-adversarial entailment stand-in catch nothing."
            # Whether the REAL entailment model catches this by accident
            # (semantic dissonance, not by design) is an empirical
            # question answered separately by run_full_suite() below,
            # against the real model — not scripted here.
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


def run_case(case: AdversarialCase, pack: EvidencePack, use_real_model: bool = False) -> tuple[VerificationReport, float]:
    """`use_real_model=False` (the default — what the fast pytest suite
    uses) builds this case's stub classifier. `use_real_model=True` passes
    `entailment_classifier=None` through to `run_pipeline`, which is what
    actually triggers semantic.py's real lazy-loaded local NLI model — an
    earlier version of this function conflated "no classifier object
    passed in" with "use the stub", which meant asking for the real model
    silently got the stub instead (the giveaway: entailment scores landing
    on exactly the stub's hardcoded 0.95/0.05 no matter what). Fixed by
    making the choice an explicit flag instead of overloading None.
    """
    classifier = None if use_real_model else make_stub_classifier(case.low_entailment_texts)
    start = time.monotonic()
    report = run_pipeline(case.sentences, pack, entailment_classifier=classifier)
    elapsed = time.monotonic() - start
    return report, elapsed


# A human reviewer skimming a fluent, well-formatted draft would very
# plausibly wave these through — they're the headline result per blueprint
# §23.3. `single_digit_account` is included here too even though the
# pipeline is NOT expected to catch it (see its case docstring) — it's a
# human-plausible miss either way, just one where we can't yet claim the
# system does better.
HUMAN_PLAUSIBLE_MISSES = frozenset({"relationship_fabrication", "silent_rounding", "single_digit_account"})


def main() -> int:
    """Full ten-case confusion matrix (blueprint §23.3 / Part 7).

    By default uses the real local NLI entailment model (None ->
    semantic.py lazy-loads it), because this is meant to be a genuine
    evaluation record of the ACTUAL production pipeline, not the
    deterministic stub the fast pytest suite uses for CI speed. Pass
    --stub to use the stub instead (useful for a quick sanity check
    without waiting on model load / GPU inference).
    """
    use_stub = "--stub" in sys.argv
    pack = make_sample_pack()
    cases = build_cases()

    results = []
    print(f"{'case':24s} {'expected':13s} {'caught_by':40s} {'result':10s} {'elapsed_s':>9s}")
    print("-" * 100)

    all_ok = True
    for case in cases:
        report, elapsed = run_case(case, pack, use_real_model=not use_stub)
        caught_by = sorted(name for name, result in report.checks.items() if not result.passed)
        expected_set = ({case.expected_catcher} if case.expected_catcher is not None else set()) | set(case.also_catchers)
        expected = sorted(expected_set)
        ok = caught_by == expected
        all_ok = all_ok and ok
        label = "CAUGHT" if (ok and expected) else ("OK (no catch)" if ok else "MISS")
        results.append(
            {
                "case": case.name,
                "description": case.description,
                "expected_catcher": case.expected_catcher,
                "caught_by": caught_by,
                "outcome": label,
                "human_plausible_miss": case.name in HUMAN_PLAUSIBLE_MISSES,
                "elapsed_s": round(elapsed, 4),
            }
        )
        expected_str = case.expected_catcher or "(none)"
        print(f"{case.name:24s} {expected_str:13s} {', '.join(caught_by) or '(none)':40s} {label:10s} {elapsed:9.3f}")

    print("-" * 100)
    print(f"classifier: {'stub (deterministic)' if use_stub else 'real local NLI model'}")
    print("ALL CASES BEHAVED AS EXPECTED" if all_ok else "SOME CASES DID NOT MATCH THE EXPECTED CATCHER — see MISS rows above")
    print()
    print("Human-plausible misses (a reviewer skimming a fluent draft would very likely wave these through):")
    for r in results:
        if r["human_plausible_miss"]:
            verdict = "caught by the pipeline" if r["caught_by"] else "NOT caught by the pipeline"
            print(f"  - {r['case']}: {verdict} ({', '.join(r['caught_by']) or 'no check fired'})")

    suffix = "stub" if use_stub else "real_nli"
    out_path = Path(__file__).parent / "results" / f"adversarial_suite_{suffix}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"classifier": suffix, "cases": results}, indent=2))
    print(f"\nWrote {out_path}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
