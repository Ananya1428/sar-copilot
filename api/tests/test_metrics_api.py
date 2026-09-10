"""API test for the quality metrics endpoint (blueprint §11.2
GET /metrics/quality)."""

from fastapi.testclient import TestClient

from app.deps import get_db
from app.domain.evidence.case_assembly import assemble_cases
from app.main import app
from tests.factories import make_account, make_alert, make_customer


def _seed_and_generate(db_session, ref_suffix: str) -> dict:
    customer = make_customer(legal_name="Metrics Test Subject", customer_ref=f"CUS-MET{ref_suffix}")
    account = make_account(customer=customer, account_ref=f"ACC-MET{ref_suffix}")
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

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    resp = client.post(f"/api/v1/cases/{alert.case_id}/narrative", params={"mode": "TEMPLATE"})
    assert resp.status_code == 200
    return resp.json()


def test_quality_metrics_reflects_generated_narratives(db_session):
    try:
        _seed_and_generate(db_session, "01")
        _seed_and_generate(db_session, "02")

        client = TestClient(app)
        resp = client.get("/api/v1/metrics/quality")
        assert resp.status_code == 200
        body = resp.json()

        assert body["narrative_count"] >= 2
        assert body["verification_report_count"] >= 2
        assert "TEMPLATE" in body["pass_rate_by_mode"]
        assert body["pass_rate_by_mode"]["TEMPLATE"] is not None
        assert 0.0 <= body["pass_rate_by_mode"]["TEMPLATE"] <= 1.0
        assert "TEMPLATE" in body["mean_overall_score_by_mode"]

        for check_name in ["numeric", "entity", "temporal", "prohibited", "entailment", "completeness"]:
            assert check_name in body["failure_count_by_check"]

        assert body["generation_latency"]["available"] is False
        assert isinstance(body["human_edit_rate"]["value"], (float, int, type(None)))
        assert body["human_edit_rate"]["total_narratives"] >= 2
    finally:
        app.dependency_overrides.clear()
