"""Evaluation harness (Part 2 scope; blueprint §23's full methodology
arrives once the narrative engine exists to evaluate too).

Runs the detection layer fresh against whatever dataset is currently in
the database, then scores the resulting Alerts against
data/seed/ground_truth.json's injected typologies: per-typology
precision/recall, an overall recall figure, and the false-positive rate
on accounts the generator never touched.

Must be run inside the api container, from its /srv working directory,
so `app.*` and the `data/`, `eval/` bind mounts all resolve the way they
do for the CLI:

    docker compose exec api python eval/run_eval.py
    # or: make eval
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.getcwd())

from app.database import SessionLocal  # noqa: E402
from app.domain.detection.orchestrator import run_detection  # noqa: E402
from app.models import Account, Alert  # noqa: E402

DEFAULT_GROUND_TRUTH_PATH = Path("data/seed/ground_truth.json")
RECALL_BAR = 0.80


def _account_refs(entry: dict) -> list[str]:
    return entry.get("account_refs") or [entry["account_ref"]]


def main() -> int:
    ground_truth_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_GROUND_TRUTH_PATH
    if not ground_truth_path.exists():
        print(f"No ground truth manifest at {ground_truth_path}.")
        print("Run `python -m app.cli generate-data` or `python -m app.cli seed` first, "
              "or pass an explicit manifest path as the first argument.")
        return 1
    print(f"Ground truth manifest: {ground_truth_path}")
    print("NOTE: this compares against whatever accounts are CURRENTLY in the")
    print("database — if it contains data from more than one generation run,")
    print("scores (especially the false-positive rate) will be contaminated")
    print("by accounts this manifest doesn't know about. For a trustworthy")
    print("number, run against a database seeded from exactly one manifest.")
    print()

    manifest = json.loads(ground_truth_path.read_text())
    injections = manifest["injections"]

    session = SessionLocal()
    try:
        # Fresh comparison: this run's alerts only, not accumulated across
        # every past `run-detection` invocation.
        session.query(Alert).delete()
        summary = run_detection(session)
        session.commit()

        alerts = (
            session.query(Alert, Account.account_ref)
            .join(Account, Alert.account_id == Account.id)
            .all()
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    fired_by_account: dict[str, set[str]] = defaultdict(set)
    band_by_account: dict[str, str] = {}
    for alert, account_ref in alerts:
        fired_by_account[account_ref].add(alert.rule_code)
        # One detection run -> one composite band per account, so every
        # alert row for that account carries the same severity; just keep
        # whichever we see (delete() above guarantees a single run's worth).
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

    # False-positive rate is defined (per the Part 2 brief) as the rate of
    # HIGH/MEDIUM bands on clean accounts — NOT "received any alert at
    # all". The orchestrator deliberately persists an Alert for every
    # fired rule regardless of band (see orchestrator.py's docstring: never
    # silently drop a real rule firing), so a clean account can rack up a
    # low-weight rule (e.g. CROSS_BORDER_RISK) and still correctly land in
    # the LOW band, meaning "no action" per blueprint §12's flowchart. Only
    # counting a HIGH/MEDIUM band as a false positive matches that.
    injected_refs = {ref for entry in injections for ref in _account_refs(entry)}
    clean_flagged = sum(
        1 for ref, band in band_by_account.items() if ref not in injected_refs and band in ("HIGH", "MEDIUM")
    )
    clean_total = manifest.get("accounts_clean", 0)
    fp_rate = clean_flagged / clean_total if clean_total else 0.0

    print(f"{'TYPOLOGY':<22}{'HITS':>6}{'TOTAL':>7}{'RECALL':>9}")
    print("-" * 44)
    total_hit, total_all = 0, 0
    for typ in sorted(per_typology):
        d = per_typology[typ]
        recall = d["hit"] / d["total"] if d["total"] else 0.0
        print(f"{typ:<22}{d['hit']:>6}{d['total']:>7}{recall:>9.1%}")
        total_hit += d["hit"]
        total_all += d["total"]

    overall_recall = total_hit / total_all if total_all else 0.0
    print("-" * 44)
    print(f"{'OVERALL':<22}{total_hit:>6}{total_all:>7}{overall_recall:>9.1%}")
    print()
    print(f"Accounts evaluated:          {summary['accounts_evaluated']}")
    print(f"Alerts created:              {summary['alerts_created']}")
    print(f"Band counts:                 {summary['band_counts']}")
    print(f"Clean accounts (no inject):  {clean_total}")
    print(f"Clean accounts flagged:      {clean_flagged}  (false-positive rate: {fp_rate:.1%})")

    if overall_recall < RECALL_BAR:
        print()
        print(f"WARNING: overall recall {overall_recall:.1%} is below the {RECALL_BAR:.0%} bar. Misses by typology:")
        for typ, d in per_typology.items():
            if d["misses"]:
                print(f"  {typ}: {len(d['misses'])} missed instance(s) of {d['total']} — {d['misses']}")
    else:
        print()
        print(f"Overall recall {overall_recall:.1%} meets the {RECALL_BAR:.0%} bar.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
