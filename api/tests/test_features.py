from datetime import UTC, datetime, timedelta

from app.domain.features.engineering import FEATURES, compute_features
from tests.factories import make_account, make_txn


def test_compute_features_returns_all_keys():
    account = make_account()
    base = datetime(2024, 3, 1, 12, 0, tzinfo=UTC)
    feats = compute_features(account, [make_txn(account, 100, "credit", base)], frozenset())
    assert set(feats.keys()) == set(FEATURES)


def test_compute_features_empty_transactions_is_all_zero():
    account = make_account()
    feats = compute_features(account, [], frozenset())
    assert all(v == 0.0 for v in feats.values())


def test_cash_ratio_and_round_amount_ratio():
    account = make_account()
    base = datetime(2024, 3, 1, tzinfo=UTC)
    txns = [
        make_txn(account, 1000, "credit", base, is_cash=True),  # cash, round
        make_txn(account, 1234.56, "debit", base + timedelta(hours=1)),  # neither
        make_txn(account, 2000, "credit", base + timedelta(hours=2), is_cash=True),  # cash, round
        make_txn(account, 500, "debit", base + timedelta(hours=3)),  # neither
    ]
    feats = compute_features(account, txns, frozenset())
    assert feats["cash_ratio"] == 0.5
    assert feats["round_amount_ratio"] == 0.5


def test_high_risk_country_ratio():
    account = make_account()
    base = datetime(2024, 3, 1, tzinfo=UTC)
    txns = [
        make_txn(account, 100, "credit", base, counterparty_country="US"),
        make_txn(account, 100, "credit", base + timedelta(hours=1), counterparty_country="AF"),
    ]
    feats = compute_features(account, txns, frozenset({"AF"}))
    assert feats["high_risk_country_ratio"] == 0.5


def test_distinct_counterparties_and_herfindahl_concentration():
    account = make_account()
    base = datetime(2024, 3, 1, tzinfo=UTC)
    txns = [
        make_txn(account, 100, "credit", base, counterparty_ref="A"),
        make_txn(account, 100, "credit", base + timedelta(hours=1), counterparty_ref="A"),
        make_txn(account, 100, "credit", base + timedelta(hours=2), counterparty_ref="B"),
    ]
    feats = compute_features(account, txns, frozenset())
    assert feats["distinct_counterparties"] == 2
    # HHI on transaction-count share: (2/3)^2 + (1/3)^2 = 5/9
    assert abs(feats["counterparty_concentration"] - 5 / 9) < 1e-9


def test_velocity_max_24h_finds_the_busiest_window():
    account = make_account()
    base = datetime(2024, 3, 1, tzinfo=UTC)
    txns = [
        make_txn(account, 100, "credit", base),
        make_txn(account, 100, "credit", base + timedelta(minutes=10)),
        make_txn(account, 100, "credit", base + timedelta(minutes=20)),
        make_txn(account, 100, "credit", base + timedelta(days=5)),  # isolated, outside the burst
    ]
    feats = compute_features(account, txns, frozenset())
    assert feats["velocity_max_24h"] == 3


def test_volume_vs_expected_ratio_against_declared_profile():
    account = make_account(expected_monthly_volume="1000.00")
    base = datetime(2024, 1, 1, tzinfo=UTC)
    # Span exactly 30 days -> months_observed = 1.0; expected_total = 1000;
    # observed total = 5000 -> ratio 5.0.
    txns = [
        make_txn(account, 2500, "credit", base),
        make_txn(account, 2500, "credit", base + timedelta(days=30)),
    ]
    feats = compute_features(account, txns, frozenset())
    assert abs(feats["volume_vs_expected_ratio"] - 5.0) < 1e-9


def test_pass_through_ratio_matches_debit_within_window():
    account = make_account()
    base = datetime(2024, 3, 1, tzinfo=UTC)
    txns = [
        make_txn(account, 1000, "credit", base),
        make_txn(account, 900, "debit", base + timedelta(hours=10)),
    ]
    feats = compute_features(account, txns, frozenset())
    assert abs(feats["pass_through_ratio"] - 0.9) < 1e-9


def test_pass_through_ratio_ignores_debits_outside_window():
    account = make_account()
    base = datetime(2024, 3, 1, tzinfo=UTC)
    txns = [
        make_txn(account, 1000, "credit", base),
        make_txn(account, 900, "debit", base + timedelta(hours=72)),  # outside 48h window
    ]
    feats = compute_features(account, txns, frozenset())
    assert feats["pass_through_ratio"] == 0.0
