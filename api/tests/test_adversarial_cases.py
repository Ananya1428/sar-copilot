"""The week 5 gate (blueprint §22): each hand-crafted adversarial case
(eval/adversarial_cases.py) must be caught by exactly the check it targets
— no more, no less. The relationship-fabrication case is the headline
result: it must pass checks 1-4 and be caught ONLY by entailment."""

import pytest

from eval.adversarial_cases import build_cases, run_case
from tests.narrative_factories import make_sample_pack

CASES = {case.name: case for case in build_cases()}


@pytest.mark.parametrize("name", sorted(CASES))
def test_case_is_caught_by_exactly_the_expected_check(name):
    case = CASES[name]
    pack = make_sample_pack()
    report, _elapsed = run_case(case, pack)

    # expected_catcher=None (currently only single_digit_account) means NO
    # check is expected to fire — a documented pipeline blind spot, not an
    # oversight in this test. also_catchers covers cases (system_disclosure)
    # where the injected error legitimately trips more than one check at
    # once. See adversarial_cases.py's module-level comments for both.
    expected = ({case.expected_catcher} if case.expected_catcher is not None else set()) | set(case.also_catchers)
    failing = {check_name for check_name, result in report.checks.items() if not result.passed}
    assert failing == expected, f"{name}: expected only {expected or '(nothing)'} to fail, got {sorted(failing)}"


def test_relationship_fabrication_passes_checks_1_through_4():
    """The single most important assertion in this suite (per the Part 5
    brief): every individual token is real and grounded, so numeric,
    entity, temporal, and prohibited must all pass; only the compound
    relational claim is fabricated, so only entailment may fail."""
    case = CASES["relationship_fabrication"]
    pack = make_sample_pack()
    report, _elapsed = run_case(case, pack)

    assert report.checks["numeric"].passed
    assert report.checks["entity"].passed
    assert report.checks["temporal"].passed
    assert report.checks["prohibited"].passed
    assert not report.checks["entailment"].passed


def test_clean_baseline_passes_every_check():
    from eval.adversarial_cases import base_sentences, make_stub_classifier
    from app.domain.verification.pipeline import run_pipeline

    pack = make_sample_pack()
    report = run_pipeline(base_sentences(), pack, entailment_classifier=make_stub_classifier(frozenset()))
    assert report.passed
    assert all(result.passed for result in report.checks.values())
