"""Evidence Pack builder (blueprint §10.2 / §11.1): turns a Case's Alerts,
subjects, and transactions into a structured, hashed, fully-enumerable
EvidencePack — the narrative engine's (Part 4) only input.

Design choices, since the blueprint's schema/builder are illustrative and
several details had to be adapted to Part 1/2's actual tables:

- **Which account a case is about**: derived from the case's own Alerts'
  `account_id` (case_assembly.py creates exactly one case per account, so
  every alert on a case shares the same account_id) — not from a new
  `CaseSubject.account_id` column, which would need a schema change for
  no benefit here.
- **The case's evidence period**: the union of every fired alert's
  `rule_evidence["transaction_refs"]`, bounded to their earliest/latest
  `executed_at`. Most rules don't store an explicit `window` key in their
  evidence (only STRUCTURING/SMURFING do) — but the transactions a rule
  cites in `transaction_refs` ARE that rule's evidence, so bounding by
  them is equivalent and works uniformly across every rule. If no alert on
  the case cites any specific transaction at all (CASH_INTENSIVE and
  PROFILE_DEVIATION carry no transaction_refs), the period falls back to
  the account's full transaction history for this batch.
- **Typology labels/descriptions**: reused from Part 1's
  `data/reference/typology_dictionary.json` (extended, not duplicated
  elsewhere, with the four Part 2 rules the original file didn't cover
  plus the synthetic ML_ANOMALY code — see that file).
- **Aggregate numbers**: computed by calling Part 2's own
  `compute_features` over the case's period-filtered transactions, not
  recomputed independently. `max_amount` / `velocity_max_24h` /
  `volume_vs_expected_ratio` map directly onto `max_single_amount` /
  `velocity_peak_24h` / `deviation_from_expected`; `observed_monthly_volume`
  on the subject is derived from that same ratio times the account's own
  `expected_monthly_volume`, not computed a second, independent way.
- **Aggregate EvidenceItems have no single source row** (they're sums
  across many transactions) — anchored to the account row, with
  `source_field` naming the aggregation performed (`"computed:..."`).
- **`content_hash`** is computed over the pack's substantive content only
  — `pack_id` (a fresh UUID) and `built_at` (wall-clock time) are excluded,
  or building the same case twice could never hash identically.
"""

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.detection.thresholds import RULE_WEIGHTS
from app.domain.evidence.schema import (
    AggregateEvidence,
    EvidenceItem,
    EvidencePack,
    SubjectEvidence,
    TransactionEvidence,
    TypologyEvidence,
    fmt_amount,
    fmt_date,
)
from app.domain.features.engineering import compute_features, load_high_risk_countries
from app.models.account import Account
from app.models.alert import Alert
from app.models.case import Case
from app.models.case_subject import CaseSubject
from app.models.evidence import EvidenceItem as EvidenceItemRow
from app.models.evidence import EvidencePack as EvidencePackRow
from app.models.transaction import Transaction

BUILDER_VERSION = "0.1.0"

_TYPOLOGY_DICT_PATH = Path("data/reference/typology_dictionary.json")

# Which quantitative_basis fields (per rule_code) are surfaced as their own
# checkable EvidenceItem, and what type each is. Deliberately explicit and
# per-rule rather than a blind generic dump of every key in rule_evidence:
# some keys (transaction_refs, window, top_features, account_ref) are
# either already represented elsewhere in the pack or are internal/
# diagnostic and never meant to be quoted in a narrative.
QUANT_BASIS_FIELD_TYPES: dict[str, dict[str, str]] = {
    "STRUCTURING": {"txn_count": "count", "total": "amount"},
    "SMURFING": {"distinct_originators": "count", "txn_count": "count"},
    "RAPID_MOVEMENT": {"credit_amount": "amount", "moved_fraction": "count"},
    "HIGH_VELOCITY": {"peak_count": "count", "baseline_mean": "count", "baseline_std": "count", "peak_day": "date"},
    "CASH_INTENSIVE": {"cash_ratio": "count"},
    "CROSS_BORDER_RISK": {},  # "countries" handled separately below (list -> location items)
    "ROUND_AMOUNTS": {"round_amount_ratio": "count"},
    "PROFILE_DEVIATION": {"volume_vs_expected_ratio": "count", "expected_monthly_volume": "amount"},
    "DORMANT_REACTIVATION": {"dormant_days": "count", "reactivation_multiplier": "count"},
    "CIRCULAR_FLOW": {"retention": "count", "hops": "count"},
    "ML_ANOMALY": {"ml_score": "count"},
}

_VOLATILE_FIELDS = {"pack_id", "built_at", "content_hash"}


def _load_typology_dictionary() -> dict:
    if not _TYPOLOGY_DICT_PATH.exists():
        return {}
    return json.loads(_TYPOLOGY_DICT_PATH.read_text())


def _add_item(
    items: dict[str, EvidenceItem],
    key: str,
    item_type: str,
    display_value: str,
    raw_value: dict,
    source_table: str,
    source_row_id: uuid.UUID,
    source_field: str,
) -> None:
    items[key] = EvidenceItem(
        key=key,
        type=item_type,
        display_value=display_value,
        raw_value=raw_value,
        source_table=source_table,
        source_row_id=source_row_id,
        source_field=source_field,
    )


def _evidence_period(alerts: list[Alert], account_txns: list[Transaction]) -> tuple[datetime, datetime]:
    refs: set[str] = set()
    for alert in alerts:
        refs.update(alert.rule_evidence.get("transaction_refs", []))

    matched = [t for t in account_txns if t.txn_ref in refs] if refs else []
    pool = matched if matched else account_txns
    if not pool:
        now = datetime.now(UTC)
        return now, now
    times = [t.executed_at for t in pool]
    return min(times), max(times)


def _flagged_by_map(alerts: list[Alert]) -> dict[str, list[str]]:
    """txn_ref -> sorted rule_codes that cited it across this case's
    alerts. A transaction in scope but not specifically cited by any rule
    gets an empty list — being part of the evidence period and being the
    specific basis for a rule firing are different things."""
    out: dict[str, set[str]] = defaultdict(set)
    for alert in alerts:
        for ref in alert.rule_evidence.get("transaction_refs", []):
            out[ref].add(alert.rule_code)
    return {ref: sorted(codes) for ref, codes in out.items()}


def _build_subjects(
    case_subjects: list[CaseSubject], account: Account, features: dict[str, float], items: dict[str, EvidenceItem]
) -> list[SubjectEvidence]:
    result = []
    for cs in case_subjects:
        customer = cs.customer
        observed_monthly_volume = (
            account.expected_monthly_volume * Decimal(str(features["volume_vs_expected_ratio"]))
        ).quantize(Decimal("0.01"))

        subj = SubjectEvidence(
            customer_ref=customer.customer_ref,
            legal_name=customer.legal_name,
            entity_type=customer.entity_type,
            role=cs.role,
            # Only one account is currently ever linked to a case (see
            # module docstring) — a customer with multiple accounts, only
            # some of which are implicated, is future work.
            account_refs=[account.account_ref],
            occupation=customer.occupation,
            country=customer.country,
            risk_rating=customer.risk_rating,
            relationship_start=customer.onboarded_at,
            expected_monthly_volume=account.expected_monthly_volume,
            observed_monthly_volume=observed_monthly_volume,
        )
        result.append(subj)

        prefix = f"subject.{cs.role}"
        _add_item(items, f"{prefix}.customer_ref", "text", subj.customer_ref, {"customer_ref": subj.customer_ref}, "customers", customer.id, "customer_ref")
        _add_item(items, f"{prefix}.legal_name", "entity", subj.legal_name, {"legal_name": subj.legal_name}, "customers", customer.id, "legal_name")
        _add_item(items, f"{prefix}.entity_type", "text", subj.entity_type, {"entity_type": subj.entity_type}, "customers", customer.id, "entity_type")
        _add_item(items, f"{prefix}.country", "location", subj.country, {"country": subj.country}, "customers", customer.id, "country")
        _add_item(items, f"{prefix}.risk_rating", "text", subj.risk_rating, {"risk_rating": subj.risk_rating}, "customers", customer.id, "risk_rating")
        _add_item(items, f"{prefix}.relationship_start", "date", fmt_date(subj.relationship_start), {"onboarded_at": subj.relationship_start.isoformat()}, "customers", customer.id, "onboarded_at")
        _add_item(items, f"{prefix}.expected_monthly_volume", "amount", fmt_amount(subj.expected_monthly_volume), {"expected_monthly_volume": str(subj.expected_monthly_volume)}, "accounts", account.id, "expected_monthly_volume")
        _add_item(items, f"{prefix}.observed_monthly_volume", "amount", fmt_amount(subj.observed_monthly_volume), {"observed_monthly_volume": str(subj.observed_monthly_volume)}, "accounts", account.id, "computed:observed_monthly_volume")
        if subj.occupation:
            _add_item(items, f"{prefix}.occupation", "entity", subj.occupation, {"occupation": subj.occupation}, "customers", customer.id, "occupation")
        for ref in subj.account_refs:
            _add_item(items, f"{prefix}.account_ref.{ref}", "text", ref, {"account_ref": ref}, "accounts", account.id, "account_ref")

    return result


def _build_transactions(
    period_txns: list[Transaction], flagged_by_map: dict[str, list[str]], items: dict[str, EvidenceItem]
) -> list[TransactionEvidence]:
    result = []
    for t in sorted(period_txns, key=lambda t: t.executed_at):
        te = TransactionEvidence(
            txn_ref=t.txn_ref,
            executed_at=t.executed_at,
            amount=t.amount,
            currency=t.currency,
            direction=t.direction,
            channel=t.channel,
            counterparty_ref=t.counterparty_ref,
            counterparty_country=t.counterparty_country,
            is_cash=t.is_cash,
            flagged_by=flagged_by_map.get(t.txn_ref, []),
        )
        result.append(te)

        prefix = f"transaction.{t.txn_ref}"
        _add_item(items, f"{prefix}.txn_ref", "text", t.txn_ref, {"txn_ref": t.txn_ref}, "transactions", t.id, "txn_ref")
        _add_item(items, f"{prefix}.amount", "amount", fmt_amount(t.amount), {"amount": str(t.amount)}, "transactions", t.id, "amount")
        _add_item(items, f"{prefix}.executed_at", "date", fmt_date(t.executed_at), {"executed_at": t.executed_at.isoformat()}, "transactions", t.id, "executed_at")
        _add_item(items, f"{prefix}.channel", "text", t.channel, {"channel": t.channel}, "transactions", t.id, "channel")
        if t.counterparty_ref:
            _add_item(items, f"{prefix}.counterparty_ref", "text", t.counterparty_ref, {"counterparty_ref": t.counterparty_ref}, "transactions", t.id, "counterparty_ref")
        if t.counterparty_country:
            _add_item(items, f"{prefix}.counterparty_country", "location", t.counterparty_country, {"counterparty_country": t.counterparty_country}, "transactions", t.id, "counterparty_country")

    return result


def _build_typologies(alerts: list[Alert], typology_dict: dict, items: dict[str, EvidenceItem]) -> list[TypologyEvidence]:
    """Note observed on real generator output: for CIRCULAR_FLOW,
    `supporting_txn_refs` / `quantitative_basis["transaction_refs"]` can
    include refs belonging to the OTHER accounts in the cycle, since one
    detected cycle spans multiple accounts but case_assembly.py opens one
    case per account (see its docstring). Those other-account refs
    correctly do NOT appear in this pack's own `transactions` list, which
    is scoped to this case's account — `quantitative_basis["cycle_account_refs"]`
    names the other participants explicitly, so this is discoverable
    rather than silently confusing. Every ref that DOES belong to this
    account still gets a real EvidenceItem via `_build_transactions`."""
    latest_by_code: dict[str, Alert] = {}
    for alert in alerts:
        current = latest_by_code.get(alert.rule_code)
        if current is None or alert.raised_at > current.raised_at:
            latest_by_code[alert.rule_code] = alert

    result = []
    for code in sorted(latest_by_code):
        alert = latest_by_code[code]
        meta = typology_dict.get(code, {"label": code.replace("_", " ").title(), "description": f"Detected by the {code} rule."})
        basis = alert.rule_evidence
        weight = RULE_WEIGHTS.get(code)
        if weight is None:
            weight = float(basis.get("ml_score", 0.5))

        typ = TypologyEvidence(
            code=code,
            label=meta["label"],
            description=meta["description"],
            weight=float(weight),
            supporting_txn_refs=basis.get("transaction_refs", []),
            quantitative_basis=basis,
        )
        result.append(typ)

        _add_item(items, f"typology.{code}.code", "typology", code, {"code": code}, "alerts", alert.id, "rule_code")
        _add_item(items, f"typology.{code}.label", "text", typ.label, {"label": typ.label}, "alerts", alert.id, "rule_code")

        for field, item_type in QUANT_BASIS_FIELD_TYPES.get(code, {}).items():
            if field not in basis:
                continue
            display = str(basis[field])
            _add_item(items, f"typology.{code}.quantitative_basis.{field}", item_type, display, {field: basis[field]}, "alerts", alert.id, f"rule_evidence.{field}")

        if code == "CROSS_BORDER_RISK":
            for country in basis.get("countries", []):
                _add_item(items, f"typology.{code}.quantitative_basis.countries.{country}", "location", country, {"country": country}, "alerts", alert.id, "rule_evidence.countries")

    return result


def _build_aggregates(
    account: Account,
    period_txns: list[Transaction],
    features: dict[str, float],
    period_start: datetime,
    period_end: datetime,
    items: dict[str, EvidenceItem],
) -> AggregateEvidence:
    cash_txn_count = sum(1 for t in period_txns if t.is_cash)
    countries = sorted({t.counterparty_country for t in period_txns if t.counterparty_country})

    agg = AggregateEvidence(
        period_start=period_start.date(),
        period_end=period_end.date(),
        total_credit=Decimal(str(round(features["total_credit_30d"], 2))),
        total_debit=Decimal(str(round(features["total_debit_30d"], 2))),
        txn_count=int(features["txn_count_30d"]),
        cash_txn_count=cash_txn_count,
        distinct_counterparties=int(features["distinct_counterparties"]),
        distinct_countries=countries,
        max_single_amount=Decimal(str(round(features["max_amount"], 2))),
        velocity_peak_24h=int(features["velocity_max_24h"]),
        deviation_from_expected=Decimal(str(round(features["volume_vs_expected_ratio"], 4))),
    )

    _add_item(items, "aggregates.period_start", "date", fmt_date(agg.period_start), {}, "accounts", account.id, "computed:period_start")
    _add_item(items, "aggregates.period_end", "date", fmt_date(agg.period_end), {}, "accounts", account.id, "computed:period_end")
    _add_item(items, "aggregates.total_credit", "amount", fmt_amount(agg.total_credit), {}, "accounts", account.id, "computed:total_credit")
    _add_item(items, "aggregates.total_debit", "amount", fmt_amount(agg.total_debit), {}, "accounts", account.id, "computed:total_debit")
    _add_item(items, "aggregates.txn_count", "count", str(agg.txn_count), {}, "accounts", account.id, "computed:txn_count")
    _add_item(items, "aggregates.cash_txn_count", "count", str(agg.cash_txn_count), {}, "accounts", account.id, "computed:cash_txn_count")
    _add_item(items, "aggregates.distinct_counterparties", "count", str(agg.distinct_counterparties), {}, "accounts", account.id, "computed:distinct_counterparties")
    _add_item(items, "aggregates.max_single_amount", "amount", fmt_amount(agg.max_single_amount), {}, "accounts", account.id, "computed:max_single_amount")
    _add_item(items, "aggregates.velocity_peak_24h", "count", str(agg.velocity_peak_24h), {}, "accounts", account.id, "computed:velocity_peak_24h")
    _add_item(items, "aggregates.deviation_from_expected", "count", str(agg.deviation_from_expected), {}, "accounts", account.id, "computed:deviation_from_expected")

    for country in countries:
        rep_txn = next((t for t in period_txns if t.counterparty_country == country), None)
        source_table, source_row_id = ("transactions", rep_txn.id) if rep_txn else ("accounts", account.id)
        _add_item(items, f"aggregates.distinct_countries.{country}", "location", country, {}, source_table, source_row_id, "counterparty_country")

    return agg


def _ml_and_graph_findings(alerts: list[Alert]) -> tuple[dict, dict]:
    ml_findings: dict = {}
    graph_findings: dict = {}
    for alert in alerts:
        if alert.rule_code == "ML_ANOMALY":
            ml_findings = alert.rule_evidence
        elif alert.rule_code == "CIRCULAR_FLOW":
            graph_findings = alert.rule_evidence
    return ml_findings, graph_findings


def _content_hash(pack_data: dict) -> str:
    hashable = {k: v for k, v in pack_data.items() if k not in _VOLATILE_FIELDS}
    canonical = json.dumps(hashable, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def build_evidence_pack(session: Session, case: Case) -> EvidencePack:
    alerts = list(session.scalars(select(Alert).where(Alert.case_id == case.id)))
    if not alerts:
        raise ValueError(f"case {case.case_ref} has no alerts to build evidence from")

    account_id = alerts[0].account_id
    account = session.get(Account, account_id)

    case_subjects = list(
        session.scalars(select(CaseSubject).where(CaseSubject.case_id == case.id).order_by(CaseSubject.role))
    )
    all_account_txns = list(session.scalars(select(Transaction).where(Transaction.account_id == account_id)))
    period_start, period_end = _evidence_period(alerts, all_account_txns)
    period_txns = [t for t in all_account_txns if period_start <= t.executed_at <= period_end]

    high_risk_countries = load_high_risk_countries()
    typology_dict = _load_typology_dictionary()
    features = compute_features(account, period_txns, high_risk_countries)

    items: dict[str, EvidenceItem] = {}
    subjects = _build_subjects(case_subjects, account, features, items)
    transactions = _build_transactions(period_txns, _flagged_by_map(alerts), items)
    typologies = _build_typologies(alerts, typology_dict, items)
    aggregates = _build_aggregates(account, period_txns, features, period_start, period_end, items)
    ml_findings, graph_findings = _ml_and_graph_findings(alerts)

    base_data = {
        "case_ref": case.case_ref,
        "builder_version": BUILDER_VERSION,
        "subjects": [s.model_dump(mode="json") for s in subjects],
        "transactions": [t.model_dump(mode="json") for t in transactions],
        "typologies": [t.model_dump(mode="json") for t in typologies],
        "aggregates": aggregates.model_dump(mode="json"),
        "ml_findings": ml_findings,
        "graph_findings": graph_findings,
        "prior_sars": [],
        "items": [i.model_dump(mode="json") for i in items.values()],
    }

    return EvidencePack(
        pack_id=uuid.uuid4(),
        case_ref=case.case_ref,
        built_at=datetime.now(UTC),
        builder_version=BUILDER_VERSION,
        content_hash=_content_hash(base_data),
        subjects=subjects,
        transactions=transactions,
        typologies=typologies,
        aggregates=aggregates,
        ml_findings=ml_findings,
        graph_findings=graph_findings,
        prior_sars=[],
        items=list(items.values()),
    )


def persist_evidence_pack(session: Session, case: Case, pack: EvidencePack) -> EvidencePackRow:
    """Always inserts a new row — packs are immutable/versioned (blueprint
    §9.2 P3); building a second pack for the same case must never overwrite
    the first."""
    row = EvidencePackRow(
        id=pack.pack_id,
        case_id=case.id,
        payload=pack.model_dump(mode="json"),
        content_hash=pack.content_hash,
        built_at=pack.built_at,
        builder_version=pack.builder_version,
    )
    session.add(row)
    session.flush()

    for item in pack.items:
        session.add(
            EvidenceItemRow(
                pack_id=row.id,
                item_key=item.key,
                item_type=item.type,
                display_value=item.display_value,
                raw_value=item.raw_value,
                source_table=item.source_table,
                source_row_id=item.source_row_id,
            )
        )
    session.flush()
    return row
