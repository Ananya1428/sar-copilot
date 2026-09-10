"""API-level tests for the narrative endpoints, using TEMPLATE mode so
they run without depending on Ollama being reachable."""

from fastapi.testclient import TestClient

from app.deps import get_db
from app.domain.evidence.case_assembly import assemble_cases
from app.main import app
from tests.factories import make_account, make_alert, make_customer


def _seed_case(db_session) -> str:
    customer = make_customer(legal_name="API Test Subject", customer_ref="CUS-API01")
    account = make_account(customer=customer, account_ref="ACC-API01")
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


def test_generate_narrative_endpoint_template_mode(db_session, make_auth_headers):
    case_id = _seed_case(db_session)
    headers = make_auth_headers("analyst")

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        client = TestClient(app)
        resp = client.post(f"/api/v1/cases/{case_id}/narrative", params={"mode": "TEMPLATE"}, headers=headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["generation_mode"] == "TEMPLATE"
        assert body["body"].strip()
        assert body["sentences"]
        assert all("evidence_keys" in s for s in body["sentences"])

        narrative_id = body["id"]
        get_resp = client.get(f"/api/v1/narratives/{narrative_id}", headers=headers)
        assert get_resp.status_code == 200
        fetched = get_resp.json()
        assert fetched["generation_mode"] == "TEMPLATE"
        assert len(fetched["sentences"]) == len(body["sentences"])
    finally:
        app.dependency_overrides.clear()
