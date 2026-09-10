"""API tests for narrative editing/versioning (blueprint §11.2
PATCH /narratives/{id}, GET /narratives/{id}/diff/{v})."""

from fastapi.testclient import TestClient

from app.deps import get_db
from app.domain.evidence.case_assembly import assemble_cases
from app.main import app
from tests.factories import make_account, make_alert, make_customer


def _seed_narrative(db_session, headers: dict) -> tuple[str, dict]:
    customer = make_customer(legal_name="Versioning Test Subject", customer_ref="CUS-VER01")
    account = make_account(customer=customer, account_ref="ACC-VER01")
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
    case_id = str(alert.case_id)

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    resp = client.post(f"/api/v1/cases/{case_id}/narrative", params={"mode": "TEMPLATE"}, headers=headers)
    assert resp.status_code == 200
    return case_id, resp.json()


def test_patch_creates_a_new_version_and_reverifies(db_session, make_auth_headers):
    analyst_headers = make_auth_headers("analyst")
    case_id, original = _seed_narrative(db_session, analyst_headers)
    client = TestClient(app)
    try:
        edited_sentences = [
            {"text": s["text"], "section": s["section"], "evidence_keys": s["evidence_keys"]}
            for s in original["sentences"]
        ]
        # Edit one sentence's text without introducing any new claim, so it
        # stays fully grounded in the same evidence it already cited.
        edited_sentences[0]["text"] = edited_sentences[0]["text"] + " (analyst reviewed.)"

        resp = client.patch(
            f"/api/v1/narratives/{original['id']}", json={"sentences": edited_sentences}, headers=analyst_headers
        )
        assert resp.status_code == 200
        edited = resp.json()

        assert edited["id"] != original["id"]
        assert edited["version"] == original["version"] + 1
        assert edited["pack_id"] == original["pack_id"]
        assert "(analyst reviewed.)" in edited["body"]

        # a NARRATIVE_EDITED audit record was written — audit trail viewing
        # is reviewer+ (RBAC §11.3), so a different role's token is needed here
        trail = client.get(f"/api/v1/audit/case/{case_id}", headers=make_auth_headers("reviewer")).json()
        assert "NARRATIVE_EDITED" in [r["action"] for r in trail["records"]]
    finally:
        app.dependency_overrides.clear()


def test_diff_endpoint_shows_both_versions_and_a_line_diff(db_session, make_auth_headers):
    analyst_headers = make_auth_headers("analyst")
    case_id, original = _seed_narrative(db_session, analyst_headers)
    client = TestClient(app)
    try:
        edited_sentences = [
            {"text": s["text"], "section": s["section"], "evidence_keys": s["evidence_keys"]}
            for s in original["sentences"]
        ]
        edited_sentences[0]["text"] = edited_sentences[0]["text"] + " (analyst reviewed.)"
        patch_resp = client.patch(
            f"/api/v1/narratives/{original['id']}", json={"sentences": edited_sentences}, headers=analyst_headers
        )
        edited = patch_resp.json()

        # diff viewing is reviewer+ (RBAC §11.3) — a different role's token
        diff_resp = client.get(
            f"/api/v1/narratives/{edited['id']}/diff/{original['version']}", headers=make_auth_headers("reviewer")
        )
        assert diff_resp.status_code == 200
        diff_body = diff_resp.json()

        assert diff_body["this_version"]["version"] == edited["version"]
        assert diff_body["other_version"]["version"] == original["version"]
        assert diff_body["this_version"]["verification"] is not None
        assert diff_body["other_version"]["verification"] is not None
        assert any("analyst reviewed" in line for line in diff_body["diff"])
    finally:
        app.dependency_overrides.clear()
