"""Unit tests for the hash-chained ledger (blueprint §15.1): chain builds
correctly across appends, and verify_chain() detects a tampered record at
the exact point of tampering."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.domain.audit.ledger import GENESIS_HASH, AuditLedger
from app.models.case import Case


def _make_case(db_session) -> Case:
    case = Case(
        case_ref=f"CASE-TEST-{uuid.uuid4().hex[:8]}",
        status="OPEN",
        risk_score="0.9000",
        opened_at=datetime.now(UTC),
    )
    db_session.add(case)
    db_session.flush()
    return case


def test_first_record_chains_to_genesis_hash(db_session):
    case = _make_case(db_session)
    ledger = AuditLedger(db_session)

    record = ledger.append(case_id=case.id, actor_id=None, action="CASE_OPENED", after_state={"status": "OPEN"})

    assert record.prev_hash == GENESIS_HASH
    assert len(record.record_hash) == 64
    assert record.record_hash != GENESIS_HASH


def test_chain_links_each_record_to_the_previous_hash(db_session):
    case = _make_case(db_session)
    ledger = AuditLedger(db_session)

    r1 = ledger.append(case_id=case.id, actor_id=None, action="CASE_OPENED", after_state={"a": 1})
    r2 = ledger.append(case_id=case.id, actor_id=None, action="EVIDENCE_BUILT", after_state={"b": 2})
    r3 = ledger.append(case_id=case.id, actor_id=None, action="NARRATIVE_GENERATED", after_state={"c": 3})

    assert r2.prev_hash == r1.record_hash
    assert r3.prev_hash == r2.record_hash
    assert len({r1.record_hash, r2.record_hash, r3.record_hash}) == 3


def test_separate_cases_get_independent_chains(db_session):
    case_a = _make_case(db_session)
    case_b = _make_case(db_session)
    ledger = AuditLedger(db_session)

    a1 = ledger.append(case_id=case_a.id, actor_id=None, action="CASE_OPENED", after_state={})
    b1 = ledger.append(case_id=case_b.id, actor_id=None, action="CASE_OPENED", after_state={})

    assert a1.prev_hash == GENESIS_HASH
    assert b1.prev_hash == GENESIS_HASH


def test_unknown_action_is_rejected(db_session):
    case = _make_case(db_session)
    ledger = AuditLedger(db_session)

    with pytest.raises(ValueError):
        ledger.append(case_id=case.id, actor_id=None, action="MADE_UP_ACTION", after_state={})


def test_verify_chain_passes_on_an_untampered_chain(db_session):
    case = _make_case(db_session)
    ledger = AuditLedger(db_session)
    ledger.append(case_id=case.id, actor_id=None, action="CASE_OPENED", after_state={"a": 1})
    ledger.append(case_id=case.id, actor_id=None, action="EVIDENCE_BUILT", after_state={"b": 2})
    ledger.append(case_id=case.id, actor_id=None, action="NARRATIVE_GENERATED", after_state={"c": 3})

    result = ledger.verify_chain(case.id)

    assert result == {"valid": True, "broken_at": None, "reason": None}


def test_verify_chain_reports_the_exact_tampered_record(db_session):
    case = _make_case(db_session)
    ledger = AuditLedger(db_session)
    ledger.append(case_id=case.id, actor_id=None, action="CASE_OPENED", after_state={"a": 1})
    r2 = ledger.append(case_id=case.id, actor_id=None, action="EVIDENCE_BUILT", after_state={"b": 2})
    ledger.append(case_id=case.id, actor_id=None, action="NARRATIVE_GENERATED", after_state={"c": 3})

    # Mutate the middle record's after_state directly, bypassing append() —
    # simulating someone editing the row straight in Postgres.
    db_session.execute(
        text("UPDATE audit_records SET after_state = CAST(:new_state AS jsonb) WHERE id = :id"),
        {"new_state": '{"b": 999}', "id": str(r2.id)},
    )
    db_session.flush()
    db_session.expire_all()

    result = ledger.verify_chain(case.id)

    assert result["valid"] is False
    assert result["broken_at"] == str(r2.id)
    assert "tampered" in result["reason"]


def test_verify_chain_reports_empty_case_as_valid(db_session):
    case = _make_case(db_session)
    ledger = AuditLedger(db_session)

    result = ledger.verify_chain(case.id)

    assert result == {"valid": True, "broken_at": None, "reason": None}
