"""Ordinary, non-suspicious account activity — the noise most accounts in
the dataset should consist entirely of (blueprint §6 in-scope generator:
"generate normal, non-suspicious background activity for realism")."""

import random
from datetime import datetime, timedelta

from app.domain.ingestion.refs import RefRegistry
from app.domain.ingestion.util import business_hour, make_txn, q2, random_dt_between
from app.models.account import Account
from app.models.transaction import Transaction


def generate_background_activity(
    account: Account,
    period_start: datetime,
    period_end: datetime,
    rng: random.Random,
    faker,
    country: str,
    registry: RefRegistry,
) -> list[Transaction]:
    """Recurring income credit + everyday spending debits, scaled off the
    account's own declared expected_monthly_volume so activity looks
    consistent with the account's stated profile."""

    txns: list[Transaction] = []
    monthly = float(account.expected_monthly_volume)
    total_days = (period_end - period_start).days
    months = max(1, total_days // 30)

    for m in range(months):
        month_start = period_start + timedelta(days=30 * m)
        if month_start >= period_end:
            break
        month_end = min(period_end, month_start + timedelta(days=30))

        credit_amount = q2(monthly * rng.uniform(0.85, 1.15))
        ts = business_hour(rng, month_start + timedelta(days=rng.randint(0, 4)))
        txns.append(
            make_txn(
                rng, registry, account, ts, credit_amount, "credit", rng.choice(["ach", "wire"]),
                is_cash=False, counterparty_ref=faker.company(), counterparty_country=country,
                narrative_text="payroll credit",
            )
        )

        for _ in range(rng.randint(3, 8)):
            amt = q2(monthly * rng.uniform(0.01, 0.12))
            ts = random_dt_between(rng, month_start, month_end)
            txns.append(
                make_txn(
                    rng, registry, account, ts, amt, "debit", rng.choice(["card", "ach", "check"]),
                    is_cash=False, counterparty_ref=faker.company(), counterparty_country=country,
                    narrative_text=rng.choice(["utility payment", "retail purchase", "subscription", "rent"]),
                )
            )

        if rng.random() < 0.4:
            amt = q2(monthly * rng.uniform(0.02, 0.08))
            ts = random_dt_between(rng, month_start, month_end)
            direction = rng.choice(["credit", "debit"])
            txns.append(
                make_txn(
                    rng, registry, account, ts, amt, direction, "cash",
                    is_cash=True, counterparty_country=country, narrative_text="cash transaction",
                )
            )

    return txns
