"""End-to-end detection test: generate a fresh synthetic dataset (Part 1),
run the full detection layer (Part 2) against it, and check recall against
that generation's own ground truth.

Why the bar is 80%, not 100%: the rule engine's thresholds (thresholds.py)
are deliberately strict band/window checks, and the generator's injected
amounts are drawn from ranges that only mostly (not always) land inside
those bands — e.g. STRUCTURING amounts are drawn from [8200, 9900] while
the rule's qualifying band is [8500, 10000), so a minority of injected
instances can legitimately have too few amounts in-band to trip the
count threshold. That's a realistic property of any threshold-based
system and is worth measuring, not hiding by loosening thresholds until
everything trivially passes.
"""

import json
from collections import defaultdict

from app.domain.detection.orchestrator import run_detection
from app.domain.ingestion.synthetic import generate_dataset
from app.models import Account, Alert

RECALL_BAR = 0.80


def _account_refs(entry: dict) -> list[str]:
    return entry.get("account_refs") or [entry["account_ref"]]


def test_detection_recall_against_fresh_ground_truth(db_session, tmp_path):
    gt_path = tmp_path / "ground_truth.json"
    generate_dataset(db_session, n_accounts=80, days=90, seed=99, ground_truth_path=gt_path)
    db_session.flush()

    run_detection(db_session)
    db_session.flush()

    manifest = json.loads(gt_path.read_text())
    injections = manifest["injections"]

    rows = (
        db_session.query(Alert, Account.account_ref)
        .join(Account, Alert.account_id == Account.id)
        .all()
    )
    fired_by_account: dict[str, set[str]] = defaultdict(set)
    for alert, account_ref in rows:
        fired_by_account[account_ref].add(alert.rule_code)

    hit, total = 0, 0
    misses = []
    for entry in injections:
        typ = entry["typology"]
        refs = _account_refs(entry)
        total += 1
        if any(typ in fired_by_account[ref] for ref in refs):
            hit += 1
        else:
            misses.append((typ, refs))

    recall = hit / total if total else 0.0
    assert recall >= RECALL_BAR, (
        f"overall recall {recall:.0%} below the {RECALL_BAR:.0%} bar "
        f"({hit}/{total} injected instances matched); misses: {misses}"
    )


def test_detection_creates_no_alerts_for_a_clean_account():
    """A sanity check independent of the live-DB generator: an account with
    only quiet, unremarkable activity should not trip any per-account rule."""
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from app.domain.detection.rules import (
        check_cash_intensive,
        check_dormant_reactivation,
        check_high_velocity,
        check_profile_deviation,
        check_rapid_movement,
        check_smurfing,
        check_structuring,
    )
    from app.domain.features.engineering import compute_features
    from tests.factories import make_account, make_txn

    account = make_account(expected_monthly_volume="4000.00")
    base = datetime(2024, 1, 1, tzinfo=UTC)
    txns = []
    for month in range(3):
        month_start = base + timedelta(days=30 * month)
        txns.append(make_txn(account, 4000, "credit", month_start, channel="ach"))
        for week in range(4):
            txns.append(
                make_txn(
                    account,
                    Decimal("250.00"),
                    "debit",
                    month_start + timedelta(days=7 * week),
                    channel="card",
                    counterparty_ref=f"merchant-{week}",
                    counterparty_country="US",
                )
            )

    features = compute_features(account, txns, frozenset())
    findings = [
        check_structuring(account, txns),
        check_smurfing(account, txns),
        check_rapid_movement(account, txns),
        check_high_velocity(account, txns),
        check_cash_intensive(account, features),
        check_profile_deviation(account, features),
        check_dormant_reactivation(account, txns),
    ]
    assert all(f is None for f in findings), [f for f in findings if f is not None]
