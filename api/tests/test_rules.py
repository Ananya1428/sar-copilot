from datetime import UTC, datetime, timedelta

from app.domain.detection import rules
from app.domain.detection.graph import build_flow_graph
from tests.factories import make_account, make_txn

BASE = datetime(2024, 3, 1, 12, 0, tzinfo=UTC)


def test_structuring_fires_on_qualifying_cash_deposits():
    account = make_account()
    txns = [make_txn(account, 8600, "credit", BASE + timedelta(days=i), is_cash=True) for i in range(4)]
    finding = rules.check_structuring(account, txns)
    assert finding is not None
    assert finding.rule_code == "STRUCTURING"
    assert finding.rule_evidence["txn_count"] == 4


def test_structuring_does_not_fire_below_min_count():
    account = make_account()
    txns = [make_txn(account, 8600, "credit", BASE + timedelta(days=i), is_cash=True) for i in range(2)]
    assert rules.check_structuring(account, txns) is None


def test_structuring_ignores_amounts_outside_the_band():
    account = make_account()
    # Below 0.85*10000 = 8500, so these don't count as structuring deposits.
    txns = [make_txn(account, 5000, "credit", BASE + timedelta(days=i), is_cash=True) for i in range(4)]
    assert rules.check_structuring(account, txns) is None


def test_smurfing_fires_on_many_distinct_originators():
    account = make_account()
    txns = [
        make_txn(account, 3000, "credit", BASE + timedelta(days=i), counterparty_ref=f"originator-{i}")
        for i in range(6)
    ]
    finding = rules.check_smurfing(account, txns)
    assert finding is not None
    assert finding.rule_evidence["distinct_originators"] == 6


def test_smurfing_does_not_fire_with_too_few_originators():
    account = make_account()
    txns = [
        make_txn(account, 3000, "credit", BASE + timedelta(days=i), counterparty_ref=f"originator-{i}")
        for i in range(3)
    ]
    assert rules.check_smurfing(account, txns) is None


def test_rapid_movement_fires_when_most_value_leaves_within_window():
    account = make_account()
    txns = [
        make_txn(account, 10000, "credit", BASE),
        make_txn(account, 8000, "debit", BASE + timedelta(hours=10)),
    ]
    finding = rules.check_rapid_movement(account, txns)
    assert finding is not None
    assert finding.rule_evidence["moved_fraction"] == 0.8


def test_rapid_movement_does_not_fire_below_threshold_fraction():
    account = make_account()
    txns = [
        make_txn(account, 10000, "credit", BASE),
        make_txn(account, 5000, "debit", BASE + timedelta(hours=10)),
    ]
    assert rules.check_rapid_movement(account, txns) is None


def test_rapid_movement_ignores_trivial_credits_below_materiality_floor():
    # A $240 credit followed by an unrelated $172 debit clears the 70%
    # fraction easily but carries no suspicious meaning — this is the
    # false-positive mechanism found via eval/run_eval.py against a full
    # synthetic dataset (see thresholds.py's RAPID_MOVEMENT_MIN_CREDIT_AMOUNT).
    account = make_account()
    txns = [
        make_txn(account, 240.44, "credit", BASE),
        make_txn(account, 172.29, "debit", BASE + timedelta(hours=6)),
    ]
    assert rules.check_rapid_movement(account, txns) is None


def test_high_velocity_fires_on_burst_above_baseline():
    account = make_account()
    txns = []
    for day in range(5):
        txns.append(make_txn(account, 100, "credit", BASE + timedelta(days=day)))  # 1/day baseline
    burst_day = BASE + timedelta(days=10)
    txns += [make_txn(account, 50, "debit", burst_day + timedelta(minutes=i)) for i in range(10)]
    finding = rules.check_high_velocity(account, txns)
    assert finding is not None
    assert finding.rule_evidence["peak_count"] == 10


def test_high_velocity_does_not_fire_on_uniform_activity():
    account = make_account()
    txns = []
    for day in range(6):
        txns += [make_txn(account, 100, "credit", BASE + timedelta(days=day, hours=h)) for h in (1, 2)]
    assert rules.check_high_velocity(account, txns) is None


def test_cash_intensive_fires_above_ratio_for_non_business_accounts():
    account = make_account(account_type="checking")
    finding = rules.check_cash_intensive(account, {"cash_ratio": 0.8})
    assert finding is not None


def test_cash_intensive_does_not_fire_for_business_accounts():
    account = make_account(account_type="business")
    assert rules.check_cash_intensive(account, {"cash_ratio": 0.8}) is None


def test_cash_intensive_does_not_fire_below_ratio():
    account = make_account(account_type="checking")
    assert rules.check_cash_intensive(account, {"cash_ratio": 0.3}) is None


def test_cross_border_risk_fires_on_high_risk_counterparty():
    account = make_account()
    txns = [make_txn(account, 100, "credit", BASE, counterparty_country="AF")]
    finding = rules.check_cross_border_risk(account, txns, frozenset({"AF"}))
    assert finding is not None
    assert finding.rule_evidence["countries"] == ["AF"]


def test_cross_border_risk_does_not_fire_without_high_risk_counterparty():
    account = make_account()
    txns = [make_txn(account, 100, "credit", BASE, counterparty_country="US")]
    assert rules.check_cross_border_risk(account, txns, frozenset({"AF"})) is None


def test_round_amounts_fires_above_ratio_and_min_count():
    account = make_account()
    txns = [make_txn(account, 1000 if i < 6 else 1234, "credit", BASE + timedelta(days=i)) for i in range(10)]
    finding = rules.check_round_amounts(account, txns, {"round_amount_ratio": 0.6})
    assert finding is not None


def test_round_amounts_does_not_fire_below_min_count():
    txns_count = 5
    account = make_account()
    txns = [make_txn(account, 1000, "credit", BASE + timedelta(days=i)) for i in range(txns_count)]
    assert rules.check_round_amounts(account, txns, {"round_amount_ratio": 1.0}) is None


def test_profile_deviation_fires_above_multiplier():
    account = make_account()
    finding = rules.check_profile_deviation(account, {"volume_vs_expected_ratio": 6.0})
    assert finding is not None


def test_profile_deviation_does_not_fire_below_multiplier():
    account = make_account()
    assert rules.check_profile_deviation(account, {"volume_vs_expected_ratio": 1.2}) is None


def test_dormant_reactivation_fires_on_long_gap_then_burst():
    account = make_account()
    pre = [make_txn(account, 50, "credit", BASE + timedelta(days=i)) for i in range(5)]
    post_start = BASE + timedelta(days=40)  # 35-day gap, above the 30-day default
    post = [make_txn(account, 5000, "credit", post_start + timedelta(hours=i)) for i in range(3)]
    finding = rules.check_dormant_reactivation(account, pre + post)
    assert finding is not None
    assert finding.rule_evidence["dormant_days"] >= 30


def test_dormant_reactivation_does_not_fire_on_short_gap():
    account = make_account()
    pre = [make_txn(account, 50, "credit", BASE + timedelta(days=i)) for i in range(5)]
    post_start = BASE + timedelta(days=10)  # only a 5-day gap
    post = [make_txn(account, 5000, "credit", post_start + timedelta(hours=i)) for i in range(3)]
    assert rules.check_dormant_reactivation(account, pre + post) is None


def test_circular_flow_fires_only_for_cycle_participants():
    a, b, c, outsider = (make_account(account_ref=ref) for ref in ("ACC-A", "ACC-B", "ACC-C", "ACC-OUT"))
    account_ref_by_id = {x.id: x.account_ref for x in (a, b, c, outsider)}

    txns = [
        make_txn(a, 10000, "debit", BASE, counterparty_account_ref="ACC-B"),
        make_txn(b, 10000, "debit", BASE + timedelta(hours=6), counterparty_account_ref="ACC-C"),
        make_txn(c, 10000, "debit", BASE + timedelta(hours=12), counterparty_account_ref="ACC-A"),
    ]
    graph = build_flow_graph(txns, account_ref_by_id)
    accounts_by_ref = {x.account_ref: x for x in (a, b, c, outsider)}

    findings = rules.check_circular_flow(graph, accounts_by_ref)

    fired_refs = {f.rule_evidence["account_ref"] for f in findings}
    assert fired_refs == {"ACC-A", "ACC-B", "ACC-C"}
    assert all(f.rule_code == "CIRCULAR_FLOW" for f in findings)
    assert all(f.rule_evidence["retention"] == 1.0 for f in findings)


def test_circular_flow_does_not_fire_without_a_cycle():
    a, b = make_account(account_ref="ACC-A"), make_account(account_ref="ACC-B")
    account_ref_by_id = {a.id: a.account_ref, b.id: b.account_ref}
    txns = [make_txn(a, 10000, "debit", BASE, counterparty_account_ref="ACC-B")]
    graph = build_flow_graph(txns, account_ref_by_id)
    accounts_by_ref = {a.account_ref: a, b.account_ref: b}
    assert rules.check_circular_flow(graph, accounts_by_ref) == []
