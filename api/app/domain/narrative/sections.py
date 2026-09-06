"""The narrative's ordered section schema (blueprint §13.3), adapted to
Part 3's actual `EvidencePack` field names — which, conveniently, already
match the blueprint's illustrative ones (`subjects`, `transactions`,
`typologies`, `aggregates`, `ml_findings`, `graph_findings`) since
schema.py was built as a direct reproduction of §10.2. `required_evidence`
values here are therefore literal `EvidencePack` attribute names,
consumed via `getattr` in engine.py's `_scope_evidence`.

Two `must_contain` placeholders from the blueprint's illustrative version
don't correspond to anything this build's schema models and are dropped
rather than kept as unsatisfiable checks:
- `"introduction".must_contain` drops `filing_institution` — no filing
  institution/branch concept exists anywhere in Part 1's schema.
- `"where".must_contain` drops `branches` for the same reason; `countries`
  is kept since `aggregates.distinct_countries` is real.

`must_contain` values are otherwise kept as the blueprint's semantic
placeholders (not live field lookups) — actually verifying a narrative
contains them is Part 5's completeness check, not this part's job; this
module just needs to carry the data forward accurately.
"""

NARRATIVE_SECTIONS: list[dict] = [
    {
        "id": "introduction",
        "label": "Introduction and basis for filing",
        "required_evidence": ["subjects", "aggregates", "typologies"],
        "max_sentences": 3,
        "must_contain": ["subject_name", "period_start", "period_end", "total_amount"],
        "static": False,
    },
    {
        "id": "who",
        "label": "Subject identification",
        "required_evidence": ["subjects"],
        "max_sentences": 4,
        "must_contain": ["subject_name", "account_ref", "relationship_start", "occupation"],
        "static": False,
    },
    {
        "id": "what_when",
        "label": "Activity description and timeline",
        "required_evidence": ["transactions", "aggregates"],
        "max_sentences": 6,
        "must_contain": ["txn_count", "total_amount", "period_start", "period_end", "channel"],
        "static": False,
    },
    {
        "id": "where",
        "label": "Locations and jurisdictions",
        "required_evidence": ["transactions", "subjects"],
        "max_sentences": 3,
        "must_contain": ["countries"],
        "static": False,
    },
    {
        "id": "how",
        "label": "Mechanics of the activity",
        "required_evidence": ["typologies", "graph_findings"],
        "max_sentences": 5,
        "must_contain": ["typology_label", "supporting_txn_count"],
        "static": False,
    },
    {
        "id": "why",
        "label": "Basis for suspicion",
        "required_evidence": ["typologies", "ml_findings", "subjects"],
        "max_sentences": 5,
        "must_contain": ["typology_label", "deviation_metric"],
        "static": False,
    },
    {
        "id": "conclusion",
        "label": "Actions taken and retention",
        "required_evidence": [],
        "max_sentences": 2,
        "must_contain": [],
        "static": True,
    },
]

SECTION_IDS: list[str] = [s["id"] for s in NARRATIVE_SECTIONS]


def get_section(section_id: str) -> dict:
    for section in NARRATIVE_SECTIONS:
        if section["id"] == section_id:
            return section
    raise KeyError(f"unknown narrative section: {section_id}")
