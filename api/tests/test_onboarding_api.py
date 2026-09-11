"""API tests for the Part 8b hand-entry "front door" (POST /customers,
POST /customers/{id}/accounts, POST /accounts/{id}/transactions):
success paths, validation failures (real 422s via Pydantic, not silent
acceptance), 404s for a non-existent parent, and unauthenticated
rejection. These endpoints accept any authenticated role (see
onboarding.py's module docstring for why), so there is no 403
role-rejection case to test here — that lives in
test_onboarding_integration.py against POST /cases/assemble instead."""

from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.deps import get_db
from app.main import app


def _client(db_session) -> TestClient:
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


# --- customers ---


def test_create_customer_succeeds(db_session, make_auth_headers):
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/v1/customers/",
            json={
                "legal_name": "Jordan Rivera",
                "entity_type": "individual",
                "onboarded_at": "2024-01-15",
                "risk_rating": "MEDIUM",
                "occupation": "Consultant",
                "country": "us",
            },
            headers=make_auth_headers("analyst"),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["legal_name"] == "Jordan Rivera"
        assert body["entity_type"] == "individual"
        assert body["risk_rating"] == "MEDIUM"
        assert body["country"] == "US"  # normalised to uppercase
        assert body["customer_ref"].startswith("CUS-")
    finally:
        app.dependency_overrides.clear()


def test_create_customer_rejects_missing_token(db_session):
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/v1/customers/",
            json={
                "legal_name": "Jordan Rivera",
                "entity_type": "individual",
                "onboarded_at": "2024-01-15",
                "country": "US",
            },
        )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_create_customer_rejects_empty_legal_name(db_session, make_auth_headers):
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/v1/customers/",
            json={"legal_name": "", "entity_type": "individual", "onboarded_at": "2024-01-15", "country": "US"},
            headers=make_auth_headers("analyst"),
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_create_customer_rejects_invalid_entity_type(db_session, make_auth_headers):
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/v1/customers/",
            json={
                "legal_name": "Jordan Rivera",
                "entity_type": "shell-corp",
                "onboarded_at": "2024-01-15",
                "country": "US",
            },
            headers=make_auth_headers("analyst"),
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_create_customer_rejects_future_onboarded_at(db_session, make_auth_headers):
    client = _client(db_session)
    try:
        future = (date.today() + timedelta(days=30)).isoformat()
        resp = client.post(
            "/api/v1/customers/",
            json={"legal_name": "Jordan Rivera", "entity_type": "individual", "onboarded_at": future, "country": "US"},
            headers=make_auth_headers("analyst"),
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


# --- accounts ---


def _create_customer(client, headers) -> str:
    resp = client.post(
        "/api/v1/customers/",
        json={"legal_name": "Account Test Subject", "entity_type": "individual", "onboarded_at": "2024-01-15", "country": "US"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_account_succeeds(db_session, make_auth_headers):
    client = _client(db_session)
    headers = make_auth_headers("analyst")
    try:
        customer_id = _create_customer(client, headers)
        resp = client.post(
            f"/api/v1/customers/{customer_id}/accounts",
            json={"account_type": "checking", "currency": "usd", "opened_at": "2024-02-01", "expected_monthly_volume": "3000.00"},
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["customer_id"] == customer_id
        assert body["account_ref"].startswith("ACC-")
        assert body["currency"] == "USD"
        assert body["status"] == "active"
    finally:
        app.dependency_overrides.clear()


def test_create_account_404_for_unknown_customer(db_session, make_auth_headers):
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/v1/customers/00000000-0000-0000-0000-000000000000/accounts",
            json={"account_type": "checking", "opened_at": "2024-02-01", "expected_monthly_volume": "3000.00"},
            headers=make_auth_headers("analyst"),
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_create_account_400_for_invalid_customer_id(db_session, make_auth_headers):
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/v1/customers/not-a-uuid/accounts",
            json={"account_type": "checking", "opened_at": "2024-02-01", "expected_monthly_volume": "3000.00"},
            headers=make_auth_headers("analyst"),
        )
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_create_account_rejects_negative_expected_volume(db_session, make_auth_headers):
    client = _client(db_session)
    headers = make_auth_headers("analyst")
    try:
        customer_id = _create_customer(client, headers)
        resp = client.post(
            f"/api/v1/customers/{customer_id}/accounts",
            json={"account_type": "checking", "opened_at": "2024-02-01", "expected_monthly_volume": "-500.00"},
            headers=headers,
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_create_account_rejects_invalid_account_type(db_session, make_auth_headers):
    client = _client(db_session)
    headers = make_auth_headers("analyst")
    try:
        customer_id = _create_customer(client, headers)
        resp = client.post(
            f"/api/v1/customers/{customer_id}/accounts",
            json={"account_type": "offshore", "opened_at": "2024-02-01", "expected_monthly_volume": "3000.00"},
            headers=headers,
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


# --- transactions ---


def _create_account(client, headers) -> str:
    customer_id = _create_customer(client, headers)
    resp = client.post(
        f"/api/v1/customers/{customer_id}/accounts",
        json={"account_type": "checking", "opened_at": "2024-02-01", "expected_monthly_volume": "3000.00"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_transaction_succeeds(db_session, make_auth_headers):
    client = _client(db_session)
    headers = make_auth_headers("analyst")
    try:
        account_id = _create_account(client, headers)
        executed_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        resp = client.post(
            f"/api/v1/accounts/{account_id}/transactions",
            json={
                "amount": "1500.00",
                "direction": "credit",
                "channel": "ach",
                "executed_at": executed_at,
                "counterparty_ref": "EXT-000001",
                "counterparty_country": "us",
                "is_cash": False,
            },
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["account_id"] == account_id
        assert body["txn_ref"].startswith("TXN-")
        assert body["counterparty_country"] == "US"
    finally:
        app.dependency_overrides.clear()


def test_create_transaction_404_for_unknown_account(db_session, make_auth_headers):
    client = _client(db_session)
    try:
        executed_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        resp = client.post(
            "/api/v1/accounts/00000000-0000-0000-0000-000000000000/transactions",
            json={"amount": "100.00", "direction": "credit", "channel": "ach", "executed_at": executed_at},
            headers=make_auth_headers("analyst"),
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_create_transaction_rejects_negative_amount(db_session, make_auth_headers):
    client = _client(db_session)
    headers = make_auth_headers("analyst")
    try:
        account_id = _create_account(client, headers)
        executed_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        resp = client.post(
            f"/api/v1/accounts/{account_id}/transactions",
            json={"amount": "-100.00", "direction": "credit", "channel": "ach", "executed_at": executed_at},
            headers=headers,
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_create_transaction_rejects_future_executed_at(db_session, make_auth_headers):
    client = _client(db_session)
    headers = make_auth_headers("analyst")
    try:
        account_id = _create_account(client, headers)
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        resp = client.post(
            f"/api/v1/accounts/{account_id}/transactions",
            json={"amount": "100.00", "direction": "credit", "channel": "ach", "executed_at": future},
            headers=headers,
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_create_transaction_rejects_invalid_direction(db_session, make_auth_headers):
    client = _client(db_session)
    headers = make_auth_headers("analyst")
    try:
        account_id = _create_account(client, headers)
        executed_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        resp = client.post(
            f"/api/v1/accounts/{account_id}/transactions",
            json={"amount": "100.00", "direction": "sideways", "channel": "ach", "executed_at": executed_at},
            headers=headers,
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()
