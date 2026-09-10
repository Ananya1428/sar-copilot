"""API tests for the audit trail and hash-chain verification endpoints
(blueprint §11.2 GET /audit/case/{id}, POST /audit/verify-chain)."""

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.deps import get_db
from app.domain.evidence.case_assembly import assemble_cases
from app.main import app
from tests.factories import make_account, make_alert, make_customer


def _seed_case(db_session) -> str:
    customer = make_customer(legal_name="Audit Test Subject", customer_ref="CUS-AUD01")
    account = make_account(customer=customer, account_ref="ACC-AUD01")
    db_session.add_all([customer, account])
    db_session.flush()

    alert = make_alert(
        account,
        rule_code="STRUCTURING",
        severity="HIGH",
        score="0.9000",
        rule_evidence={"account_ref": account.account_ref, "txn_count": 0, "total": "0.00", "transaction_refs": []},
    )
    db_session.add(alert)
    db_session.flush()

    assemble_cases(db_session)
    db_session.flush()
    db_session.refresh(alert)
    return str(alert.case_id)


def _client(db_session) -> TestClient:
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def test_audit_trail_shows_case_opened_evidence_built_narrative_generated(db_session):
    case_id = _seed_case(db_session)
    client = _client(db_session)
    try:
        client.post(f"/api/v1/cases/{case_id}/narrative", params={"mode": "TEMPLATE"})

        resp = client.get(f"/api/v1/audit/case/{case_id}")
        assert resp.status_code == 200
        body = resp.json()
        actions = [r["action"] for r in body["records"]]
        assert actions == ["CASE_OPENED", "EVIDENCE_BUILT", "NARRATIVE_GENERATED"]

        # chain linkage visible through the API response too
        prev_hash = "0" * 64
        for record in body["records"]:
            assert record["prev_hash"] == prev_hash
            prev_hash = record["record_hash"]
    finally:
        app.dependency_overrides.clear()


def test_verify_chain_passes_on_untouched_data(db_session):
    case_id = _seed_case(db_session)
    client = _client(db_session)
    try:
        client.post(f"/api/v1/cases/{case_id}/narrative", params={"mode": "TEMPLATE"})

        resp = client.post("/api/v1/audit/verify-chain", json={"case_id": case_id})
        assert resp.status_code == 200
        assert resp.json() == {"valid": True, "broken_at": None, "reason": None}
    finally:
        app.dependency_overrides.clear()


def test_verify_chain_detects_a_record_corrupted_directly_in_postgres(db_session):
    case_id = _seed_case(db_session)
    client = _client(db_session)
    try:
        client.post(f"/api/v1/cases/{case_id}/narrative", params={"mode": "TEMPLATE"})

        trail = client.get(f"/api/v1/audit/case/{case_id}").json()
        evidence_built = next(r for r in trail["records"] if r["action"] == "EVIDENCE_BUILT")

        db_session.execute(
            text("UPDATE audit_records SET after_state = CAST(:new_state AS jsonb) WHERE id = :id"),
            {"new_state": '{"pack_id": "tampered", "content_hash": "deadbeef"}', "id": evidence_built["id"]},
        )
        db_session.flush()

        resp = client.post("/api/v1/audit/verify-chain", json={"case_id": case_id})
        assert resp.status_code == 200
        result = resp.json()
        assert result["valid"] is False
        assert result["broken_at"] == evidence_built["id"]
        assert "tampered" in result["reason"]
    finally:
        app.dependency_overrides.clear()
