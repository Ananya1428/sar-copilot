"""Deterministic Jinja2 template fallback (blueprint §13.6): renders a
complete narrative directly from an `EvidencePack`'s fields, with zero LLM
calls. Structurally guaranteed grounded — every sentence template below
draws only from named pack fields, paired explicitly with the exact
`EvidenceItem` keys (matching builder.py's dotted-path convention) those
fields correspond to, so TEMPLATE-mode output carries the same
sentence -> evidence_keys shape as HYBRID mode rather than a lesser one.

This is what ships when the LLM misbehaves (engine.py's retry/fallback),
and it is why the system can promise it never emits an ungrounded
narrative even under total model failure.
"""

from collections.abc import Callable

from jinja2 import Template

from app.domain.evidence.builder import QUANT_BASIS_FIELD_TYPES
from app.domain.evidence.schema import EvidencePack, TypologyEvidence
from app.domain.narrative.sections import NARRATIVE_SECTIONS

# Every transaction in the evidence period gets its own sentence; capped so
# a case with an unusually wide evidence period doesn't produce a
# narrative with hundreds of one-line sentences. The totals are already
# stated by the section's opening aggregate sentence regardless of the cap.
MAX_TRANSACTION_SENTENCES = 10

_TYPOLOGY_SUMMARY_TEMPLATES: dict[str, str] = {
    "STRUCTURING": "{{ b.txn_count }} cash deposits totalling {{ b.total }}, each structured below the reporting threshold",
    "SMURFING": "{{ b.distinct_originators }} distinct originators contributed deposits within the observed window",
    "RAPID_MOVEMENT": "{{ (b.moved_fraction * 100) | round(1) }} percent of a {{ b.credit_amount }} credit was moved out again within 48 hours",
    "CIRCULAR_FLOW": "funds moved through a {{ b.hops }}-hop cycle of accounts with {{ (b.retention * 100) | round(1) }} percent value retention",
    "HIGH_VELOCITY": "{{ b.peak_count }} transactions occurred on {{ b.peak_day }}, against a baseline average of {{ b.baseline_mean }}",
    "DORMANT_REACTIVATION": "following {{ b.dormant_days }} days without activity, transaction volume resumed at {{ b.reactivation_multiplier | round(1) }} times the prior daily average",
    "CASH_INTENSIVE": "cash transactions represented {{ (b.cash_ratio * 100) | round(1) }} percent of observed activity",
    "CROSS_BORDER_RISK": "transactions involved counterparties in {{ b.countries | join(', ') }}",
    "ROUND_AMOUNTS": "{{ (b.round_amount_ratio * 100) | round(1) }} percent of transactions were in round amounts",
    "PROFILE_DEVIATION": "observed volume was {{ b.volume_vs_expected_ratio | round(1) }} times the declared expected monthly volume of {{ b.expected_monthly_volume }}",
    "ML_ANOMALY": "the account's behavioural profile was flagged as anomalous by the unsupervised detection ensemble",
}


def _typology_summary(typ: TypologyEvidence) -> str:
    tmpl = _TYPOLOGY_SUMMARY_TEMPLATES.get(typ.code)
    if tmpl is None:
        return typ.description
    return Template(tmpl).render(b=typ.quantitative_basis)


def _quant_basis_keys(typ: TypologyEvidence) -> list[str]:
    """Exactly the EvidenceItem keys builder.py created for this
    typology's quantitative_basis (see QUANT_BASIS_FIELD_TYPES there) —
    reusing that same mapping guarantees these keys always exist in
    pack.items, with no risk of the two lists drifting apart."""
    fields = QUANT_BASIS_FIELD_TYPES.get(typ.code, {})
    keys = [f"typology.{typ.code}.quantitative_basis.{f}" for f in fields if f in typ.quantitative_basis]
    if typ.code == "CROSS_BORDER_RISK":
        keys += [f"typology.{typ.code}.quantitative_basis.countries.{c}" for c in typ.quantitative_basis.get("countries", [])]
    return keys


def _sentence(text_template: str, evidence_keys: list[str], **context) -> dict:
    text = Template(text_template).render(**context)
    return {"text": " ".join(text.split()), "evidence_keys": evidence_keys}


def render_introduction(pack: EvidencePack) -> list[dict]:
    primary = next((s for s in pack.subjects if s.role == "primary"), pack.subjects[0])
    agg = pack.aggregates
    return [
        _sentence(
            "This report concerns account activity conducted by {{ s.legal_name }}, customer reference "
            "{{ s.customer_ref }}, between {{ agg.period_start }} and {{ agg.period_end }}.",
            [f"subject.{primary.role}.legal_name", f"subject.{primary.role}.customer_ref", "aggregates.period_start", "aggregates.period_end"],
            s=primary, agg=agg,
        ),
        _sentence(
            "During this period, activity totalling {{ agg.total_credit }} in credits and {{ agg.total_debit }} "
            "in debits was identified as inconsistent with the subject's established profile.",
            ["aggregates.total_credit", "aggregates.total_debit"],
            agg=agg,
        ),
    ]


def render_who(pack: EvidencePack) -> list[dict]:
    out = []
    for s in pack.subjects:
        prefix = f"subject.{s.role}"
        out.append(_sentence(
            "The subject of this report is {{ s.legal_name }} ({{ s.entity_type }}), customer reference "
            "{{ s.customer_ref }}, who has maintained a relationship with the filing institution since "
            "{{ s.relationship_start }}.",
            [f"{prefix}.legal_name", f"{prefix}.entity_type", f"{prefix}.customer_ref", f"{prefix}.relationship_start"],
            s=s,
        ))
        if s.occupation:
            out.append(_sentence(
                "The subject is recorded as {{ s.occupation }} and resident in {{ s.country }}.",
                [f"{prefix}.occupation", f"{prefix}.country"],
                s=s,
            ))
        out.append(_sentence(
            "The activity described in this report was conducted through account{{ 's' if s.account_refs|length > 1 else '' }} "
            "{{ s.account_refs | join(', ') }}.",
            [f"{prefix}.account_ref.{ref}" for ref in s.account_refs],
            s=s,
        ))
    return out


def render_what_when(pack: EvidencePack) -> list[dict]:
    agg = pack.aggregates
    out = [
        _sentence(
            "Between {{ agg.period_start }} and {{ agg.period_end }}, {{ agg.txn_count }} transactions totalling "
            "{{ agg.total_credit }} in credits and {{ agg.total_debit }} in debits were recorded.",
            ["aggregates.period_start", "aggregates.period_end", "aggregates.txn_count", "aggregates.total_credit", "aggregates.total_debit"],
            agg=agg,
        )
    ]
    if agg.cash_txn_count:
        out.append(_sentence(
            "{{ agg.cash_txn_count }} of these transactions were conducted in cash.",
            ["aggregates.cash_txn_count"],
            agg=agg,
        ))
    for t in sorted(pack.transactions, key=lambda t: t.executed_at)[:MAX_TRANSACTION_SENTENCES]:
        prefix = f"transaction.{t.txn_ref}"
        out.append(_sentence(
            "On {{ t.executed_at.date() }}, a {{ t.direction }} of {{ t.amount }} was recorded via {{ t.channel }} "
            "(reference {{ t.txn_ref }}).",
            [f"{prefix}.executed_at", f"{prefix}.amount", f"{prefix}.channel", f"{prefix}.txn_ref"],
            t=t,
        ))
    return out


def render_where(pack: EvidencePack) -> list[dict]:
    countries = pack.aggregates.distinct_countries
    if not countries:
        return []
    return [
        _sentence(
            "Counterparties in this activity were located in {{ countries | join(', ') }}.",
            [f"aggregates.distinct_countries.{c}" for c in countries],
            countries=countries,
        )
    ]


def render_how(pack: EvidencePack) -> list[dict]:
    return [
        _sentence(
            "{{ typ.label }}: {{ summary }}.",
            [f"typology.{typ.code}.label", *_quant_basis_keys(typ)],
            typ=typ, summary=_typology_summary(typ),
        )
        for typ in pack.typologies
    ]


def render_why(pack: EvidencePack) -> list[dict]:
    out = [
        _sentence(
            "The activity is consistent with {{ typ.label }}: {{ summary }}.",
            [f"typology.{typ.code}.label", *_quant_basis_keys(typ)],
            typ=typ, summary=_typology_summary(typ),
        )
        for typ in pack.typologies
    ]
    primary = next((s for s in pack.subjects if s.role == "primary"), None)
    if primary is not None:
        out.append(_sentence(
            "The subject's declared expected monthly volume is {{ s.expected_monthly_volume }}, whereas observed "
            "volume over the reporting period was {{ s.observed_monthly_volume }}, representing "
            "{{ agg.deviation_from_expected }} times the declared expectation.",
            [f"subject.{primary.role}.expected_monthly_volume", f"subject.{primary.role}.observed_monthly_volume", "aggregates.deviation_from_expected"],
            s=primary, agg=pack.aggregates,
        ))
    return out


def render_conclusion(_pack: EvidencePack) -> list[dict]:
    """Fully static institutional boilerplate (blueprint §13.3: conclusion
    is the one section marked `static`) — no evidence_keys, because
    nothing here is drawn from the pack."""
    return [
        _sentence("The filing institution has not closed the account at the time of filing.", []),
        _sentence("Supporting documentation is retained and will be made available upon request.", []),
    ]


SECTION_RENDERERS: dict[str, Callable[[EvidencePack], list[dict]]] = {
    "introduction": render_introduction,
    "who": render_who,
    "what_when": render_what_when,
    "where": render_where,
    "how": render_how,
    "why": render_why,
    "conclusion": render_conclusion,
}


def render_section(section_id: str, pack: EvidencePack) -> list[dict]:
    return SECTION_RENDERERS[section_id](pack)


def render_all_sections(pack: EvidencePack) -> list[dict]:
    """Renders every section in order, tagging each sentence with its
    section id. TEMPLATE mode (and HYBRID's ultimate fallback) uses this
    to produce a complete narrative with zero LLM calls."""
    out = []
    for section in NARRATIVE_SECTIONS:
        sentences = render_section(section["id"], pack)
        for s in sentences:
            s["section"] = section["id"]
        out.extend(sentences)
    return out
