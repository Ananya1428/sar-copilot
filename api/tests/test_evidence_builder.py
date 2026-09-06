"""Evidence builder tests against a hand-constructed case (not the live
generator), so the expected pack content is known exactly rather than
inferred after the fact."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.domain.detection.thresholds import RULE_WEIGHTS
from app.domain.evidence.builder import build_evidence_pack, persist_evidence_pack
from app.models import Case, CaseSubject
from app.models.evidence import EvidencePack as EvidencePackRow
from tests.factories import make_account, make_alert, make_customer, make_txn

BASE = datetime(2024, 3, 1, 12, 0, tzinfo=UTC)


def _build_test_case(db_session):
    customer = make_customer(legal_name="Rajesh Mehta", customer_ref="CUS-4471", country="IN", occupation="Retail Trader")
    account = make_account(customer=customer, account_ref="ACC-88213", expected_monthly_volume="15000.00")
    db_session.add_all([customer, account])
    db_session.flush()

    structuring_txns = [
        make_txn(account, "8600.00", "credit", BASE + timedelta(days=i), is_cash=True) for i in range(4)
    ]
    # Outside the structuring window entirely (a month earlier) — must be
    # excluded from the pack by the period filter, proving it actually filters.
    background_txn = make_txn(account, "300.00", "debit", BASE - timedelta(days=30), channel="card")
    db_session.add_all([*structuring_txns, background_txn])
    db_session.flush()

    rule_evidence = {
        "account_ref": account.account_ref,
        "txn_count": 4,
        "total": "34400.00",
        "window": {"start": BASE.isoformat(), "end": (BASE + timedelta(days=7)).isoformat()},
        "transaction_refs": [t.txn_ref for t in structuring_txns],
    }
    alert = make_alert(account, rule_code="STRUCTURING", severity="HIGH", score="0.8500", rule_evidence=rule_evidence, raised_at=BASE)
    db_session.add(alert)
    db_session.flush()

    case = Case(case_ref="CASE-TEST1", status="OPEN", risk_score=alert.score, opened_at=BASE)
    db_session.add(case)
    db_session.flush()
    alert.case_id = case.id
    db_session.add(CaseSubject(case_id=case.id, customer_id=customer.id, role="primary"))
    db_session.flush()

    return case, customer, account, alert, structuring_txns, background_txn


def test_builder_populates_real_subject_data(db_session):
    case, customer, account, alert, txns, _ = _build_test_case(db_session)
    pack = build_evidence_pack(db_session, case)

    assert pack.case_ref == "CASE-TEST1"
    assert len(pack.subjects) == 1
    subj = pack.subjects[0]
    assert subj.legal_name == "Rajesh Mehta"
    assert subj.customer_ref == "CUS-4471"
    assert subj.role == "primary"
    assert subj.account_refs == ["ACC-88213"]
    assert subj.country == "IN"
    assert subj.occupation == "Retail Trader"
    assert subj.expected_monthly_volume == Decimal("15000.00")


def test_builder_populates_real_typology_data(db_session):
    case, _customer, _account, _alert, structuring_txns, _bg = _build_test_case(db_session)
    pack = build_evidence_pack(db_session, case)

    assert len(pack.typologies) == 1
    typ = pack.typologies[0]
    assert typ.code == "STRUCTURING"
    assert typ.label  # sourced from data/reference/typology_dictionary.json
    assert typ.weight == RULE_WEIGHTS["STRUCTURING"]
    assert typ.quantitative_basis["txn_count"] == 4
    assert typ.quantitative_basis["total"] == "34400.00"
    assert set(typ.supporting_txn_refs) == {t.txn_ref for t in structuring_txns}


def test_builder_filters_transactions_to_the_evidence_period(db_session):
    case, customer, account, alert, structuring_txns, background_txn = _build_test_case(db_session)
    pack = build_evidence_pack(db_session, case)

    pack_refs = {t.txn_ref for t in pack.transactions}
    assert pack_refs == {t.txn_ref for t in structuring_txns}
    assert background_txn.txn_ref not in pack_refs

    for t in pack.transactions:
        assert t.flagged_by == ["STRUCTURING"]


def test_builder_computes_real_aggregates(db_session):
    case, customer, account, alert, structuring_txns, _ = _build_test_case(db_session)
    pack = build_evidence_pack(db_session, case)

    agg = pack.aggregates
    assert agg.txn_count == 4
    assert agg.total_credit == Decimal("34400.00")
    assert agg.total_debit == Decimal("0")
    assert agg.cash_txn_count == 4
    assert agg.max_single_amount == Decimal("8600.00")


def test_builder_leaves_ml_and_graph_findings_empty_when_no_such_alert(db_session):
    case, *_ = _build_test_case(db_session)
    pack = build_evidence_pack(db_session, case)

    assert pack.ml_findings == {}
    assert pack.graph_findings == {}
    assert pack.prior_sars == []


def test_builder_is_deterministic(db_session):
    case, *_ = _build_test_case(db_session)
    pack_a = build_evidence_pack(db_session, case)
    pack_b = build_evidence_pack(db_session, case)

    assert pack_a.pack_id != pack_b.pack_id  # fresh identity each build
    assert pack_a.content_hash == pack_b.content_hash  # identical substantive content


def test_persisted_pack_creates_a_new_row_each_time(db_session):
    case, *_ = _build_test_case(db_session)
    pack_a = build_evidence_pack(db_session, case)
    persist_evidence_pack(db_session, case, pack_a)

    pack_b = build_evidence_pack(db_session, case)
    persist_evidence_pack(db_session, case, pack_b)

    rows = db_session.query(EvidencePackRow).filter(EvidencePackRow.case_id == case.id).all()
    assert len(rows) == 2
    assert {r.id for r in rows} == {pack_a.pack_id, pack_b.pack_id}


def test_every_fact_used_in_the_pack_has_a_matching_evidence_item(db_session):
    """The enumerability invariant (blueprint §10.2's own emphasis): every
    unique amount/name/date/location used in subjects, transactions,
    typologies, or aggregates must also appear as an EvidenceItem, or
    Part 5's verification pipeline has no way to check it."""
    case, *_ = _build_test_case(db_session)
    pack = build_evidence_pack(db_session, case)

    allowed_numbers = pack.allowed_numbers()
    allowed_dates = pack.allowed_dates()
    allowed_entities = pack.allowed_entities()  # entity + location
    allowed_text = {i.display_value for i in pack.items if i.type == "text"}
    allowed_typology = {i.display_value for i in pack.items if i.type == "typology"}

    for s in pack.subjects:
        assert s.legal_name in allowed_entities, s.legal_name
        assert s.customer_ref in allowed_text, s.customer_ref
        assert s.country in allowed_entities, s.country
        assert s.risk_rating in allowed_text, s.risk_rating
        assert str(s.expected_monthly_volume) in allowed_numbers
        assert str(s.observed_monthly_volume) in allowed_numbers
        assert s.relationship_start.isoformat() in allowed_dates
        if s.occupation:
            assert s.occupation in allowed_entities, s.occupation
        for ref in s.account_refs:
            assert ref in allowed_text, ref

    for t in pack.transactions:
        assert t.txn_ref in allowed_text, t.txn_ref
        assert str(t.amount) in allowed_numbers, t.amount
        assert t.executed_at.date().isoformat() in allowed_dates
        assert t.channel in allowed_text
        if t.counterparty_ref:
            assert t.counterparty_ref in allowed_text
        if t.counterparty_country:
            assert t.counterparty_country in allowed_entities

    for typ in pack.typologies:
        assert typ.code in allowed_typology, typ.code

    agg = pack.aggregates
    assert str(agg.total_credit) in allowed_numbers
    assert str(agg.total_debit) in allowed_numbers
    assert str(agg.max_single_amount) in allowed_numbers
    assert agg.period_start.isoformat() in allowed_dates
    assert agg.period_end.isoformat() in allowed_dates
    for country in agg.distinct_countries:
        assert country in allowed_entities

    # Every item must itself point at a real source row (this build's
    # traceability guarantee) — spot-check the shape rather than every row.
    for item in pack.items:
        assert item.source_table
        assert item.source_row_id is not None
