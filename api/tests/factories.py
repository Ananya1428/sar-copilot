"""Plain in-memory ORM object builders for detection-layer unit tests.
These never touch a session/DB — feature engineering, rule, and graph
functions all operate on plain Account/Transaction objects, so tests for
them don't need Part 1's live-Postgres fixtures at all."""

import uuid
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.models.transaction import Transaction


def make_account(expected_monthly_volume="5000.00", account_type="checking", account_ref=None) -> Account:
    return Account(
        id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
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
