"""THE integration test that matters for Part 8b: proves the hand-entry
"front door" (onboarding.py) genuinely connects to the existing detection
and case-assembly engine — not just that the new endpoints don't crash.

Flow, entirely through the API: create a customer -> create an account
under it -> add real STRUCTURING-shaped transactions (amounts/count/
window read from the actual thresholds in domain/detection/thresholds.py,
not guessed) -> POST /detection/run -> POST /cases/assemble -> a real
Case now exists linking back to that hand-entered account -> generate a
narrative for it (TEMPLATE mode, so this doesn't depend on Ollama)."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.deps import get_db
from app.domain.detection import thresholds as th
from app.main import app
from app.models.account import Account
from app.models.alert import Alert
from app.models.case_subject import CaseSubject


def _client(db_session) -> TestClient:
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def _create_customer(client, headers) -> str:
    resp = client.post(
        "/api/v1/customers/",
        json={
            "legal_name": "Structuring Integration Subject",
            "entity_type": "individual",
            "onboarded_at": "2023-06-01",
            "risk_rating": "LOW",
            "country": "US",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_account(client, headers, customer_id: str) -> str:
    resp = client.post(
        f"/api/v1/customers/{customer_id}/accounts",
        json={"account_type": "checking", "opened_at": "2023-07-01", "expected_monthly_volume": "3000.00"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_structuring_transactions(client, headers, account_id: str) -> None:
    """STRUCTURING (rules.py: check_structuring, thresholds.py) fires on
    >= STRUCTURING_MIN_COUNT cash credits with amount in
    [REPORTING_THRESHOLD * STRUCTURING_LOWER_FRACTION, REPORTING_THRESHOLD)
    landing inside a rolling STRUCTURING_WINDOW_DAYS window. Reading the
    real numbers rather than guessing them, per the task brief."""
    # Same conversion rules.py's check_structuring itself uses (float ->
    # Decimal via str, never a direct Decimal*float multiplication).
    lower = th.REPORTING_THRESHOLD * Decimal(str(th.STRUCTURING_LOWER_FRACTION))
    qualifying_amount = (lower + th.REPORTING_THRESHOLD) / 2  # comfortably inside [lower, threshold)
    assert lower <= qualifying_amount < th.REPORTING_THRESHOLD

    now = datetime.now(timezone.utc)
    # One more than the minimum count, all within the window, for margin.
    offsets_days = list(range(th.STRUCTURING_MIN_COUNT + 1))
    assert max(offsets_days) < th.STRUCTURING_WINDOW_DAYS

    for i, offset in enumerate(offsets_days):
        executed_at = (now - timedelta(days=offset + 1)).isoformat()
        resp = client.post(
            f"/api/v1/accounts/{account_id}/transactions",
            json={
                "amount": str(qualifying_amount),
                "direction": "credit",
                "channel": "cash",
                "executed_at": executed_at,
                "is_cash": True,
                "counterparty_ref": f"EXT-STRUCT-{i}",
                "counterparty_country": "US",
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text


def test_hand_entered_account_flows_through_detection_assembly_and_narrative(db_session, make_auth_headers):
    client = _client(db_session)
    try:
        analyst_headers = make_auth_headers("analyst")
        admin_headers = make_auth_headers("admin")

        # 1. Hand-enter a customer, account, and enough transactions to trip
        #    a real rule — all through the new front-door endpoints.
        customer_id = _create_customer(client, analyst_headers)
        account_id = _create_account(client, analyst_headers, customer_id)
        _add_structuring_transactions(client, analyst_headers, account_id)

        # Sanity check the rows actually landed against the real Account
        # model, not just that the API returned 201s.
        account_row = db_session.get(Account, uuid.UUID(account_id))
        assert account_row is not None
        assert account_row.customer_id is not None

        # 2. Trigger the real detection engine (admin-gated).
        detect_resp = client.post("/api/v1/detection/run", headers=admin_headers)
        assert detect_resp.status_code == 200
        detect_summary = detect_resp.json()
        assert detect_summary["accounts_evaluated"] >= 1
        assert detect_summary["alerts_created"] >= 1

        alerts = db_session.query(Alert).filter(Alert.account_id == account_row.id).all()
        assert any(a.rule_code == "STRUCTURING" for a in alerts), [a.rule_code for a in alerts]

        # 3. Assemble cases from those alerts (admin-gated).
        assemble_resp = client.post("/api/v1/cases/assemble", headers=admin_headers)
        assert assemble_resp.status_code == 200
        assert assemble_resp.json()["cases_created"] >= 1

        # 4. A real Case now links back to this hand-entered account via its
        #    customer (CaseSubject) — proving the front door truly connects
        #    to the existing engine, not just that nothing crashed.
        case_subject = db_session.query(CaseSubject).filter(CaseSubject.customer_id == account_row.customer_id).first()
        assert case_subject is not None, "no case was opened for the hand-entered customer"
        case_id = str(case_subject.case_id)

        # ... and it shows up through the ordinary read API too.
        list_resp = client.get("/api/v1/cases/", headers=analyst_headers)
        assert list_resp.status_code == 200
        assert any(c["id"] == case_id for c in list_resp.json())

        # 5. Close the loop completely: generate a real narrative for it
        #    (TEMPLATE mode — deterministic, no Ollama dependency).
        narrative_resp = client.post(
            f"/api/v1/cases/{case_id}/narrative", params={"mode": "TEMPLATE"}, headers=analyst_headers
        )
        assert narrative_resp.status_code == 200
        narrative = narrative_resp.json()
        assert narrative["generation_mode"] == "TEMPLATE"
        assert narrative["body"].strip()
        assert narrative["sentences"]
    finally:
        app.dependency_overrides.clear()


def test_adding_more_transactions_after_a_case_exists_does_not_break_a_rerun(db_session, make_auth_headers):
    """Confirms item 3's edge case: transactions can keep being added to an
    already-flagged account, and re-running detection + assembly afterward
    is safe (reuses the existing OPEN case rather than erroring or
    duplicating it — see assemble_cases()'s docstring).

    Note: global `cases_created`/`cases_reused` counts aren't asserted here
    — the live DB also carries the seeded demo dataset (~500 accounts,
    some with their own injected typologies), so a full detection+assembly
    run legitimately opens/reuses cases for accounts having nothing to do
    with this test. What must hold is scoped to OUR hand-entered account:
    exactly one Case ever gets opened for it, and re-running reuses it."""
    client = _client(db_session)
    try:
        analyst_headers = make_auth_headers("analyst")
        admin_headers = make_auth_headers("admin")

        customer_id = _create_customer(client, analyst_headers)
        account_id = _create_account(client, analyst_headers, customer_id)
        _add_structuring_transactions(client, analyst_headers, account_id)
        customer_uuid = uuid.UUID(customer_id)

        assert client.post("/api/v1/detection/run", headers=admin_headers).status_code == 200
        assert client.post("/api/v1/cases/assemble", headers=admin_headers).status_code == 200

        subjects_after_first = db_session.query(CaseSubject).filter(CaseSubject.customer_id == customer_uuid).all()
        assert len(subjects_after_first) == 1, "expected exactly one case opened for this customer"
        case_id_after_first = subjects_after_first[0].case_id

        # More activity on the same, already-flagged account.
        extra_executed_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        extra_resp = client.post(
            f"/api/v1/accounts/{account_id}/transactions",
            json={"amount": "42.00", "direction": "debit", "channel": "card", "executed_at": extra_executed_at},
            headers=analyst_headers,
        )
        assert extra_resp.status_code == 201

        # Re-running both steps must not error, and must not open a second
        # case for the same account.
        assert client.post("/api/v1/detection/run", headers=admin_headers).status_code == 200
        assert client.post("/api/v1/cases/assemble", headers=admin_headers).status_code == 200

        subjects_after_second = db_session.query(CaseSubject).filter(CaseSubject.customer_id == customer_uuid).all()
        assert len(subjects_after_second) == 1, "a second case was incorrectly opened on rerun"
        assert subjects_after_second[0].case_id == case_id_after_first
    finally:
        app.dependency_overrides.clear()


def test_detection_run_returns_a_real_summary_not_a_stub(db_session, make_auth_headers):
    client = _client(db_session)
    try:
        resp = client.post("/api/v1/detection/run", headers=make_auth_headers("admin"))
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) >= {"accounts_evaluated", "alerts_created", "band_counts"}
        assert isinstance(body["accounts_evaluated"], int)
    finally:
        app.dependency_overrides.clear()


def test_non_admin_is_rejected_from_assembling_cases(db_session, make_auth_headers):
    client = _client(db_session)
    try:
        resp = client.post("/api/v1/cases/assemble", headers=make_auth_headers("analyst"))
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_admin_can_assemble_cases(db_session, make_auth_headers):
    client = _client(db_session)
    try:
        resp = client.post("/api/v1/cases/assemble", headers=make_auth_headers("admin"))
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) >= {"accounts_considered", "cases_created", "cases_reused", "alerts_linked"}
    finally:
        app.dependency_overrides.clear()
