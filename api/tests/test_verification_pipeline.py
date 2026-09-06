"""Check 7 — aggregation (blueprint §14.7): weighted score, and the rule
that a single CRITICAL failure blocks release regardless of score."""

from app.domain.narrative.deterministic import render_all_sections
from app.domain.verification.pipeline import PASS_THRESHOLD, WEIGHTS, run_pipeline
from eval.adversarial_cases import base_sentences
from tests.narrative_factories import make_sample_pack


def _entailing_classifier(premise: str, hypothesis: str) -> tuple[str, float]:
    return "entailment", 0.95


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_clean_narrative_passes_overall():
    pack = make_sample_pack()
    report = run_pipeline(base_sentences(), pack, entailment_classifier=_entailing_classifier)
    assert report.passed
    assert report.overall_score >= PASS_THRESHOLD
    assert not report.critical_failures


def test_a_single_critical_failure_blocks_release_regardless_of_score():
    """Even though only one of six checks fails, and the other five are
    perfect, a CRITICAL failure must block release outright — "no
    averaging away a fabricated account number" (blueprint §14)."""
    pack = make_sample_pack()
    sentences = list(base_sentences())
    sentences[2] = dict(sentences[2], text="Two cash transactions totalling 42.42 were recorded during the reporting period.")

    report = run_pipeline(sentences, pack, entailment_classifier=_entailing_classifier)
    assert not report.passed
    assert report.critical_failures == ["numeric"]
    # The other five checks are still clean, so the weighted score alone
    # would look passable — demonstrating that `passed` is driven by the
    # critical-failure rule, not by the score crossing PASS_THRESHOLD.
    assert report.overall_score > 0.5


def test_real_deterministic_template_output_passes_the_full_pipeline():
    """The blueprint's own claim (§13.6): the TEMPLATE fallback is
    "structurally guaranteed grounded" — it must pass all four CRITICAL
    checks against the REAL renderer output, not just hand-written test
    sentences. This is the check that caught two real bugs during
    development: ISO-date digits being mistaken for numeric tokens, and a
    typology label's capitalised words being mistaken for a fabricated
    entity, both against this exact real output."""
    pack = make_sample_pack()
    sentences = render_all_sections(pack)
    report = run_pipeline(sentences, pack, entailment_classifier=_entailing_classifier)

    for name in ("numeric", "entity", "temporal", "prohibited"):
        assert report.checks[name].passed, (name, report.checks[name].violations)


def test_to_jsonable_shape_matches_the_persisted_checks_column():
    pack = make_sample_pack()
    report = run_pipeline(base_sentences(), pack, entailment_classifier=_entailing_classifier)
    payload = report.to_jsonable()
    assert set(payload) == set(WEIGHTS)
    for check_payload in payload.values():
        assert {"severity", "passed", "score", "violations"} <= set(check_payload)
