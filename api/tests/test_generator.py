import json

from app.domain.ingestion.synthetic import generate_dataset
from app.domain.ingestion.typologies import TYPOLOGIES
from app.models import Transaction


def test_generator_produces_expected_shape(db_session, tmp_path):
    # These tests run against the live dev Postgres (see conftest.py) and
    # roll back afterward, but the table can already hold rows committed by
    # earlier manual `generate-data` / `seed` runs — so assertions must be
    # scoped to what THIS call created, never to raw table-wide counts.
    gt_path = tmp_path / "ground_truth.json"
    summary = generate_dataset(db_session, n_accounts=40, days=60, seed=123, ground_truth_path=gt_path)

    assert summary["accounts"] == 40
    assert summary["transactions"] > 0

    # Most accounts should carry no injected typology.
    assert summary["accounts_clean"] > summary["accounts_touched_by_typology"]

    # At n=40 (well above the minimum needed for one of each type, per
    # plan_injections in typologies.py) every typology should appear at
    # least once.
    assert set(summary["typology_counts"].keys()) == set(TYPOLOGIES)
    for count in summary["typology_counts"].values():
        assert count >= 1

    manifest = json.loads(gt_path.read_text())
    injected_refs = [ref for entry in manifest["injections"] for ref in entry["transaction_refs"]]
    found = db_session.query(Transaction).filter(Transaction.txn_ref.in_(injected_refs)).count()
    assert found == len(injected_refs)


def test_generator_is_deterministic(session_factory):
    # Sequential, not concurrent — see session_factory's docstring in
    # conftest.py. Both runs use the same seed and so deliberately produce
    # identical new refs; holding both transactions open at once would
    # deadlock on the resulting uncommitted duplicate-key inserts.
    with session_factory() as session_a:
        summary_a = generate_dataset(session_a, n_accounts=20, days=30, seed=7, ground_truth_path=None)

    with session_factory() as session_b:
        summary_b = generate_dataset(session_b, n_accounts=20, days=30, seed=7, ground_truth_path=None)

    assert summary_a["typology_counts"] == summary_b["typology_counts"]
    assert summary_a["accounts_touched_by_typology"] == summary_b["accounts_touched_by_typology"]


def test_generator_writes_ground_truth_manifest(db_session, tmp_path):
    gt_path = tmp_path / "ground_truth.json"
    generate_dataset(db_session, n_accounts=20, days=30, seed=7, ground_truth_path=gt_path)

    assert gt_path.exists()
    manifest = json.loads(gt_path.read_text())
    assert manifest["config"] == {"accounts": 20, "days": 30, "seed": 7}
    assert len(manifest["injections"]) > 0
    for entry in manifest["injections"]:
        assert entry["typology"] in TYPOLOGIES
        assert "transaction_refs" in entry
