"""The Evidence Pack (blueprint §10.2) — the object the narrative engine
(Part 4) will be given as its ONLY input. Reproduced field-for-field from
the blueprint; the only additions are two small helper formatting
functions used consistently by both this schema's own serialization and
builder.py, so a value's string form can never drift between the
substantive fields (subjects/transactions/typologies/aggregates) and its
corresponding `EvidenceItem` — see builder.py's module docstring for why
that consistency is the whole point of this object.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


def fmt_amount(value: Decimal) -> str:
    return str(value)


def fmt_date(value: date | datetime) -> str:
    if isinstance(value, datetime):
        value = value.date()
    return value.isoformat()


class EvidenceItem(BaseModel):
    """An atomic, verifiable fact. Every narrative claim maps to one of these."""

    key: str  # e.g. "subject.primary.legal_name"
    type: Literal["entity", "amount", "date", "count", "location", "channel", "typology", "text"]
    display_value: str  # exact string allowed in narrative
    raw_value: dict
    source_table: str
    source_row_id: UUID
    source_field: str
    confidence: float = 1.0  # 1.0 for direct DB reads (always true in this build)


class SubjectEvidence(BaseModel):
    customer_ref: str
    legal_name: str
    entity_type: str
    role: Literal["primary", "counterparty", "beneficiary", "originator"]
    account_refs: list[str]
    occupation: str | None
    country: str
    risk_rating: str
    relationship_start: date
    expected_monthly_volume: Decimal
    observed_monthly_volume: Decimal


class TransactionEvidence(BaseModel):
    txn_ref: str
    executed_at: datetime
    amount: Decimal
    currency: str
    direction: Literal["credit", "debit"]
    channel: str
    counterparty_ref: str | None
    counterparty_country: str | None
    is_cash: bool
    flagged_by: list[str]  # rule codes of alerts on this case that cited this transaction


class TypologyEvidence(BaseModel):
    code: str
    label: str
    description: str
    weight: float
    supporting_txn_refs: list[str]
    quantitative_basis: dict


class AggregateEvidence(BaseModel):
    period_start: date
    period_end: date
    total_credit: Decimal
    total_debit: Decimal
    txn_count: int
    cash_txn_count: int
    distinct_counterparties: int
    distinct_countries: list[str]
    max_single_amount: Decimal
    velocity_peak_24h: int
    deviation_from_expected: Decimal  # multiple of expected volume


class EvidencePack(BaseModel):
    """Immutable, hashed, versioned (blueprint §9.2 P3). The LLM's ONLY input."""

    pack_id: UUID
    case_ref: str
    built_at: datetime
    builder_version: str
    content_hash: str

    subjects: list[SubjectEvidence]
    transactions: list[TransactionEvidence]
    typologies: list[TypologyEvidence]
    aggregates: AggregateEvidence
    ml_findings: dict
    graph_findings: dict
    prior_sars: list[dict]
    items: list[EvidenceItem]

    def allowed_entities(self) -> set[str]:
        """Every proper noun the narrative may legally contain."""
        return {i.display_value for i in self.items if i.type in ("entity", "location")}

    def allowed_numbers(self) -> set[str]:
        """Every numeric token the narrative may legally contain."""
        return {i.display_value for i in self.items if i.type in ("amount", "count")}

    def allowed_dates(self) -> set[str]:
        return {i.display_value for i in self.items if i.type == "date"}
