"""Composite risk scoring (blueprint §12.5): three independent [0,1]
sub-scores — rules, ML ensemble, graph — combined by fixed weights into one
composite score, then banded into HIGH/MEDIUM/LOW. Weights and band
boundaries live in thresholds.py, not here.
"""

from app.domain.detection import thresholds as th
from app.domain.detection.rules import RuleFinding


def rule_score(findings: list[RuleFinding]) -> float:
    """Sum of fired rules' weights, capped at 1.0 — one strong rule (weight
    1.0) can already saturate this; several weak/contextual rules together
    can too, but no single weak rule can on its own."""
    return min(1.0, sum(f.weight for f in findings))


def graph_score_for_account(account_ref: str, cycles: list[dict], hubs: list[dict], betweenness: dict[str, float]) -> float:
    """Turns graph.py's raw findings into one [0,1] score per account.
    Participating in a qualifying circular flow is itself the strongest
    possible graph signal (1.0); being a fan-in/fan-out hub is treated as a
    secondary signal; betweenness centrality is scaled up since raw values
    are typically small even for genuinely central nodes in graphs this
    size."""
    if any(account_ref in c["nodes"] for c in cycles):
        return 1.0

    score = 0.0
    if any(h["node"] == account_ref for h in hubs):
        score = max(score, 0.6)

    bc = betweenness.get(account_ref, 0.0)
    score = max(score, min(1.0, bc * 5))
    return score


def band_for_score(score: float) -> str:
    for lower, label in th.RISK_BANDS:
        if score >= lower:
            return label
    return "LOW"


def composite_score(rule_score_value: float, ml_score_value: float, graph_score_value: float) -> float:
    return (
        th.RULE_SCORE_WEIGHT * rule_score_value
        + th.ML_SCORE_WEIGHT * ml_score_value
        + th.GRAPH_SCORE_WEIGHT * graph_score_value
    )
