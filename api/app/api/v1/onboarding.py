"""Manual, hand-entry data-onboarding endpoints (Part 8b) — the "front
door" for real (non-synthetic) Customer/Account/Transaction rows. Right
up to this part, the CLI's `generate-data` (synthetic, batch) was the
only way data entered the system at all.

Scope, deliberately: one row at a time, form-friendly (a customer, then
an account under it, then a transaction under that). Bulk CSV upload is
a reasonable future extension but is NOT this part's job — hand entry is
what the spec asked for.

Two routers live in this one module (`customers_router`, `accounts_router`)
rather than the usual one-router-per-file convention (compare cases.py,
narratives.py, ...), because `POST /customers/{id}/accounts` and
`POST /accounts/{id}/transactions` are the same onboarding concern even
though they mount at different URL prefixes in router.py.

RBAC: blueprint §11.3's matrix has no row for data entry — it didn't
exist when that table was written. Gated the same as the existing
single-entity write actions in cases.py (rebuild evidence, generate
narrative): any authenticated role (`get_current_user`, no
`require_role`). Reasoning: like those actions, this is ordinary,
one-entity-at-a-time casework — the opposite of the system-wide batch
operations §11.3 actually reserves for admin (`POST /detection/run`,
and the new `POST /cases/assemble` in cases.py, gated the same way for
the same reason).
"""

import random
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.domain.ingestion.refs import account_ref as gen_account_ref
from app.domain.ingestion.refs import customer_ref as gen_customer_ref
from app.domain.ingestion.refs import txn_ref as gen_txn_ref
from app.models.account import Account
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.models.user import User

customers_router = APIRouter()
accounts_router = APIRouter()


def _generate_unique_ref(db: Session, generator, column, attempts: int = 20) -> str:
    """Hand entry is one-off, not a seeded batch run, so — unlike
    domain/ingestion/synthetic.py's RefRegistry, which tracks every ref
    issued across a whole generation run so a shared rng seed can't ever
    collide with itself — this just checks the DB directly per insert and
    retries on the (astronomically unlikely) collision. Simpler, and
    correct for a single ad hoc insert where there's no batch-wide
    registry to consult."""
    rng = random.Random()
    for _ in range(attempts):
        candidate = generator(rng)
        if db.scalar(select(column).where(column == candidate)) is None:
            return candidate
    raise RuntimeError(f"could not generate a unique reference after {attempts} attempts")


def _parse_uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid {label}") from None


# --- customers ---


class CustomerCreateRequest(BaseModel):
    legal_name: str = Field(min_length=1)
    entity_type: Literal["individual", "business"]
    onboarded_at: date
    risk_rating: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    occupation: str | None = None
    country: str = Field(min_length=2, max_length=2)

    @field_validator("onboarded_at")
    @classmethod
    def _onboarded_not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("onboarded_at cannot be in the future")
        return v

    @field_validator("country")
    @classmethod
    def _country_upper(cls, v: str) -> str:
        return v.upper()


def _customer_dict(customer: Customer) -> dict:
    return {
        "id": str(customer.id),
        "customer_ref": customer.customer_ref,
        "legal_name": customer.legal_name,
        "entity_type": customer.entity_type,
        "onboarded_at": customer.onboarded_at.isoformat(),
        "risk_rating": customer.risk_rating,
        "occupation": customer.occupation,
        "country": customer.country,
    }


@customers_router.post("/", status_code=201)
def create_customer(body: CustomerCreateRequest, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    """blueprint §10.1 CUSTOMER — real hand-entry front door. `entity_type`
    and `risk_rating` are constrained to exactly the values
    domain/ingestion/synthetic.py already produces ("individual"/"business",
    "LOW"/"MEDIUM"/"HIGH"), not new values invented for this endpoint."""
    customer = Customer(
        customer_ref=_generate_unique_ref(db, gen_customer_ref, Customer.customer_ref),
        legal_name=body.legal_name,
        entity_type=body.entity_type,
        onboarded_at=body.onboarded_at,
        risk_rating=body.risk_rating,
        occupation=body.occupation,
        country=body.country,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return _customer_dict(customer)


# --- accounts ---


class AccountCreateRequest(BaseModel):
    account_type: Literal["checking", "savings", "business"]
    currency: str = Field(default="USD", min_length=3, max_length=3)
    opened_at: date
    expected_monthly_volume: Decimal = Field(gt=0)

    @field_validator("opened_at")
    @classmethod
    def _opened_not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("opened_at cannot be in the future")
        return v

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, v: str) -> str:
        return v.upper()


def _account_dict(account: Account) -> dict:
    return {
        "id": str(account.id),
        "customer_id": str(account.customer_id),
        "account_ref": account.account_ref,
        "account_type": account.account_type,
        "currency": account.currency,
        "opened_at": account.opened_at.isoformat(),
        "expected_monthly_volume": float(account.expected_monthly_volume),
        "status": account.status,
    }


@customers_router.post("/{customer_id}/accounts", status_code=201)
def create_account(
    customer_id: str,
    body: AccountCreateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """blueprint §10.1 ACCOUNT. `status` is deliberately not on the request
    — every new account (synthetic or hand-entered) starts `"active"`;
    going dormant is something that happens to an account over time
    (§12.2 DORMANT_REACTIVATION), never its initial state."""
    customer = db.get(Customer, _parse_uuid(customer_id, "customer id"))
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")

    account = Account(
        customer_id=customer.id,
        account_ref=_generate_unique_ref(db, gen_account_ref, Account.account_ref),
        account_type=body.account_type,
        currency=body.currency,
        opened_at=body.opened_at,
        expected_monthly_volume=body.expected_monthly_volume,
        status="active",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return _account_dict(account)


# --- transactions ---


class TransactionCreateRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    direction: Literal["credit", "debit"]
    channel: Literal["cash", "wire", "ach", "card", "check"]
    executed_at: datetime
    counterparty_ref: str | None = None
    counterparty_country: str | None = Field(default=None, min_length=2, max_length=2)
    is_cash: bool = False

    @field_validator("executed_at")
    @classmethod
    def _executed_not_future(cls, v: datetime) -> datetime:
        now = datetime.now(timezone.utc)
        compare = v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
        if compare > now:
            raise ValueError("executed_at cannot be in the future")
        return v

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("counterparty_country")
    @classmethod
    def _counterparty_country_upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v


def _transaction_dict(txn: Transaction) -> dict:
    return {
        "id": str(txn.id),
        "account_id": str(txn.account_id),
        "txn_ref": txn.txn_ref,
        "executed_at": txn.executed_at.isoformat(),
        "amount": float(txn.amount),
        "currency": txn.currency,
        "direction": txn.direction,
        "channel": txn.channel,
        "counterparty_ref": txn.counterparty_ref,
        "counterparty_country": txn.counterparty_country,
        "is_cash": txn.is_cash,
    }


@accounts_router.post("/{account_id}/transactions", status_code=201)
def create_transaction(
    account_id: str,
    body: TransactionCreateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """blueprint §10.1 TRANSACTION. Adding transactions to an account that
    already has alerts or an open case is expected and safe: nothing in
    detection (orchestrator.py) or case assembly (case_assembly.py) treats
    an account's transaction history as frozen once flagged — a re-run of
    POST /detection/run just recomputes over whatever rows exist now, and
    POST /cases/assemble reuses the account's existing OPEN case rather
    than opening a duplicate (see assemble_cases()'s docstring)."""
    account = db.get(Account, _parse_uuid(account_id, "account id"))
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")

    txn = Transaction(
        account_id=account.id,
        txn_ref=_generate_unique_ref(db, gen_txn_ref, Transaction.txn_ref),
        executed_at=body.executed_at,
        amount=body.amount,
        currency=body.currency,
        direction=body.direction,
        channel=body.channel,
        counterparty_ref=body.counterparty_ref,
        counterparty_country=body.counterparty_country,
        is_cash=body.is_cash,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return _transaction_dict(txn)
