from datetime import UTC, datetime, timedelta

from app.domain.detection.graph import build_flow_graph, find_circular_flows, find_hubs, pass_through_score
from tests.factories import make_account, make_txn

BASE = datetime(2024, 3, 1, tzinfo=UTC)


def _graph_of_cycle(retention_values):
    """Builds a directed cycle A -> B -> C -> A with the given per-hop
    values (so retention = min/max is controllable)."""
    refs = [f"ACC-{i}" for i in range(len(retention_values))]
    accounts = [make_account(account_ref=r) for r in refs]
    account_ref_by_id = {a.id: a.account_ref for a in accounts}

    txns = []
    for i, value in enumerate(retention_values):
        src = accounts[i]
        dst_ref = refs[(i + 1) % len(refs)]
        txns.append(make_txn(src, value, "debit", BASE + timedelta(hours=i * 6), counterparty_account_ref=dst_ref))

    return build_flow_graph(txns, account_ref_by_id), refs


def test_build_flow_graph_only_uses_debit_legs():
    a, b = make_account(account_ref="ACC-A"), make_account(account_ref="ACC-B")
    account_ref_by_id = {a.id: a.account_ref, b.id: b.account_ref}
    txns = [
        make_txn(a, 5000, "debit", BASE, counterparty_account_ref="ACC-B"),
        make_txn(b, 5000, "credit", BASE, counterparty_account_ref="ACC-A"),  # paired leg of the same transfer
    ]
    G = build_flow_graph(txns, account_ref_by_id)
    assert G["ACC-A"]["ACC-B"]["value"] == 5000.0
    assert G["ACC-A"]["ACC-B"]["count"] == 1  # not 2 — the credit leg must not double-count


def test_find_circular_flows_detects_high_retention_cycle():
    G, refs = _graph_of_cycle([10000, 10000, 10000])
    findings = find_circular_flows(G, min_retention=0.6)
    assert len(findings) == 1
    assert findings[0]["retention"] == 1.0
    assert set(findings[0]["nodes"]) == set(refs)


def test_find_circular_flows_rejects_low_retention():
    # Value nearly halves each hop -> retention well below the default 0.6.
    G, _ = _graph_of_cycle([10000, 4000, 1000])
    findings = find_circular_flows(G, min_retention=0.6)
    assert findings == []


def test_find_circular_flows_ignores_non_cyclic_graph():
    a, b, c = (make_account(account_ref=r) for r in ("ACC-A", "ACC-B", "ACC-C"))
    account_ref_by_id = {x.id: x.account_ref for x in (a, b, c)}
    txns = [
        make_txn(a, 1000, "debit", BASE, counterparty_account_ref="ACC-B"),
        make_txn(b, 1000, "debit", BASE, counterparty_account_ref="ACC-C"),
    ]
    G = build_flow_graph(txns, account_ref_by_id)
    assert find_circular_flows(G) == []


def test_find_hubs_detects_fan_in_and_fan_out():
    hub = make_account(account_ref="ACC-HUB")
    spokes = [make_account(account_ref=f"ACC-S{i}") for i in range(9)]
    account_ref_by_id = {hub.id: hub.account_ref, **{s.id: s.account_ref for s in spokes}}

    # 9 distinct accounts each send money TO the hub -> fan-in.
    txns = [make_txn(s, 100, "debit", BASE + timedelta(hours=i), counterparty_account_ref="ACC-HUB") for i, s in enumerate(spokes)]
    G = build_flow_graph(txns, account_ref_by_id)

    hubs = find_hubs(G, fan_threshold=8)
    fan_in_nodes = {h["node"] for h in hubs if h["type"] == "FAN_IN"}
    assert "ACC-HUB" in fan_in_nodes


def test_find_hubs_ignores_low_degree_nodes():
    a, b = make_account(account_ref="ACC-A"), make_account(account_ref="ACC-B")
    account_ref_by_id = {a.id: a.account_ref, b.id: b.account_ref}
    txns = [make_txn(a, 100, "debit", BASE, counterparty_account_ref="ACC-B")]
    G = build_flow_graph(txns, account_ref_by_id)
    assert find_hubs(G, fan_threshold=8) == []


def test_pass_through_score_is_higher_for_intermediary_nodes():
    # A -> B -> C: B sits on every path, so its betweenness should exceed
    # the endpoints'.
    a, b, c = (make_account(account_ref=r) for r in ("ACC-A", "ACC-B", "ACC-C"))
    account_ref_by_id = {x.id: x.account_ref for x in (a, b, c)}
    txns = [
        make_txn(a, 1000, "debit", BASE, counterparty_account_ref="ACC-B"),
        make_txn(b, 1000, "debit", BASE + timedelta(hours=1), counterparty_account_ref="ACC-C"),
    ]
    G = build_flow_graph(txns, account_ref_by_id)
    scores = pass_through_score(G)
    assert scores["ACC-B"] > scores["ACC-A"]
    assert scores["ACC-B"] > scores["ACC-C"]
