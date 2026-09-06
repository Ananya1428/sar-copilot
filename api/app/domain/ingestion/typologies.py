"""Deliberate AML typology injectors (blueprint §6 in-scope generator +
§12.2 typology list). Each injector fabricates transactions matching one
laundering pattern and returns a ground-truth record describing exactly
what it planted, so later parts can measure detection precision/recall
against a known answer.

Injection rate and distribution: `plan_injections` touches roughly
`INJECTION_RATE` of accounts (default 12%), split as evenly as possible
across the six typologies, so the large majority of generated accounts
carry only ordinary background activity (see background.py) — matching
the spec's "most accounts should have NO injected typology."
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from app.domain.ingestion.refs import RefRegistry
from app.domain.ingestion.util import business_hour, make_txn, q2, random_dt_between
from app.models.account import Account
from app.models.transaction import Transaction

TYPOLOGIES = [
    "STRUCTURING",
    "SMURFING",
    "RAPID_MOVEMENT",
    "CIRCULAR_FLOW",
    "HIGH_VELOCITY",
    "DORMANT_REACTIVATION",
]

INJECTION_RATE = 0.12
CIRCULAR_FLOW_GROUP_SIZE = 3


@dataclass
class InjectionPlanItem:
    typology: str
    accounts: list[Account]


@dataclass
class Injection:
    typology: str
    transactions: list[Transaction]
    ground_truth: dict = field(default_factory=dict)


def plan_injections(accounts: list[Account], rng: random.Random) -> list[InjectionPlanItem]:
    """Decide which accounts get which typology, without generating any
    transactions yet. Deterministic given `rng`."""

    n = len(accounts)
    target_total = max(len(TYPOLOGIES), round(n * INJECTION_RATE))

    pool = accounts.copy()
    rng.shuffle(pool)

    per_type = target_total // len(TYPOLOGIES)
    remainder = target_total % len(TYPOLOGIES)

    plan: list[InjectionPlanItem] = []
    idx = 0
    for i, typ in enumerate(TYPOLOGIES):
        count = per_type + (1 if i < remainder else 0)
        if typ == "CIRCULAR_FLOW":
            for _ in range(max(1, count)):
                if idx + CIRCULAR_FLOW_GROUP_SIZE > len(pool):
                    break
                group = pool[idx : idx + CIRCULAR_FLOW_GROUP_SIZE]
                idx += CIRCULAR_FLOW_GROUP_SIZE
                plan.append(InjectionPlanItem(typ, group))
        else:
            for _ in range(count):
                if idx >= len(pool):
                    break
                plan.append(InjectionPlanItem(typ, [pool[idx]]))
                idx += 1

    return plan


def _window(period_start: datetime, period_end: datetime, rng: random.Random, span_days: int) -> datetime:
    """A start point leaving `span_days` of room before period_end."""
    latest_start = period_end - timedelta(days=span_days)
    if latest_start <= period_start:
        return period_start
    return random_dt_between(rng, period_start, latest_start)


def inject_structuring(account: Account, period_start: datetime, period_end: datetime, rng: random.Random, faker, country: str, registry: RefRegistry) -> Injection:
    window_days = 7
    start = _window(period_start, period_end, rng, window_days)
    n = rng.randint(4, 7)

    txns = []
    for _ in range(n):
        amt = q2(rng.uniform(8200, 9900))
        ts = business_hour(rng, start + timedelta(days=rng.uniform(0, window_days)))
        txns.append(make_txn(rng, registry, account, ts, amt, "credit", "cash", is_cash=True, counterparty_country=country, narrative_text="cash deposit"))

    gt = {
        "typology": "STRUCTURING",
        "account_ref": account.account_ref,
        "customer_id": str(account.customer_id),
        "transaction_refs": [t.txn_ref for t in txns],
        "window": {"start": start.isoformat(), "end": (start + timedelta(days=window_days)).isoformat()},
        "total": str(sum((t.amount for t in txns), Decimal("0"))),
    }
    return Injection("STRUCTURING", txns, gt)


def inject_smurfing(account: Account, period_start: datetime, period_end: datetime, rng: random.Random, faker, country: str, registry: RefRegistry) -> Injection:
    window_days = 14
    start = _window(period_start, period_end, rng, window_days)
    n = rng.randint(5, 9)

    txns = []
    originators = []
    for _ in range(n):
        amt = q2(rng.uniform(1500, 9200))
        ts = random_dt_between(rng, start, start + timedelta(days=window_days))
        originator = faker.name()
        originators.append(originator)
        txns.append(
            make_txn(
                rng, registry, account, ts, amt, "credit", rng.choice(["wire", "cash"]),
                is_cash=False, counterparty_ref=originator, counterparty_country=country,
                narrative_text="third-party deposit",
            )
        )

    gt = {
        "typology": "SMURFING",
        "account_ref": account.account_ref,
        "customer_id": str(account.customer_id),
        "transaction_refs": [t.txn_ref for t in txns],
        "distinct_originators": len(set(originators)),
        "window": {"start": start.isoformat(), "end": (start + timedelta(days=window_days)).isoformat()},
    }
    return Injection("SMURFING", txns, gt)


def inject_rapid_movement(account: Account, period_start: datetime, period_end: datetime, rng: random.Random, faker, country: str, registry: RefRegistry) -> Injection:
    start = _window(period_start, period_end, rng, 2)
    credit_amount = q2(rng.uniform(20000, 60000))
    credit_ts = business_hour(rng, start)
    credit = make_txn(
        rng, registry, account, credit_ts, credit_amount, "credit", "wire",
        is_cash=False, counterparty_ref=faker.company(), counterparty_country=country,
        narrative_text="incoming wire",
    )

    move_fraction = Decimal(str(rng.uniform(0.70, 0.95)))
    remaining = q2(credit_amount * move_fraction)
    n_debits = rng.randint(1, 3)
    debits = []
    per = q2(remaining / n_debits)
    for i in range(n_debits):
        amt = per if i < n_debits - 1 else q2(remaining - per * (n_debits - 1))
        ts = credit_ts + timedelta(hours=rng.uniform(1, 47))
        debits.append(
            make_txn(
                rng, registry, account, ts, amt, "debit", "wire",
                is_cash=False, counterparty_ref=faker.company(), counterparty_country=country,
                narrative_text="outgoing wire",
            )
        )

    txns = [credit, *debits]
    moved_pct = float(remaining / credit_amount) * 100
    gt = {
        "typology": "RAPID_MOVEMENT",
        "account_ref": account.account_ref,
        "customer_id": str(account.customer_id),
        "transaction_refs": [t.txn_ref for t in txns],
        "credit_amount": str(credit_amount),
        "moved_within_48h_pct": round(moved_pct, 1),
        "window": {"start": credit_ts.isoformat(), "end": (credit_ts + timedelta(hours=48)).isoformat()},
    }
    return Injection("RAPID_MOVEMENT", txns, gt)


def inject_high_velocity(account: Account, period_start: datetime, period_end: datetime, rng: random.Random, faker, country: str, registry: RefRegistry) -> Injection:
    start = _window(period_start, period_end, rng, 1)
    n = rng.randint(15, 30)
    monthly = float(account.expected_monthly_volume)

    txns = []
    for _ in range(n):
        amt = q2(monthly * rng.uniform(0.01, 0.06))
        ts = random_dt_between(rng, start, start + timedelta(hours=24))
        direction = rng.choice(["credit", "debit"])
        txns.append(
            make_txn(
                rng, registry, account, ts, amt, direction, rng.choice(["card", "ach"]),
                is_cash=False, counterparty_ref=faker.company(), counterparty_country=country,
                narrative_text="rapid transaction burst",
            )
        )

    gt = {
        "typology": "HIGH_VELOCITY",
        "account_ref": account.account_ref,
        "customer_id": str(account.customer_id),
        "transaction_refs": [t.txn_ref for t in txns],
        "txn_count_24h": n,
        "window": {"start": start.isoformat(), "end": (start + timedelta(hours=24)).isoformat()},
    }
    return Injection("HIGH_VELOCITY", txns, gt)


def inject_dormant_reactivation(account: Account, period_start: datetime, period_end: datetime, rng: random.Random, faker, country: str, registry: RefRegistry) -> Injection:
    """Caller is responsible for NOT generating ordinary background activity
    across the whole period for this account — see synthetic.py, which only
    gives dormant-reactivation accounts background activity in the first
    slice of the period, leaving the gap this typology depends on."""

    burst_days = rng.randint(3, 7)
    start = period_end - timedelta(days=burst_days)
    n = rng.randint(5, 10)
    monthly = float(account.expected_monthly_volume)

    txns = []
    for _ in range(n):
        amt = q2(monthly * rng.uniform(3, 8))
        ts = random_dt_between(rng, start, period_end)
        direction = rng.choice(["credit", "debit"])
        txns.append(
            make_txn(
                rng, registry, account, ts, amt, direction, rng.choice(["wire", "ach"]),
                is_cash=False, counterparty_ref=faker.company(), counterparty_country=country,
                narrative_text="reactivation transfer",
            )
        )

    gt = {
        "typology": "DORMANT_REACTIVATION",
        "account_ref": account.account_ref,
        "customer_id": str(account.customer_id),
        "transaction_refs": [t.txn_ref for t in txns],
        "dormant_days_before_burst": (period_end - period_start).days - burst_days,
        "window": {"start": start.isoformat(), "end": period_end.isoformat()},
    }
    return Injection("DORMANT_REACTIVATION", txns, gt)


def inject_circular_flow(accounts: list[Account], period_start: datetime, period_end: datetime, rng: random.Random, registry: RefRegistry) -> Injection:
    """Round-tripping across a cycle of accounts (blueprint §12.4
    find_circular_flows: retention = min(hop value) / max(hop value)).
    Each hop produces two rows — a debit on the source account and a
    credit on the destination — linked via counterparty_account_ref."""

    start = _window(period_start, period_end, rng, len(accounts) * 2)
    amount = Decimal(str(rng.uniform(30000, 70000)))

    txns: list[Transaction] = []
    hop_values = []
    ts = business_hour(rng, start)
    current = amount

    n = len(accounts)
    for i in range(n):
        src = accounts[i]
        dst = accounts[(i + 1) % n]
        hop_amount = q2(current)
        hop_values.append(hop_amount)

        debit = make_txn(
            rng, registry, src, ts, hop_amount, "debit", "wire", is_cash=False,
            counterparty_ref=dst.account_ref, counterparty_country=None,
            counterparty_account_ref=dst.account_ref, narrative_text="internal transfer out",
        )
        ts = ts + timedelta(hours=rng.uniform(6, 36))
        credit = make_txn(
            rng, registry, dst, ts, hop_amount, "credit", "wire", is_cash=False,
            counterparty_ref=src.account_ref, counterparty_country=None,
            counterparty_account_ref=src.account_ref, narrative_text="internal transfer in",
        )
        txns.extend([debit, credit])

        current = current * Decimal(str(rng.uniform(0.85, 0.95)))

    retention = float(min(hop_values) / max(hop_values))
    gt = {
        "typology": "CIRCULAR_FLOW",
        "account_refs": [a.account_ref for a in accounts],
        "customer_ids": [str(a.customer_id) for a in accounts],
        "transaction_refs": [t.txn_ref for t in txns],
        "retention": round(retention, 3),
        "hops": n,
        "window": {"start": start.isoformat(), "end": ts.isoformat()},
    }
    return Injection("CIRCULAR_FLOW", txns, gt)
