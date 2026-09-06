"""Hand-built EvidencePack for narrative-engine tests — no DB involved.
Deliberately includes a counterparty country so the "where" section has
something to render, alongside a STRUCTURING typology so "how"/"why" do too."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.domain.evidence.schema import (
    AggregateEvidence,
    EvidenceItem,
    EvidencePack,
    SubjectEvidence,
    TransactionEvidence,
    TypologyEvidence,
)


def make_sample_pack() -> EvidencePack:
    subject = SubjectEvidence(
        customer_ref="CUS-4471",
        legal_name="Rajesh Mehta",
        entity_type="individual",
        role="primary",
        account_refs=["ACC-88213"],
        occupation="Retail Trader",
        country="IN",
        risk_rating="MEDIUM",
        relationship_start=date(2021, 6, 14),
        expected_monthly_volume=Decimal("15000.00"),
        observed_monthly_volume=Decimal("128500.00"),
    )

    txn1 = TransactionEvidence(
        txn_ref="TXN-0001",
        executed_at=datetime(2024, 3, 3, 10, 0, tzinfo=UTC),
        amount=Decimal("8600.00"),
        currency="USD",
        direction="credit",
        channel="cash",
        counterparty_ref=None,
        counterparty_country=None,
        is_cash=True,
        flagged_by=["STRUCTURING"],
    )
    txn2 = TransactionEvidence(
        txn_ref="TXN-0002",
        executed_at=datetime(2024, 3, 4, 11, 0, tzinfo=UTC),
        amount=Decimal("8700.00"),
        currency="USD",
        direction="credit",
        channel="cash",
        counterparty_ref="external-party",
        counterparty_country="IN",
        is_cash=True,
        flagged_by=["STRUCTURING"],
    )

    typology = TypologyEvidence(
        code="STRUCTURING",
        label="Structuring / smurfing (deposits)",
        description="Deposits engineered in amounts just below the reporting threshold to avoid detection.",
        weight=1.0,
        supporting_txn_refs=["TXN-0001", "TXN-0002"],
        quantitative_basis={"txn_count": 2, "total": "17300.00"},
    )

    aggregates = AggregateEvidence(
        period_start=date(2024, 3, 3),
        period_end=date(2024, 3, 4),
        total_credit=Decimal("17300.00"),
        total_debit=Decimal("0.00"),
        txn_count=2,
        cash_txn_count=2,
        distinct_counterparties=1,
        distinct_countries=["IN"],
        max_single_amount=Decimal("8700.00"),
        velocity_peak_24h=1,
        deviation_from_expected=Decimal("8.5667"),
    )

    def item(key, type_, display_value, source_table="customers", source_field="") -> EvidenceItem:
        return EvidenceItem(
            key=key,
            type=type_,
            display_value=display_value,
            raw_value={},
            source_table=source_table,
            source_row_id=uuid.uuid4(),
            source_field=source_field,
        )

    items = [
        item("subject.primary.legal_name", "entity", "Rajesh Mehta", source_field="legal_name"),
        item("subject.primary.customer_ref", "text", "CUS-4471", source_field="customer_ref"),
        item("subject.primary.entity_type", "text", "individual", source_field="entity_type"),
        item("subject.primary.country", "location", "IN", source_field="country"),
        item("subject.primary.risk_rating", "text", "MEDIUM", source_field="risk_rating"),
        item("subject.primary.relationship_start", "date", "2021-06-14", source_field="onboarded_at"),
        item("subject.primary.occupation", "entity", "Retail Trader", source_field="occupation"),
        item("subject.primary.expected_monthly_volume", "amount", "15000.00", source_table="accounts", source_field="expected_monthly_volume"),
        item("subject.primary.observed_monthly_volume", "amount", "128500.00", source_table="accounts", source_field="computed:observed_monthly_volume"),
        item("subject.primary.account_ref.ACC-88213", "text", "ACC-88213", source_table="accounts", source_field="account_ref"),
        item("transaction.TXN-0001.txn_ref", "text", "TXN-0001", source_table="transactions", source_field="txn_ref"),
        item("transaction.TXN-0001.amount", "amount", "8600.00", source_table="transactions", source_field="amount"),
        item("transaction.TXN-0001.executed_at", "date", "2024-03-03", source_table="transactions", source_field="executed_at"),
        item("transaction.TXN-0001.channel", "text", "cash", source_table="transactions", source_field="channel"),
        item("transaction.TXN-0002.txn_ref", "text", "TXN-0002", source_table="transactions", source_field="txn_ref"),
        item("transaction.TXN-0002.amount", "amount", "8700.00", source_table="transactions", source_field="amount"),
        item("transaction.TXN-0002.executed_at", "date", "2024-03-04", source_table="transactions", source_field="executed_at"),
        item("transaction.TXN-0002.channel", "text", "cash", source_table="transactions", source_field="channel"),
        item("transaction.TXN-0002.counterparty_ref", "text", "external-party", source_table="transactions", source_field="counterparty_ref"),
        item("transaction.TXN-0002.counterparty_country", "location", "IN", source_table="transactions", source_field="counterparty_country"),
        item("typology.STRUCTURING.code", "typology", "STRUCTURING", source_table="alerts", source_field="rule_code"),
        item("typology.STRUCTURING.label", "text", "Structuring / smurfing (deposits)", source_table="alerts", source_field="rule_code"),
        item("typology.STRUCTURING.quantitative_basis.txn_count", "count", "2", source_table="alerts", source_field="rule_evidence.txn_count"),
        item("typology.STRUCTURING.quantitative_basis.total", "amount", "17300.00", source_table="alerts", source_field="rule_evidence.total"),
        item("aggregates.period_start", "date", "2024-03-03", source_table="accounts", source_field="computed:period_start"),
        item("aggregates.period_end", "date", "2024-03-04", source_table="accounts", source_field="computed:period_end"),
        item("aggregates.total_credit", "amount", "17300.00", source_table="accounts", source_field="computed:total_credit"),
        item("aggregates.total_debit", "amount", "0.00", source_table="accounts", source_field="computed:total_debit"),
        item("aggregates.max_single_amount", "amount", "8700.00", source_table="accounts", source_field="computed:max_single_amount"),
        item("aggregates.deviation_from_expected", "count", "8.5667", source_table="accounts", source_field="computed:deviation_from_expected"),
        item("aggregates.distinct_countries.IN", "location", "IN", source_table="transactions", source_field="counterparty_country"),
    ]

    return EvidencePack(
        pack_id=uuid.uuid4(),
        case_ref="CASE-TEST",
        built_at=datetime.now(UTC),
        builder_version="0.1.0",
        content_hash="0" * 64,
        subjects=[subject],
        transactions=[txn1, txn2],
        typologies=[typology],
        aggregates=aggregates,
        ml_findings={},
        graph_findings={},
        prior_sars=[],
        items=items,
    )
