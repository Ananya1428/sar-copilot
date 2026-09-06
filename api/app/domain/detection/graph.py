"""Money-flow graph analysis (blueprint §12.4).

`build_flow_graph` is adapted from the blueprint's illustrative version:
the original assumed `t.originator_ref` / `t.beneficiary_ref` fields that
don't exist on Part 1's `Transaction` model. This build's schema instead
records, on each internal transfer, the account's own side (`account_id`,
`direction`) and the counterparty's account ref (`counterparty_account_ref`,
set only when the counterparty is one of our own accounts — see Part 1's
transaction.py docstring). Nodes here are therefore account refs, and each
transaction is turned into a directed edge using `direction` to determine
which end is the source. `find_circular_flows`, `find_hubs`, and
`pass_through_score` are otherwise as specified.
"""

import uuid

import networkx as nx

from app.models.transaction import Transaction


def build_flow_graph(transactions: list[Transaction], account_ref_by_id: dict[uuid.UUID, str]) -> nx.DiGraph:
    """`account_ref_by_id` maps each transaction's own `account_id` to that
    account's `account_ref`, so the caller controls loading (avoids N+1
    lazy-loads of `transaction.account` inside a detection run).

    Only `direction == "debit"` rows are used. Part 1's generator records
    each internal transfer as a pair of rows — a debit on the sender and a
    credit on the receiver — both carrying the same amount and pointing at
    each other via `counterparty_account_ref`. The debit leg alone already
    fully describes the directed edge; also processing the paired credit
    leg would add the same transfer to the same edge a second time.
    """
    G = nx.DiGraph()
    for t in transactions:
        if t.direction != "debit" or not t.counterparty_account_ref:
            continue
        this_ref = account_ref_by_id.get(t.account_id)
        if not this_ref:
            continue

        src, dst = this_ref, t.counterparty_account_ref

        if G.has_edge(src, dst):
            G[src][dst]["value"] += float(t.amount)
            G[src][dst]["count"] += 1
            G[src][dst]["txn_refs"].append(t.txn_ref)
        else:
            G.add_edge(src, dst, value=float(t.amount), count=1, txn_refs=[t.txn_ref])
    return G


def find_circular_flows(G: nx.DiGraph, min_retention: float = 0.6, max_len: int = 6) -> list[dict]:
    """Round-tripping: value that returns to origin."""
    findings = []
    for cycle in nx.simple_cycles(G, length_bound=max_len):
        if len(cycle) < 3:
            continue
        vals = [G[cycle[i]][cycle[(i + 1) % len(cycle)]]["value"] for i in range(len(cycle))]
        retention = min(vals) / max(vals) if max(vals) else 0
        if retention >= min_retention:
            findings.append(
                {
                    "type": "CIRCULAR_FLOW",
                    "nodes": cycle,
                    "retention": round(retention, 3),
                    "min_value": min(vals),
                    "hops": len(cycle),
                }
            )
    return findings


def find_hubs(G: nx.DiGraph, fan_threshold: int = 8) -> list[dict]:
    """Collector (fan-in) and mule-distribution (fan-out) patterns."""
    out = []
    for n in G.nodes():
        fan_in, fan_out = G.in_degree(n), G.out_degree(n)
        if fan_in >= fan_threshold:
            out.append({"type": "FAN_IN", "node": n, "degree": fan_in})
        if fan_out >= fan_threshold:
            out.append({"type": "FAN_OUT", "node": n, "degree": fan_out})
    return out


def pass_through_score(G: nx.DiGraph) -> dict[str, float]:
    """Betweenness -> intermediaries in layering chains."""
    return nx.betweenness_centrality(G, weight="value")
