"""Check 2 — entity grounding."""

from app.domain.verification.entity import check_entities
from tests.narrative_factories import make_sample_pack


def test_grounded_name_passes():
    pack = make_sample_pack()
    sentences = [{"text": "Rajesh Mehta conducted the activity.", "section": "who", "evidence_keys": []}]
    result = check_entities(sentences, pack)
    assert result.passed


def test_fabricated_name_fails_even_with_a_plausible_looking_evidence_key():
    pack = make_sample_pack()
    sentences = [{"text": "The activity was conducted by Suresh Kapoor.", "section": "who", "evidence_keys": ["subject.primary.legal_name"]}]
    result = check_entities(sentences, pack)
    assert not result.passed
    assert any(v.token == "Suresh Kapoor" for v in result.violations)


def test_wrong_evidence_key_on_a_correct_entity_still_passes():
    pack = make_sample_pack()
    sentences = [{"text": "The activity was conducted by Rajesh Mehta.", "section": "who", "evidence_keys": ["subjects", "legal_name"]}]
    result = check_entities(sentences, pack)
    assert result.passed


def test_sentence_initial_word_is_excluded():
    pack = make_sample_pack()
    sentences = [{"text": "The activity occurred over two days.", "section": "what_when", "evidence_keys": []}]
    result = check_entities(sentences, pack)
    assert result.passed


def test_reference_codes_are_not_mistaken_for_entities():
    pack = make_sample_pack()
    sentences = [{"text": "Transaction TXN-0001 and customer CUS-4471 were reviewed.", "section": "what_when", "evidence_keys": []}]
    result = check_entities(sentences, pack)
    assert result.passed, result.violations


def test_domain_acronyms_are_not_mistaken_for_entities():
    pack = make_sample_pack()
    sentences = [{"text": "The deposit was consistent with STRUCTURING patterns paid in USD via ACH.", "section": "how", "evidence_keys": []}]
    result = check_entities(sentences, pack)
    assert result.passed, result.violations


def test_typology_label_words_are_not_mistaken_for_fabricated_entities():
    """A typology's label ("Structuring / smurfing (deposits)") is a
    fixed, evidence-backed string (type="text", not an entity item) that
    the real deterministic template quotes verbatim mid-sentence — it
    must not be flagged just because it's capitalised."""
    pack = make_sample_pack()
    sentences = [{
        "text": "The activity is consistent with Structuring / smurfing (deposits): 2 deposits below the reporting threshold.",
        "section": "why", "evidence_keys": [],
    }]
    result = check_entities(sentences, pack)
    assert result.passed, result.violations


def test_grounded_country_code_passes_but_fabricated_one_fails():
    pack = make_sample_pack()
    ok = check_entities([{"text": "A counterparty was located in IN.", "section": "where", "evidence_keys": []}], pack)
    assert ok.passed

    bad = check_entities([{"text": "A counterparty was located in XX.", "section": "where", "evidence_keys": []}], pack)
    assert not bad.passed
