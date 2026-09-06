"""Synthetic AML case data generator (blueprint §6 in-scope / §20
`data/generator`). Produces customers, accounts, and transactions with a
known set of deliberately injected laundering typologies plus realistic
non-suspicious background activity, and returns/records a ground-truth
manifest so later parts can measure detection precision and recall.

Determinism: everything is driven by a single `random.Random(seed)` plus
`Faker` seeded the same way, so the same (n_accounts, days, seed) always
produces the same dataset.
"""

import json
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from faker import Faker
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.ingestion.background import generate_background_activity
from app.domain.ingestion.refs import RefRegistry
from app.domain.ingestion.typologies import (
    inject_circular_flow,
    inject_dormant_reactivation,
    inject_high_velocity,
    inject_rapid_movement,
    inject_smurfing,
    inject_structuring,
    plan_injections,
)
from app.domain.ingestion.util import q2
from app.models.account import Account
from app.models.customer import Customer
from app.models.transaction import Transaction

BUILDER_VERSION = "0.1.0"

# Mostly domestic, with a light sprinkling of other jurisdictions so later
# geography-based detection rules (§12.2 CROSS_BORDER_RISK) have something
# to find — deliberately NOT correlated with which accounts get an injected
# typology, so geography alone never doubles as a leak of the ground truth.
COUNTRY_POOL = ["US"] * 14 + ["IN", "GB", "CA", "MX", "DE", "PH", "NG", "AF"]

SINGLE_ACCOUNT_INJECTORS = {
    "STRUCTURING": inject_structuring,
    "SMURFING": inject_smurfing,
    "RAPID_MOVEMENT": inject_rapid_movement,
    "HIGH_VELOCITY": inject_high_velocity,
    "DORMANT_REACTIVATION": inject_dormant_reactivation,
}


def _make_customer_and_account(rng: random.Random, faker: Faker, registry: RefRegistry, period_start: datetime) -> tuple[Customer, Account]:
    is_business = rng.random() < 0.3
    country = rng.choice(COUNTRY_POOL)
    onboarded_at = (period_start - timedelta(days=rng.randint(30, 365 * 6))).date()

    customer = Customer(
        customer_ref=registry.new_customer_ref(rng),
        legal_name=faker.company() if is_business else faker.name(),
        entity_type="business" if is_business else "individual",
        onboarded_at=onboarded_at,
        risk_rating=rng.choices(["LOW", "MEDIUM", "HIGH"], weights=[0.75, 0.20, 0.05])[0],
        occupation=None if is_business else faker.job(),
        country=country,
    )

    expected_volume = q2(rng.uniform(10000, 80000) if is_business else rng.uniform(2000, 9000))
    account = Account(
        account_ref=registry.new_account_ref(rng),
        account_type="business" if is_business else rng.choice(["checking", "savings"]),
        currency="USD",
        opened_at=max(onboarded_at, (period_start - timedelta(days=rng.randint(0, 200))).date()),
        expected_monthly_volume=expected_volume,
        status="active",
    )
    account.customer = customer
    return customer, account


def generate_dataset(
    session: Session,
    n_accounts: int = 500,
    days: int = 180,
    seed: int = 42,
    ground_truth_path: Path | None = None,
) -> dict:
    rng = random.Random(seed)
    Faker.seed(seed)
    faker = Faker()

    period_end = datetime.now(timezone.utc).replace(microsecond=0)
    period_start = period_end - timedelta(days=days)

    # Preload with whatever refs already exist so this function stays safely
    # re-runnable against a non-empty database, even with a repeated seed
    # (see RefRegistry docstring in refs.py for why this matters).
    registry = RefRegistry()
    registry.customer_refs.update(session.scalars(select(Customer.customer_ref)))
    registry.account_refs.update(session.scalars(select(Account.account_ref)))
    registry.txn_refs.update(session.scalars(select(Transaction.txn_ref)))

    accounts: list[Account] = []
    for _ in range(n_accounts):
        customer, account = _make_customer_and_account(rng, faker, registry, period_start)
        session.add(customer)
        session.add(account)
        accounts.append(account)

    # Assign ids before wiring up transactions / cycles across accounts.
    session.flush()

    plan = plan_injections(accounts, rng)

    ground_truth_entries: list[dict] = []
    dormant_account_ids: set = set()
    typology_by_account: dict = {}
    total_txns = 0

    for item in plan:
        country = item.accounts[0].customer.country
        if item.typology == "CIRCULAR_FLOW":
            injection = inject_circular_flow(item.accounts, period_start, period_end, rng, registry)
            for a in item.accounts:
                typology_by_account.setdefault(a.id, []).append("CIRCULAR_FLOW")
        else:
            account = item.accounts[0]
            injector = SINGLE_ACCOUNT_INJECTORS[item.typology]
            injection = injector(account, period_start, period_end, rng, faker, country, registry)
            typology_by_account.setdefault(account.id, []).append(item.typology)
            if item.typology == "DORMANT_REACTIVATION":
                dormant_account_ids.add(account.id)

        session.add_all(injection.transactions)
        total_txns += len(injection.transactions)
        ground_truth_entries.append(injection.ground_truth)

    # Background activity for every account — full period for ordinary and
    # multi-typology accounts, truncated for dormant-reactivation accounts
    # so the gap the typology depends on actually exists.
    for account in accounts:
        country = account.customer.country
        if account.id in dormant_account_ids:
            early_end = period_start + timedelta(days=max(1, int(days * 0.2)))
            bg = generate_background_activity(account, period_start, early_end, rng, faker, country, registry)
        else:
            bg = generate_background_activity(account, period_start, period_end, rng, faker, country, registry)
        session.add_all(bg)
        total_txns += len(bg)

    session.flush()

    typology_counts = Counter(g["typology"] for g in ground_truth_entries)
    touched_accounts = len(typology_by_account)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "builder_version": BUILDER_VERSION,
        "config": {"accounts": n_accounts, "days": days, "seed": seed},
        "injection_rate_target": 0.12,
        "accounts_touched": touched_accounts,
        "accounts_clean": n_accounts - touched_accounts,
        "typology_counts": dict(typology_counts),
        "injections": ground_truth_entries,
    }

    if ground_truth_path is not None:
        ground_truth_path.parent.mkdir(parents=True, exist_ok=True)
        ground_truth_path.write_text(json.dumps(manifest, indent=2, default=str))

    summary = {
        "customers": n_accounts,
        "accounts": n_accounts,
        "transactions": total_txns,
        "accounts_touched_by_typology": touched_accounts,
        "accounts_clean": n_accounts - touched_accounts,
        "typology_counts": dict(typology_counts),
        "ground_truth_path": str(ground_truth_path) if ground_truth_path else None,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
    }
    return summary
