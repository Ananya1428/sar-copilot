"""Detection evaluation at Part 2's original scale (500 accounts, blueprint
§23.4 / Part 7) — one clean final run: typology precision/recall,
case-level metrics, and false-positive rate on clean accounts, against a
FRESH synthetic dataset and its own ground-truth manifest.

Runs inside an isolated, rolled-back DB transaction (same pattern as
api/tests/conftest.py's isolated_session) so this doesn't add 500 accounts
worth of synthetic noise to the live demo database that README.md
documents specific case refs against — the whole point of this script is
a clean, reproducible number, not a change to persistent app state.

    docker compose exec api python eval/detection_at_scale.py
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.getcwd())

from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import engine  # noqa: E402
from app.domain.detection.orchestrator import run_detection  # noqa: E402
from app.domain.evidence.case_assembly import assemble_cases  # noqa: E402
from app.domain.ingestion.synthetic import generate_dataset  # noqa: E402
from app.models import Account, Alert, Case  # noqa: E402

N_ACCOUNTS = 500
DAYS = 180
SEED = 42
GROUND_TRUTH_PATH = Path(__file__).parent / "results" / "detection_at_scale_ground_truth.json"


def _account_refs(entry: dict) -> list[str]:
    return entry.get("account_refs") or [entry["account_ref"]]


def main() -> int:
    connection = engine.connect()
    trans = connection.begin()
    Session = sessionmaker(bind=connection, future=True)
    session = Session()

    try:
        print(f"Generating a fresh {N_ACCOUNTS}-account synthetic dataset (seed={SEED}, {DAYS} days)...")
        # generate_dataset() RETURNS a print-friendly summary dict (no
        # "injections" key) but WRITES the full manifest — including
        # "injections" — to ground_truth_path. Read that back rather than
        # trying to pull injections out of the return value.
        summary_from_generation = generate_dataset(session, n_accounts=N_ACCOUNTS, days=DAYS, seed=SEED, ground_truth_path=GROUND_TRUTH_PATH)
        session.flush()
        manifest = json.loads(GROUND_TRUTH_PATH.read_text())
        injections = manifest["injections"]
        print(json.dumps(summary_from_generation, indent=2, default=str))

        print("\nRunning detection...")
        summary = run_detection(session)
        session.flush()

        print("\nAssembling cases (so case-level metrics are real, not just alert-level)...")
        case_summary = assemble_cases(session)
        session.flush()

        alerts = session.query(Alert, Account.account_ref).join(Account, Alert.account_id == Account.id).all()

        fired_by_account: dict[str, set[str]] = defaultdict(set)
        band_by_account: dict[str, str] = {}
        for alert, account_ref in alerts:
            fired_by_account[account_ref].add(alert.rule_code)
            band_by_account[account_ref] = alert.severity

        per_typology: dict[str, dict] = defaultdict(lambda: {"hit": 0, "total": 0, "misses": []})
        for entry in injections:
            typ = entry["typology"]
            refs = _account_refs(entry)
            per_typology[typ]["total"] += 1
            if any(typ in fired_by_account[ref] for ref in refs):
                per_typology[typ]["hit"] += 1
            else:
                per_typology[typ]["misses"].append(refs)

        injected_refs = {ref for entry in injections for ref in _account_refs(entry)}
        clean_flagged = sum(1 for ref, band in band_by_account.items() if ref not in injected_refs and band in ("HIGH", "MEDIUM"))
        clean_total = manifest.get("accounts_clean", 0)
        fp_rate = clean_flagged / clean_total if clean_total else 0.0

        # Case-level: does the case opened for an injected account's
        # typology actually carry an alert for that typology? (assemble_cases
        # only opens cases for HIGH/MEDIUM alerts — a typology that fires
        # only as a LOW-severity alert never gets a case at all, which is
        # itself a real, reportable gap, not a bug in this script.)
        cases = session.query(Case).all()
        case_count = len(cases)
        cases_covering_injection = 0
        for entry in injections:
            typ = entry["typology"]
            refs = _account_refs(entry)
            for ref in refs:
                acct = session.query(Account).filter(Account.account_ref == ref).first()
                if acct is None:
                    continue
                has_case = (
                    session.query(Alert)
                    .filter(Alert.account_id == acct.id, Alert.rule_code == typ, Alert.case_id.isnot(None))
                    .first()
                    is not None
                )
                if has_case:
                    cases_covering_injection += 1
                    break

        print(f"\n{'TYPOLOGY':<22}{'HITS':>6}{'TOTAL':>7}{'RECALL':>9}")
        print("-" * 44)
        total_hit, total_all = 0, 0
        typology_table = {}
        for typ in sorted(per_typology):
            d = per_typology[typ]
            recall = d["hit"] / d["total"] if d["total"] else 0.0
            typology_table[typ] = {"hits": d["hit"], "total": d["total"], "recall": recall}
            print(f"{typ:<22}{d['hit']:>6}{d['total']:>7}{recall:>9.1%}")
            total_hit += d["hit"]
            total_all += d["total"]

        overall_recall = total_hit / total_all if total_all else 0.0
        print("-" * 44)
        print(f"{'OVERALL':<22}{total_hit:>6}{total_all:>7}{overall_recall:>9.1%}")

        print(f"\nAccounts evaluated:              {summary['accounts_evaluated']}")
        print(f"Alerts created:                  {summary['alerts_created']}")
        print(f"Band counts:                     {summary['band_counts']}")
        print(f"Clean accounts (no injection):   {clean_total}")
        print(f"Clean accounts flagged HIGH/MED:  {clean_flagged}  (false-positive rate: {fp_rate:.1%})")
        print(f"Cases opened:                     {case_count}  (created={case_summary['cases_created']}, reused={case_summary['cases_reused']})")
        print(f"Injected-typology instances with a case: {cases_covering_injection} / {len(injections)}")

        out = {
            "n_accounts": N_ACCOUNTS,
            "days": DAYS,
            "seed": SEED,
            "manifest_summary": {k: v for k, v in manifest.items() if k != "injections"},
            "typology_recall": typology_table,
            "overall_recall": overall_recall,
            "detection_summary": summary,
            "clean_accounts": clean_total,
            "clean_accounts_flagged": clean_flagged,
            "false_positive_rate": fp_rate,
            "cases_opened": case_count,
            "injected_typology_instances_with_case": cases_covering_injection,
            "injected_typology_instances_total": len(injections),
        }
        out_path = Path(__file__).parent / "results" / "detection_at_scale.json"
        out_path.write_text(json.dumps(out, indent=2, default=str))
        print(f"\nWrote {out_path}")
        print("Wrote", GROUND_TRUTH_PATH)

    finally:
        # Never commits — this is a throwaway 500-account dataset for the
        # eval record only, not a change to the live demo database.
        session.close()
        trans.rollback()
        connection.close()
        print("\n(transaction rolled back — no changes persisted to the live database)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
