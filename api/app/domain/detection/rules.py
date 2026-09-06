"""Deterministic typology rule engine (blueprint §12.2).

Rules are auditable in a way the ML ensemble isn't — this is why
regulators still require them alongside anomaly detection (§12).

Every per-account rule takes the account, its own transactions, and
whatever shared context it needs (a precomputed features dict, the
high-risk country set) and returns a `RuleFinding` if it fires, or `None`.
`check_circular_flow` is the exception: it's inherently cross-account, so
it takes the whole account set and the money-flow graph and returns one
finding per participating account.

All thresholds are imported from thresholds.py — see that module for why
each value is what it is, including the one place (DORMANT_REACTIVATION)
where this build deliberately departs from the blueprint's illustrative
constant.
"""

import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from app.domain.detection import thresholds as th
from app.domain.detection.graph import find_circular_flows
from app.models.account import Account
from app.models.transaction import Transaction


@dataclass
class RuleFinding:
    rule_code: str
    weight: float
    rule_evidence: dict = field(default_factory=dict)


def _best_window(times: list, window: timedelta) -> tuple[int, object]:
    """Among windows starting at each candidate time, the one containing
    the most of the other candidate times. O(n^2), fine at per-account
    transaction volumes (tens to low hundreds)."""
    best_count, best_start = 0, None
    for t in times:
        end = t + window
        count = sum(1 for other in times if t <= other < end)
        if count > best_count:
            best_count, best_start = count, t
    return best_count, best_start


def check_structuring(account: Account, transactions: list[Transaction]) -> RuleFinding | None:
    lower = th.REPORTING_THRESHOLD * Decimal(str(th.STRUCTURING_LOWER_FRACTION))
    candidates = sorted(
        (t for t in transactions if t.is_cash and t.direction == "credit" and lower <= t.amount < th.REPORTING_THRESHOLD),
        key=lambda t: t.executed_at,
    )
    if len(candidates) < th.STRUCTURING_MIN_COUNT:
        return None

    times = [t.executed_at for t in candidates]
    count, start = _best_window(times, timedelta(days=th.STRUCTURING_WINDOW_DAYS))
    if count < th.STRUCTURING_MIN_COUNT:
        return None

    end = start + timedelta(days=th.STRUCTURING_WINDOW_DAYS)
    matched = [t for t in candidates if start <= t.executed_at < end]
    total = sum((t.amount for t in matched), Decimal("0"))

    return RuleFinding(
        "STRUCTURING",
        th.RULE_WEIGHTS["STRUCTURING"],
        {
            "account_ref": account.account_ref,
            "txn_count": len(matched),
            "total": str(total),
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "transaction_refs": [t.txn_ref for t in matched],
        },
    )


def check_smurfing(account: Account, transactions: list[Transaction]) -> RuleFinding | None:
    candidates = sorted(
        (t for t in transactions if t.direction == "credit" and t.amount < th.REPORTING_THRESHOLD and t.counterparty_ref),
        key=lambda t: t.executed_at,
    )
    if len(candidates) < th.SMURFING_MIN_ORIGINATORS:
        return None

    window = timedelta(days=th.SMURFING_WINDOW_DAYS)
    best_originators, best_start, best_matched = 0, None, []
    for t in candidates:
        end = t.executed_at + window
        in_window = [c for c in candidates if t.executed_at <= c.executed_at < end]
        distinct = len({c.counterparty_ref for c in in_window})
        if distinct > best_originators:
            best_originators, best_start, best_matched = distinct, t.executed_at, in_window

    if best_originators < th.SMURFING_MIN_ORIGINATORS:
        return None

    return RuleFinding(
        "SMURFING",
        th.RULE_WEIGHTS["SMURFING"],
        {
            "account_ref": account.account_ref,
            "distinct_originators": best_originators,
            "txn_count": len(best_matched),
            "window": {"start": best_start.isoformat(), "end": (best_start + window).isoformat()},
            "transaction_refs": [t.txn_ref for t in best_matched],
        },
    )


def check_rapid_movement(account: Account, transactions: list[Transaction]) -> RuleFinding | None:
    credits = sorted((t for t in transactions if t.direction == "credit"), key=lambda t: t.amount, reverse=True)
    debits = [t for t in transactions if t.direction == "debit"]
    window = timedelta(hours=th.RAPID_MOVEMENT_WINDOW_HOURS)

    for c in credits:
        if c.amount < th.RAPID_MOVEMENT_MIN_CREDIT_AMOUNT:
            continue
        matched = [d for d in debits if c.executed_at <= d.executed_at <= c.executed_at + window]
        moved = min(sum((d.amount for d in matched), Decimal("0")), c.amount)
        fraction = float(moved / c.amount)
        if fraction >= th.RAPID_MOVEMENT_MIN_FRACTION:
            return RuleFinding(
                "RAPID_MOVEMENT",
                th.RULE_WEIGHTS["RAPID_MOVEMENT"],
                {
                    "account_ref": account.account_ref,
                    "credit_amount": str(c.amount),
                    "moved_fraction": round(fraction, 3),
                    "transaction_refs": [c.txn_ref] + [d.txn_ref for d in matched],
                },
            )
    return None


def check_high_velocity(account: Account, transactions: list[Transaction]) -> RuleFinding | None:
    if len(transactions) < 2:
        return None

    by_day = Counter(t.executed_at.date() for t in transactions)
    if len(by_day) < 2:
        return None

    peak_day, peak_count = max(by_day.items(), key=lambda kv: kv[1])
    baseline_counts = [c for d, c in by_day.items() if d != peak_day]
    if not baseline_counts:
        return None

    mean = statistics.fmean(baseline_counts)
    std = statistics.pstdev(baseline_counts) if len(baseline_counts) > 1 else 0.0
    threshold = mean + th.HIGH_VELOCITY_STD_MULTIPLIER * std

    if peak_count > threshold and peak_count >= th.HIGH_VELOCITY_MIN_ABSOLUTE_COUNT:
        matched = [t for t in transactions if t.executed_at.date() == peak_day]
        return RuleFinding(
            "HIGH_VELOCITY",
            th.RULE_WEIGHTS["HIGH_VELOCITY"],
            {
                "account_ref": account.account_ref,
                "peak_day": peak_day.isoformat(),
                "peak_count": peak_count,
                "baseline_mean": round(mean, 2),
                "baseline_std": round(std, 2),
                "transaction_refs": [t.txn_ref for t in matched],
            },
        )
    return None


def check_cash_intensive(account: Account, features: dict[str, float]) -> RuleFinding | None:
    if account.account_type in th.CASH_INTENSIVE_EXCLUDE_ACCOUNT_TYPES:
        return None
    if features["cash_ratio"] > th.CASH_INTENSIVE_RATIO:
        return RuleFinding(
            "CASH_INTENSIVE",
            th.RULE_WEIGHTS["CASH_INTENSIVE"],
            {"account_ref": account.account_ref, "cash_ratio": round(features["cash_ratio"], 3)},
        )
    return None


def check_cross_border_risk(account: Account, transactions: list[Transaction], high_risk_countries: frozenset[str]) -> RuleFinding | None:
    hits = [t for t in transactions if t.counterparty_country in high_risk_countries]
    if not hits:
        return None
    return RuleFinding(
        "CROSS_BORDER_RISK",
        th.RULE_WEIGHTS["CROSS_BORDER_RISK"],
        {
            "account_ref": account.account_ref,
            "countries": sorted({t.counterparty_country for t in hits}),
            "transaction_refs": [t.txn_ref for t in hits[:20]],
        },
    )


def check_round_amounts(account: Account, transactions: list[Transaction], features: dict[str, float]) -> RuleFinding | None:
    if len(transactions) < th.ROUND_AMOUNTS_MIN_COUNT:
        return None
    if features["round_amount_ratio"] <= th.ROUND_AMOUNTS_RATIO:
        return None
    matched = [t for t in transactions if t.amount % Decimal("1000") == 0]
    return RuleFinding(
        "ROUND_AMOUNTS",
        th.RULE_WEIGHTS["ROUND_AMOUNTS"],
        {
            "account_ref": account.account_ref,
            "round_amount_ratio": round(features["round_amount_ratio"], 3),
            "transaction_refs": [t.txn_ref for t in matched[:20]],
        },
    )


def check_profile_deviation(account: Account, features: dict[str, float]) -> RuleFinding | None:
    if features["volume_vs_expected_ratio"] <= th.PROFILE_DEVIATION_MULTIPLIER:
        return None
    return RuleFinding(
        "PROFILE_DEVIATION",
        th.RULE_WEIGHTS["PROFILE_DEVIATION"],
        {
            "account_ref": account.account_ref,
            "volume_vs_expected_ratio": round(features["volume_vs_expected_ratio"], 2),
            "expected_monthly_volume": str(account.expected_monthly_volume),
        },
    )


def check_dormant_reactivation(account: Account, transactions: list[Transaction]) -> RuleFinding | None:
    if len(transactions) < 2:
        return None

    times = sorted(t.executed_at for t in transactions)
    gaps = [times[i] - times[i - 1] for i in range(1, len(times))]
    max_gap = max(gaps)
    if max_gap.days < th.DORMANT_MIN_INACTIVE_DAYS:
        return None

    gap_idx = gaps.index(max_gap)
    boundary_pre, boundary_post = times[gap_idx], times[gap_idx + 1]
    pre_txns = [t for t in transactions if t.executed_at <= boundary_pre]
    post_txns = [t for t in transactions if t.executed_at >= boundary_post]
    if not pre_txns or not post_txns:
        return None

    pre_span_days = max(1, (boundary_pre - times[0]).days)
    post_span_days = max(1, (times[-1] - boundary_post).days)
    pre_daily_mean = float(sum((t.amount for t in pre_txns), Decimal("0"))) / pre_span_days
    post_daily_mean = float(sum((t.amount for t in post_txns), Decimal("0"))) / post_span_days

    if pre_daily_mean <= 0:
        return None  # no pre-gap baseline to compare against
    multiplier = post_daily_mean / pre_daily_mean

    if multiplier < th.DORMANT_REACTIVATION_MULTIPLIER:
        return None

    return RuleFinding(
        "DORMANT_REACTIVATION",
        th.RULE_WEIGHTS["DORMANT_REACTIVATION"],
        {
            "account_ref": account.account_ref,
            "dormant_days": max_gap.days,
            "reactivation_multiplier": round(multiplier, 2),
            "transaction_refs": [t.txn_ref for t in post_txns],
        },
    )


def check_circular_flow(graph, accounts_by_ref: dict[str, Account]) -> list[RuleFinding]:
    """Cross-account: delegates the actual cycle search to graph.py, then
    turns each qualifying cycle into one finding per participating account
    (mirroring the one-finding-per-account shape of every other rule, so
    downstream code — Alert persistence, eval matching — doesn't need a
    special case for this rule)."""
    cycles = find_circular_flows(graph, min_retention=th.CIRCULAR_FLOW_MIN_RETENTION, max_len=th.CIRCULAR_FLOW_MAX_LEN)

    findings: list[RuleFinding] = []
    seen: set[str] = set()
    for cycle in cycles:
        nodes = cycle["nodes"]
        txn_refs: list[str] = []
        for i in range(len(nodes)):
            src, dst = nodes[i], nodes[(i + 1) % len(nodes)]
            if graph.has_edge(src, dst):
                txn_refs.extend(graph[src][dst].get("txn_refs", []))

        for node in nodes:
            if node in seen or node not in accounts_by_ref:
                continue
            seen.add(node)
            findings.append(
                RuleFinding(
                    "CIRCULAR_FLOW",
                    th.RULE_WEIGHTS["CIRCULAR_FLOW"],
                    {
                        "account_ref": node,
                        "cycle_account_refs": nodes,
                        "retention": cycle["retention"],
                        "hops": cycle["hops"],
                        "transaction_refs": txn_refs,
                    },
                )
            )
    return findings
