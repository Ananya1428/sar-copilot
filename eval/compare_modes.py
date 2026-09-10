"""Compares TEMPLATE / HYBRID / FREEFORM generation modes over the same
real cases (blueprint §23.1's central experiment / Part 7). Runs each
mode against every case's latest evidence pack (building one if a case
doesn't have one yet), with the same seed, and reports real numbers for
every metric in §23's list: hallucination rate (fraction of generations
with a CRITICAL check failure — a fabricated/prohibited claim), numeric/
entity/prohibited violation rates, mean entailment score, mean
completeness score, typology coverage, material fact recall, generation
latency (p50/p95), retry/fallback rate (HYBRID only), and a separate
byte-identical reproducibility check.

N is whatever's actually in the seeded database (capped by an optional
CLI arg) — this reports the real N used, never assumes 100.

Must run inside the api container:

    docker compose exec api python eval/compare_modes.py [N]

HYBRID and FREEFORM each make a real Ollama call per case and can take
45s+ per generation on this machine's GPU — budget several minutes for
the full run.
"""

import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean

sys.path.insert(0, os.getcwd())

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.domain.evidence.builder import build_evidence_pack, persist_evidence_pack  # noqa: E402
from app.domain.evidence.schema import EvidencePack as EvidencePackSchema  # noqa: E402
from app.domain.narrative.engine import NarrativeEngine  # noqa: E402
from app.models.case import Case  # noqa: E402
from app.models.evidence import EvidencePack as EvidencePackRow  # noqa: E402

MODES = ["TEMPLATE", "HYBRID", "FREEFORM"]
DEFAULT_N = 5
SEED = 42


def _latest_pack_for(session, case) -> EvidencePackSchema:
    row = session.scalars(
        select(EvidencePackRow).where(EvidencePackRow.case_id == case.id).order_by(EvidencePackRow.built_at.desc())
    ).first()
    if row is None:
        pack = build_evidence_pack(session, case)
        row = persist_evidence_pack(session, case, pack)
        session.commit()
        return EvidencePackSchema.model_validate(row.payload)
    return EvidencePackSchema.model_validate(row.payload)


def _typology_coverage(body: str, pack: EvidencePackSchema) -> float | None:
    """Fraction of the pack's typologies whose label or code is literally
    named in the narrative body — a simple, explicit operationalisation
    since the blueprint doesn't define this metric precisely either."""
    if not pack.typologies:
        return None
    mentioned = sum(1 for t in pack.typologies if t.label in body or t.code in body)
    return mentioned / len(pack.typologies)


def _material_fact_recall(body: str, pack: EvidencePackSchema) -> float | None:
    """Fraction of a fixed set of "material" facts (subject name, primary
    typology label, total credit/debit, reporting period) that literally
    appear in the narrative body. Also an explicit operationalisation —
    the blueprint names this metric without defining it."""
    facts = []
    if pack.subjects:
        facts.append(pack.subjects[0].legal_name)
    if pack.typologies:
        facts.append(pack.typologies[0].label)
    facts.append(str(pack.aggregates.total_credit))
    facts.append(str(pack.aggregates.total_debit))
    facts.append(pack.aggregates.period_start.isoformat())
    facts.append(pack.aggregates.period_end.isoformat())
    facts = [f for f in facts if f]
    if not facts:
        return None
    hits = sum(1 for f in facts if f in body)
    return hits / len(facts)


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(p * (len(s) - 1))))
    return s[idx]


def run_comparison(n: int) -> dict:
    session = SessionLocal()
    try:
        cases = session.scalars(select(Case).order_by(Case.case_ref)).all()[:n]
        print(f"Evaluating {len(cases)} real case(s): {', '.join(c.case_ref for c in cases)}")
        print()

        engine = NarrativeEngine()  # real Verifier() by default (Part 5)
        per_mode = defaultdict(
            lambda: {
                "n": 0,
                "n_with_report": 0,
                "generation_failures": 0,  # no verifiable report at all (e.g. FREEFORM producing 0 parseable sentences)
                "passed": 0,
                "critical_fail": 0,
                "numeric_fail": 0,
                "entity_fail": 0,
                "prohibited_fail": 0,
                "entailment_scores": [],
                "completeness_scores": [],
                "typology_coverage": [],
                "material_fact_recall": [],
                "latencies": [],
                "attempts": [],
                "fallback_count": 0,
            }
        )
        records = []

        print(f"{'case':12s} {'mode':9s} {'actual_mode':18s} {'attempts':>8s} {'elapsed_s':>10s} {'passed':>8s} {'score':>7s}")
        print("-" * 80)

        for case in cases:
            pack = _latest_pack_for(session, case)
            for mode in MODES:
                start = time.monotonic()
                result = engine.generate(pack, mode=mode, seed=SEED)
                elapsed = time.monotonic() - start
                report = result.verification_report
                body = result.narrative_text

                m = per_mode[mode]
                m["n"] += 1
                m["latencies"].append(elapsed)
                m["attempts"].append(result.attempts)
                if mode == "HYBRID" and result.mode == "TEMPLATE_FALLBACK":
                    m["fallback_count"] += 1
                if report is None:
                    # No sentences survived parsing at all (seen with
                    # FREEFORM, which — unlike HYBRID — has no retry loop
                    # in engine.py's _generate_freeform: one malformed LLM
                    # response and generation simply fails). This must NOT
                    # silently count as "0% hallucination" — it produced no
                    # verifiable claims, which is a distinct, worse outcome
                    # than "verified and clean," and needs its own rate.
                    m["generation_failures"] += 1
                else:
                    m["n_with_report"] += 1
                    m["passed"] += int(report.passed)
                    m["critical_fail"] += int(bool(report.critical_failures))
                    m["numeric_fail"] += int(not report.checks["numeric"].passed)
                    m["entity_fail"] += int(not report.checks["entity"].passed)
                    m["prohibited_fail"] += int(not report.checks["prohibited"].passed)
                    m["entailment_scores"].append(report.checks["entailment"].score)
                    m["completeness_scores"].append(report.checks["completeness"].score)
                tc = _typology_coverage(body, pack)
                if tc is not None:
                    m["typology_coverage"].append(tc)
                mfr = _material_fact_recall(body, pack)
                if mfr is not None:
                    m["material_fact_recall"].append(mfr)

                records.append(
                    {
                        "case_ref": case.case_ref,
                        "requested_mode": mode,
                        "actual_mode": result.mode,
                        "attempts": result.attempts,
                        "elapsed_s": round(elapsed, 3),
                        "passed": report.passed if report else None,
                        "overall_score": float(report.overall_score) if report else None,
                    }
                )
                print(
                    f"{case.case_ref:12s} {mode:9s} {result.mode:18s} {result.attempts:8d} {elapsed:10.2f} "
                    f"{str(report.passed if report else 'N/A'):>8s} {(f'{report.overall_score:.3f}' if report else '—'):>7s}"
                )
    finally:
        session.close()

    summary = {}
    for mode in MODES:
        m = per_mode[mode]
        n_ = m["n"]
        n_report = m["n_with_report"]
        summary[mode] = {
            "n": n_,
            "generation_failure_rate": m["generation_failures"] / n_ if n_ else None,
            # Rates below are computed over generations that actually
            # produced a verification report — a generation that failed
            # outright is already counted separately above, not folded in
            # here as a misleading "0% hallucination."
            "n_with_report": n_report,
            "hallucination_rate": m["critical_fail"] / n_report if n_report else None,
            "verification_pass_rate": m["passed"] / n_report if n_report else None,
            "numeric_violation_rate": m["numeric_fail"] / n_report if n_report else None,
            "entity_violation_rate": m["entity_fail"] / n_report if n_report else None,
            "prohibited_violation_rate": m["prohibited_fail"] / n_report if n_report else None,
            "mean_entailment_score": mean(m["entailment_scores"]) if m["entailment_scores"] else None,
            "mean_completeness_score": mean(m["completeness_scores"]) if m["completeness_scores"] else None,
            # Typology coverage / material fact recall scan the rendered
            # BODY text directly, so they stay meaningful (and correctly
            # score 0) even for a generation that produced no verifiable
            # report — computed over all n, not just n_with_report.
            "mean_typology_coverage": mean(m["typology_coverage"]) if m["typology_coverage"] else None,
            "mean_material_fact_recall": mean(m["material_fact_recall"]) if m["material_fact_recall"] else None,
            "latency_p50_s": _percentile(m["latencies"], 0.50),
            "latency_p95_s": _percentile(m["latencies"], 0.95),
            "mean_attempts": mean(m["attempts"]) if m["attempts"] else None,
            "fallback_rate": m["fallback_count"] / n_ if mode == "HYBRID" and n_ else None,
        }

    return {"n_cases": len(cases), "case_refs": [c.case_ref for c in cases], "records": records, "summary": summary}


def print_summary_table(summary: dict) -> None:
    def fmt(v, pct=False):
        if v is None:
            return "—"
        return f"{v:.1%}" if pct else f"{v:.3f}"

    rows = [
        ("Generation failure rate (no verifiable output)", "generation_failure_rate", True),
        ("Hallucination rate (CRITICAL check failure)", "hallucination_rate", True),
        ("Verification pass rate", "verification_pass_rate", True),
        ("Numeric violation rate", "numeric_violation_rate", True),
        ("Entity violation rate", "entity_violation_rate", True),
        ("Prohibited violation rate", "prohibited_violation_rate", True),
        ("Mean entailment score", "mean_entailment_score", False),
        ("Mean completeness score", "mean_completeness_score", False),
        ("Mean typology coverage", "mean_typology_coverage", True),
        ("Mean material fact recall", "mean_material_fact_recall", True),
        ("Latency p50 (s)", "latency_p50_s", False),
        ("Latency p95 (s)", "latency_p95_s", False),
        ("Mean attempts", "mean_attempts", False),
        ("Fallback rate (HYBRID only)", "fallback_rate", True),
    ]

    print()
    print(f"{'metric':45s}" + "".join(f"{m:>12s}" for m in MODES))
    print("-" * (45 + 12 * len(MODES)))
    for label, key, pct in rows:
        print(f"{label:45s}" + "".join(f"{fmt(summary[m][key], pct):>12s}" for m in MODES))


def test_template_reproducibility(n_trials: int = 2) -> dict:
    """TEMPLATE mode should be byte-identical across repeated calls with
    the same pack + seed — it makes no LLM call at all."""
    session = SessionLocal()
    try:
        case = session.scalars(select(Case).order_by(Case.case_ref)).first()
        pack = _latest_pack_for(session, case)
    finally:
        session.close()

    engine = NarrativeEngine()
    outputs = [engine.generate(pack, mode="TEMPLATE", seed=SEED).narrative_text for _ in range(n_trials)]
    identical = len(set(outputs)) == 1
    return {"mode": "TEMPLATE", "trials": n_trials, "byte_identical": identical, "case_ref": case.case_ref}


def test_hybrid_reproducibility(n_trials: int = 2) -> dict:
    """HYBRID reproducibility depends on Ollama's own determinism at
    temperature=0.1 with a fixed seed — tested empirically, not assumed."""
    session = SessionLocal()
    try:
        case = session.scalars(select(Case).order_by(Case.case_ref)).first()
        pack = _latest_pack_for(session, case)
    finally:
        session.close()

    engine = NarrativeEngine()
    outputs = [engine.generate(pack, mode="HYBRID", seed=SEED).narrative_text for _ in range(n_trials)]
    identical = len(set(outputs)) == 1
    return {
        "mode": "HYBRID",
        "trials": n_trials,
        "byte_identical": identical,
        "case_ref": case.case_ref,
        "outputs": outputs if not identical else None,
    }


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N

    result = run_comparison(n)
    print_summary_table(result["summary"])

    print()
    print("Reproducibility:")
    template_repro = test_template_reproducibility()
    print(f"  TEMPLATE: byte-identical across {template_repro['trials']} trials = {template_repro['byte_identical']}")
    hybrid_repro = test_hybrid_reproducibility()
    print(f"  HYBRID:   byte-identical across {hybrid_repro['trials']} trials = {hybrid_repro['byte_identical']}")

    out = {**result, "reproducibility": {"template": template_repro, "hybrid": hybrid_repro}}
    out_path = Path(__file__).parent / "results" / "compare_modes.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
