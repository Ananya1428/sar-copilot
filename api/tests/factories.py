"""Plain in-memory ORM object builders for detection-layer unit tests.
These never touch a session/DB — feature engineering, rule, and graph
functions all operate on plain Account/Transaction objects, so tests for
them don't need Part 1's live-Postgres fixtures at all."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.models.account import Account
from app.models.alert import Alert
from app.models.customer import Customer
from app.models.transaction import Transaction


def make_customer(
    legal_name="Test Person",
    entity_type="individual",
    country="US",
    risk_rating="LOW",
    occupation="Engineer",
    onboarded_at=date(2023, 1, 1),
    customer_ref=None,
) -> Customer:
    return Customer(
        id=uuid.uuid4(),
        customer_ref=customer_ref or f"CUS-{uuid.uuid4().hex[:6].upper()}",
        legal_name=legal_name,
        entity_type=entity_type,
        onboarded_at=onboarded_at,
        risk_rating=risk_rating,
        occupation=occupation,
        country=country,
    )


def make_account(expected_monthly_volume="5000.00", account_type="checking", account_ref=None, customer: Customer | None = None) -> Account:
    return Account(
        id=uuid.uuid4(),
        customer_id=customer.id if customer is not None else uuid.uuid4(),
        account_ref=account_ref or f"ACC-{uuid.uuid4().hex[:6].upper()}",
        account_type=account_type,
        currency="USD",
        opened_at=date(2024, 1, 1),
        expected_monthly_volume=Decimal(str(expected_monthly_volume)),
        status="active",
    )


def make_txn(
    account: Account,
    amount,
    direction: str,
    executed_at,
    is_cash: bool = False,
    channel: str = "ach",
    counterparty_ref: str | None = None,
    counterparty_country: str | None = None,
    counterparty_account_ref: str | None = None,
) -> Transaction:
    return Transaction(
        id=uuid.uuid4(),
        account_id=account.id,
        txn_ref=f"TXN-{uuid.uuid4().hex[:10]}",
        executed_at=executed_at,
        amount=Decimal(str(amount)),
        currency="USD",
        direction=direction,
        channel=channel,
        counterparty_ref=counterparty_ref,
        counterparty_country=counterparty_country,
        counterparty_account_ref=counterparty_account_ref,
        is_cash=is_cash,
    )


def make_alert(
    account: Account,
    rule_code: str = "STRUCTURING",
    severity: str = "HIGH",
    score="0.8000",
    raised_at: datetime | None = None,
    rule_evidence: dict | None = None,
    case_id: uuid.UUID | None = None,
) -> Alert:
    return Alert(
        id=uuid.uuid4(),
        account_id=account.id,
        case_id=case_id,
        rule_code=rule_code,
        score=Decimal(str(score)),
        severity=severity,
        raised_at=raised_at or datetime(2024, 3, 1, tzinfo=UTC),
        rule_evidence=rule_evidence or {},
    )
