"""API tests for real authentication (Part 8a, blueprint §11.3): login,
JWT validation, and role enforcement — genuinely exercised end to end
through the API (real users, real bcrypt hashes, real JWTs), not just unit
tests against the dependency functions in isolation."""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.config import settings
from app.deps import get_db
from app.domain.evidence.case_assembly import assemble_cases
from app.main import app
from tests.factories import make_account, make_alert, make_customer

VALID_PASSWORD = "test-password-123"


def _client(db_session) -> TestClient:
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def _seed_case(db_session) -> str:
    customer = make_customer(legal_name="Auth Test Subject", customer_ref="CUS-AUTH01")
    account = make_account(customer=customer, account_ref="ACC-AUTH01")
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


# --- login ---


def test_login_succeeds_with_correct_password(db_session, make_user):
    user = make_user(role="analyst", email="login-ok@test.local")
    client = _client(db_session)
    try:
        resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": VALID_PASSWORD})
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["expires_in"] > 0
    finally:
        app.dependency_overrides.clear()


def test_login_fails_with_wrong_password(db_session, make_user):
    user = make_user(role="analyst", email="login-wrong@test.local")
    client = _client(db_session)
    try:
        resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": "not-the-password"})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_login_fails_for_unknown_email(db_session):
    client = _client(db_session)
    try:
        resp = client.post("/api/v1/auth/login", json={"email": "nobody@test.local", "password": "whatever"})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_login_fails_for_inactive_user(db_session, make_user):
    user = make_user(role="analyst", email="login-inactive@test.local", is_active=False)
    client = _client(db_session)
    try:
        resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": VALID_PASSWORD})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


# --- JWT validation ---


def test_protected_endpoint_rejects_missing_token(db_session):
    client = _client(db_session)
    try:
        resp = client.get("/api/v1/cases/")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_protected_endpoint_rejects_malformed_token(db_session):
    client = _client(db_session)
    try:
        resp = client.get("/api/v1/cases/", headers={"Authorization": "Bearer not-a-real-token"})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_protected_endpoint_rejects_expired_token(db_session, make_user):
    user = make_user(role="analyst", email="expired@test.local")
    expired_payload = {
        "sub": str(user.id),
        "role": user.role,
        "type": "access",
        "iat": datetime.now(timezone.utc) - timedelta(minutes=60),
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    expired_token = jwt.encode(expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    client = _client(db_session)
    try:
        resp = client.get("/api/v1/cases/", headers={"Authorization": f"Bearer {expired_token}"})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_valid_token_grants_access_to_protected_endpoint(db_session, make_auth_headers):
    client = _client(db_session)
    try:
        resp = client.get("/api/v1/cases/", headers=make_auth_headers("analyst"))
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()


# --- role enforcement (genuine 403s, not just a dependency-exists check) ---


def test_admin_is_rejected_from_editing_a_narrative(db_session, make_auth_headers):
    case_id = _seed_case(db_session)
    client = _client(db_session)
    try:
        gen = client.post(
            f"/api/v1/cases/{case_id}/narrative", params={"mode": "TEMPLATE"}, headers=make_auth_headers("analyst")
        )
        narrative = gen.json()
        resp = client.patch(
            f"/api/v1/narratives/{narrative['id']}",
            json={
                "sentences": [
                    {"text": s["text"], "section": s["section"], "evidence_keys": s["evidence_keys"]}
                    for s in narrative["sentences"]
                ]
            },
            headers=make_auth_headers("admin"),
        )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_non_admin_is_rejected_from_running_detection(db_session, make_auth_headers):
    client = _client(db_session)
    try:
        resp = client.post("/api/v1/detection/run", headers=make_auth_headers("analyst"))
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_admin_can_run_detection(db_session, make_auth_headers):
    client = _client(db_session)
    try:
        resp = client.post("/api/v1/detection/run", headers=make_auth_headers("admin"))
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_analyst_is_rejected_from_viewing_audit_trail(db_session, make_auth_headers):
    case_id = _seed_case(db_session)
    client = _client(db_session)
    try:
        resp = client.get(f"/api/v1/audit/case/{case_id}", headers=make_auth_headers("analyst"))
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_reviewer_is_rejected_from_verifying_chain_integrity(db_session, make_auth_headers):
    case_id = _seed_case(db_session)
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/v1/audit/verify-chain", json={"case_id": case_id}, headers=make_auth_headers("reviewer")
        )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_officer_can_verify_chain_integrity(db_session, make_auth_headers):
    case_id = _seed_case(db_session)
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/v1/audit/verify-chain", json={"case_id": case_id}, headers=make_auth_headers("officer")
        )
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()


# --- refresh ---


def test_refresh_issues_a_new_working_access_token(db_session, make_user):
    user = make_user(role="analyst", email="refresh-ok@test.local")
    client = _client(db_session)
    try:
        login_resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": VALID_PASSWORD})
        refresh_token = login_resp.json()["refresh_token"]

        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        new_access = resp.json()["access_token"]

        gate_resp = client.get("/api/v1/cases/", headers={"Authorization": f"Bearer {new_access}"})
        assert gate_resp.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_refresh_rejects_an_access_token(db_session, make_auth_headers):
    headers = make_auth_headers("analyst")
    access_token = headers["Authorization"].split(" ")[1]
    client = _client(db_session)
    try:
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()
