"""Account-level behavioural feature engineering (blueprint §12.1).

Per the Part 2 brief: computed over the account's FULL transaction history
in the generated period, not a rolling 30-day window — the "_30d" suffix on
some feature names is inherited from the blueprint's rolling-window design
and kept for name-parity with §12.1's `FEATURES` list, but nothing here
actually windows to 30 days. A later part can reintroduce a real rolling
window once detection runs on an ongoing (not batch) basis.

`volume_vs_expected_ratio` is the single most compliance-native feature
here — it's the only one that checks the account's actual behaviour against
what its own KYC profile (`expected_monthly_volume`) said it would do,
rather than against other accounts' behaviour. See blueprint §12.1's design
note.
"""

import json
import statistics
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.domain.detection.thresholds import (
    RAPID_MOVEMENT_WINDOW_HOURS,
    REPORTING_THRESHOLD,
    STRUCTURING_LOWER_FRACTION,
)
from app.models.account import Account
from app.models.transaction import Transaction

FEATURES: list[str] = [
    "txn_count_30d",
    "total_credit_30d",
    "total_debit_30d",
    "net_flow_30d",
    "mean_amount",
    "std_amount",
    "max_amount",
    "cash_ratio",
    "round_amount_ratio",
    "sub_threshold_ratio",
    "distinct_counterparties",
    "counterparty_concentration",
    "distinct_countries",
    "high_risk_country_ratio",
    "night_txn_ratio",
    "weekend_txn_ratio",
    "velocity_max_24h",
    "inter_txn_time_mean",
    "inter_txn_time_std",
    "volume_vs_expected_ratio",
    "pass_through_ratio",
    "balance_volatility",
]

_HIGH_RISK_COUNTRIES_PATH = Path("data/reference/high_risk_countries.json")


def load_high_risk_countries(include_elevated: bool = True) -> frozenset[str]:
    """Reads Part 1's data/reference/high_risk_countries.json. Returns an
    empty set (rather than raising) if the file isn't present, so feature
    computation degrades gracefully instead of crashing a detection run."""
    if not _HIGH_RISK_COUNTRIES_PATH.exists():
        return frozenset()
    data = json.loads(_HIGH_RISK_COUNTRIES_PATH.read_text())
    countries = set(data.get("high_risk", []))
    if include_elevated:
        countries |= set(data.get("elevated_risk", []))
    return frozenset(countries)


def _reporting_threshold_band(amount: Decimal, lower_fraction: float, threshold: Decimal) -> bool:
    lower = threshold * Decimal(str(lower_fraction))
    return lower <= amount < threshold


def _max_24h_velocity(sorted_times: list[datetime]) -> int:
    """Largest number of transactions falling inside any 24h span, via a
    sliding window over sorted timestamps."""
    if not sorted_times:
        return 0
    best = 1
    left = 0
    for right, t_right in enumerate(sorted_times):
        while (t_right - sorted_times[left]).total_seconds() > 24 * 3600:
            left += 1
        best = max(best, right - left + 1)
    return best


def _pass_through_fraction(transactions: list[Transaction]) -> float:
    """Value-weighted fraction of each credit's amount that leaves again
    (via any debit) within RAPID_MOVEMENT_WINDOW_HOURS. Mirrors the
    RAPID_MOVEMENT rule's logic (rules.py) but as a continuous feature
    rather than a threshold decision."""
    credits = [t for t in transactions if t.direction == "credit"]
    debits = sorted((t for t in transactions if t.direction == "debit"), key=lambda t: t.executed_at)
    if not credits:
        return 0.0

    total_credit = sum((t.amount for t in credits), Decimal("0"))
    if total_credit == 0:
        return 0.0

    window = RAPID_MOVEMENT_WINDOW_HOURS * 3600
    moved = Decimal("0")
    for c in credits:
        matched = Decimal("0")
        for d in debits:
            delta = (d.executed_at - c.executed_at).total_seconds()
            if 0 <= delta <= window:
                matched += d.amount
        moved += min(matched, c.amount)

    return float(min(Decimal("1"), moved / total_credit))


def _balance_series(transactions: list[Transaction]) -> list[float]:
    """Cumulative net flow from a zero baseline, in chronological order —
    Part 1's schema has no real running-balance column, so this is a
    documented proxy for one."""
    balance = Decimal("0")
    series = []
    for t in sorted(transactions, key=lambda t: t.executed_at):
        balance += t.amount if t.direction == "credit" else -t.amount
        series.append(float(balance))
    return series


def compute_features(account: Account, transactions: list[Transaction], high_risk_countries: frozenset[str]) -> dict[str, float]:
    """Returns exactly the `FEATURES` keys, computed from `transactions`
    (assumed to all belong to `account`)."""

    n = len(transactions)
    if n == 0:
        return {name: 0.0 for name in FEATURES}

    amounts = [t.amount for t in transactions]
    amounts_f = [float(a) for a in amounts]
    credits = [t for t in transactions if t.direction == "credit"]
    debits = [t for t in transactions if t.direction == "debit"]
    total_credit = sum((t.amount for t in credits), Decimal("0"))
    total_debit = sum((t.amount for t in debits), Decimal("0"))

    times_sorted = sorted(t.executed_at for t in transactions)
    gaps_hours = [
        (times_sorted[i] - times_sorted[i - 1]).total_seconds() / 3600.0
        for i in range(1, len(times_sorted))
    ]

    counterparties = [t.counterparty_ref for t in transactions if t.counterparty_ref]
    distinct_counterparties = len(set(counterparties))
    if counterparties:
        counts = {}
        for c in counterparties:
            counts[c] = counts.get(c, 0) + 1
        total_cp = len(counterparties)
        hhi = sum((c / total_cp) ** 2 for c in counts.values())
    else:
        hhi = 0.0

    countries = [t.counterparty_country for t in transactions if t.counterparty_country]
    distinct_countries = len(set(countries))
    high_risk_hits = sum(1 for c in countries if c in high_risk_countries)

    round_amount_count = sum(1 for a in amounts if a % Decimal("1000") == 0)
    sub_threshold_count = sum(
        1 for a in amounts if _reporting_threshold_band(a, STRUCTURING_LOWER_FRACTION, REPORTING_THRESHOLD)
    )

    # "Local" time isn't modeled anywhere in Part 1's schema (no branch/
    # customer timezone), so UTC is used as the proxy for both of these.
    night_count = sum(1 for t in transactions if t.executed_at.astimezone(UTC).hour < 5)
    weekend_count = sum(1 for t in transactions if t.executed_at.astimezone(UTC).weekday() >= 5)

    # volume_vs_expected_ratio: observed monthly average vs. the account's
    # own declared expectation. "Months observed" is derived from the
    # transaction span itself, so accounts with sparse activity don't get
    # an artificially inflated or deflated ratio from an external window.
    span_days = (times_sorted[-1] - times_sorted[0]).days if len(times_sorted) > 1 else 0
    months_observed = max(1.0, span_days / 30.0)
    observed_total = float(total_credit + total_debit)
    expected_total = float(account.expected_monthly_volume) * months_observed
    volume_vs_expected_ratio = observed_total / expected_total if expected_total > 0 else 0.0

    return {
        "txn_count_30d": float(n),
        "total_credit_30d": float(total_credit),
        "total_debit_30d": float(total_debit),
        "net_flow_30d": float(total_credit - total_debit),
        "mean_amount": statistics.fmean(amounts_f),
        "std_amount": statistics.pstdev(amounts_f) if n > 1 else 0.0,
        "max_amount": max(amounts_f),
        "cash_ratio": sum(1 for t in transactions if t.is_cash) / n,
        "round_amount_ratio": round_amount_count / n,
        "sub_threshold_ratio": sub_threshold_count / n,
        "distinct_counterparties": float(distinct_counterparties),
        "counterparty_concentration": hhi,
        "distinct_countries": float(distinct_countries),
        "high_risk_country_ratio": high_risk_hits / n,
        "night_txn_ratio": night_count / n,
        "weekend_txn_ratio": weekend_count / n,
        "velocity_max_24h": float(_max_24h_velocity(times_sorted)),
        "inter_txn_time_mean": statistics.fmean(gaps_hours) if gaps_hours else 0.0,
        "inter_txn_time_std": statistics.pstdev(gaps_hours) if len(gaps_hours) > 1 else 0.0,
        "volume_vs_expected_ratio": volume_vs_expected_ratio,
        "pass_through_ratio": _pass_through_fraction(transactions),
        "balance_volatility": statistics.pstdev(_balance_series(transactions)) if n > 1 else 0.0,
    }


def features_to_vector(features: dict[str, float]) -> list[float]:
    """Orders a feature dict into the canonical vector for the ML ensemble."""
    return [features[name] for name in FEATURES]
