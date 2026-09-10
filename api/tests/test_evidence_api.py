"""API tests for GET /evidence/{pack_id} — fetching a specific evidence
pack by id, not just "latest for a case" (api/v1/cases.py's endpoint)."""

from fastapi.testclient import TestClient

from app.deps import get_db
from app.domain.evidence.builder import build_evidence_pack, persist_evidence_pack
from app.domain.evidence.case_assembly import assemble_cases
from app.main import app
from tests.factories import make_account, make_alert, make_customer


def _seed_case_with_evidence(db_session):
    customer = make_customer(legal_name="Evidence Test Subject", customer_ref="CUS-EVI01")
    account = make_account(customer=customer, account_ref="ACC-EVI01")
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

    from app.models.case import Case

    case_obj = db_session.get(Case, alert.case_id)
    pack = build_evidence_pack(db_session, case_obj)
    pack_row = persist_evidence_pack(db_session, case_obj, pack)
    db_session.flush()
    return pack_row.id


def test_get_evidence_pack_by_id(db_session):
    pack_id = _seed_case_with_evidence(db_session)

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        client = TestClient(app)
        resp = client.get(f"/api/v1/evidence/{pack_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pack_id"] == str(pack_id)
        assert len(body["items"]) > 0
    finally:
        app.dependency_overrides.clear()


def test_get_evidence_pack_by_id_404_for_unknown_id(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        client = TestClient(app)
        resp = client.get("/api/v1/evidence/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_get_evidence_pack_by_id_400_for_invalid_id(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        client = TestClient(app)
        resp = client.get("/api/v1/evidence/not-a-uuid")
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()
