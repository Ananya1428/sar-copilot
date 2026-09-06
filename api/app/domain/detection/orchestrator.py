"""Detection run orchestration (blueprint §12, end-to-end flowchart):
feature engineering -> rule engine + ML ensemble + graph analysis ->
composite scoring -> persisted Alert rows.

Design note on when an Alert gets written: every fired rule finding is
persisted as its own Alert row, regardless of the account's overall
composite band. The composite/band is descriptive context stored on the
alert (blueprint §12's flowchart uses it for case-opening, not for
deciding whether evidence gets recorded at all) — gating persistence on
the band would risk silently dropping a real rule firing whenever an
account's OTHER two signals (ML, graph) happened to be quiet enough to
keep the composite under the MEDIUM boundary. An audit-oriented detection
layer should never do that. Accounts with zero fired rules only get an
Alert if the ML/graph signal alone is already at MEDIUM or HIGH (recorded
under a synthetic `ML_ANOMALY` rule_code); accounts with zero fired rules
and a LOW band get nothing, matching §12's flowchart ("Low -> No action").
"""

import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.detection.graph import build_flow_graph, find_circular_flows, find_hubs, pass_through_score
from app.domain.detection.ml import AnomalyEnsemble
from app.domain.detection.rules import (
    RuleFinding,
    check_cash_intensive,
    check_circular_flow,
    check_cross_border_risk,
    check_dormant_reactivation,
    check_high_velocity,
    check_profile_deviation,
    check_rapid_movement,
    check_round_amounts,
    check_smurfing,
    check_structuring,
)
from app.domain.detection.scoring import band_for_score, composite_score, graph_score_for_account, rule_score
from app.domain.detection.thresholds import ML_MIN_ACCOUNTS_TO_FIT
from app.domain.features.engineering import FEATURES, compute_features, features_to_vector, load_high_risk_countries
from app.models.account import Account
from app.models.alert import Alert
from app.models.transaction import Transaction

ML_ANOMALY_RULE_CODE = "ML_ANOMALY"


def _run_per_account_rules(account: Account, transactions: list[Transaction], features: dict, high_risk_countries: frozenset[str]) -> list[RuleFinding]:
    findings = [
        check_structuring(account, transactions),
        check_smurfing(account, transactions),
        check_rapid_movement(account, transactions),
        check_high_velocity(account, transactions),
        check_cash_intensive(account, features),
        check_cross_border_risk(account, transactions, high_risk_countries),
        check_round_amounts(account, transactions, features),
        check_profile_deviation(account, features),
        check_dormant_reactivation(account, transactions),
    ]
    return [f for f in findings if f is not None]


def run_detection(session: Session) -> dict:
    accounts = list(session.scalars(select(Account)))
    if not accounts:
        return {"accounts_evaluated": 0, "alerts_created": 0, "band_counts": {}}

    account_ref_by_id = {a.id: a.account_ref for a in accounts}
    accounts_by_ref = {a.account_ref: a for a in accounts}

    all_txns = list(session.scalars(select(Transaction)))
    txns_by_account: dict[uuid.UUID, list[Transaction]] = defaultdict(list)
    for t in all_txns:
        txns_by_account[t.account_id].append(t)

    high_risk_countries = load_high_risk_countries()

    # 1. Feature engineering, per account.
    features_by_account = {
        a.id: compute_features(a, txns_by_account.get(a.id, []), high_risk_countries) for a in accounts
    }

    # 2. Per-account deterministic rules.
    findings_by_account: dict[uuid.UUID, list[RuleFinding]] = defaultdict(list)
    for a in accounts:
        findings_by_account[a.id] = _run_per_account_rules(
            a, txns_by_account.get(a.id, []), features_by_account[a.id], high_risk_countries
        )

    # 3. Graph analysis + the cross-account CIRCULAR_FLOW rule.
    graph = build_flow_graph(all_txns, account_ref_by_id)
    for finding in check_circular_flow(graph, accounts_by_ref):
        acc = accounts_by_ref[finding.rule_evidence["account_ref"]]
        findings_by_account[acc.id].append(finding)

    cycles = find_circular_flows(graph)
    hubs = find_hubs(graph)
    betweenness = pass_through_score(graph)
    graph_score_by_account = {
        a.id: graph_score_for_account(a.account_ref, cycles, hubs, betweenness) for a in accounts
    }

    # 4. ML ensemble, fit fresh on this run's full account population
    #    (unsupervised — ground truth is never used here, only in eval).
    matrix = np.array([features_to_vector(features_by_account[a.id]) for a in accounts])
    index_by_account_id = {a.id: i for i, a in enumerate(accounts)}
    ensemble: AnomalyEnsemble | None = None
    if len(accounts) >= ML_MIN_ACCOUNTS_TO_FIT:
        ensemble = AnomalyEnsemble()
        ensemble.fit(matrix, FEATURES)
        scores = ensemble.score()
        ml_score_by_account = {a.id: float(scores[index_by_account_id[a.id]]) for a in accounts}
    else:
        ml_score_by_account = {a.id: 0.0 for a in accounts}

    # 5. Composite scoring + persistence.
    now = datetime.now(UTC)
    band_counts: Counter = Counter()
    alerts_created = 0

    for a in accounts:
        r_score = rule_score(findings_by_account[a.id])
        m_score = ml_score_by_account[a.id]
        g_score = graph_score_by_account[a.id]
        composite = composite_score(r_score, m_score, g_score)
        band = band_for_score(composite)
        band_counts[band] += 1
        score_decimal = Decimal(str(round(composite, 4)))

        account_findings = findings_by_account[a.id]
        if account_findings:
            for finding in account_findings:
                session.add(
                    Alert(
                        account_id=a.id,
                        rule_code=finding.rule_code,
                        score=score_decimal,
                        severity=band,
                        raised_at=now,
                        rule_evidence=finding.rule_evidence,
                    )
                )
                alerts_created += 1
        elif band in ("HIGH", "MEDIUM") and ensemble is not None:
            explanation = ensemble.explain(matrix[index_by_account_id[a.id]])
            session.add(
                Alert(
                    account_id=a.id,
                    rule_code=ML_ANOMALY_RULE_CODE,
                    score=score_decimal,
                    severity=band,
                    raised_at=now,
                    rule_evidence={
                        "account_ref": a.account_ref,
                        "ml_score": round(m_score, 4),
                        "top_features": explanation,
                    },
                )
            )
            alerts_created += 1

    session.flush()

    return {
        "accounts_evaluated": len(accounts),
        "alerts_created": alerts_created,
        "band_counts": dict(band_counts),
        "ml_ensemble_fitted": ensemble is not None,
    }
