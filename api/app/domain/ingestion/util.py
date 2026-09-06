import random
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.domain.ingestion.refs import RefRegistry
from app.models.transaction import Transaction


def make_txn(
    rng: random.Random,
    registry: RefRegistry,
    account,
    ts: datetime,
    amount: Decimal,
    direction: str,
    channel: str,
    is_cash: bool,
    counterparty_ref: str | None = None,
    counterparty_country: str | None = None,
    counterparty_account_ref: str | None = None,
    narrative_text: str | None = None,
) -> Transaction:
    return Transaction(
        account_id=account.id,
        txn_ref=registry.new_txn_ref(rng),
        executed_at=ts,
        amount=amount,
        currency=account.currency,
        direction=direction,
        channel=channel,
        counterparty_ref=counterparty_ref,
        counterparty_country=counterparty_country,
        counterparty_account_ref=counterparty_account_ref,
        narrative_text=narrative_text,
        is_cash=is_cash,
    )


def q2(value) -> Decimal:
    """Quantize to 2 decimal places (currency amounts)."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def random_dt_between(rng: random.Random, start: datetime, end: datetime) -> datetime:
    if end <= start:
        return start
    span = (end - start).total_seconds()
    return start + timedelta(seconds=rng.uniform(0, span))


def business_hour(rng: random.Random, day: datetime) -> datetime:
    """Anchor a datetime to a plausible business hour on the given day."""
    return day.replace(hour=rng.randint(8, 18), minute=rng.randint(0, 59), second=rng.randint(0, 59), microsecond=0)
