"""Administrative CLI (blueprint §11.1 / §21 Makefile targets).

Usage (inside the api container):
    python -m app.cli init-db
    python -m app.cli generate-data --accounts 500 --days 180
    python -m app.cli seed --if-empty
    python -m app.cli run-detection
"""

import json
import subprocess
from pathlib import Path

import typer

from app.database import SessionLocal
from app.domain.detection.orchestrator import run_detection
from app.domain.ingestion.synthetic import generate_dataset
from app.models import Customer

app = typer.Typer(help="SAR Copilot administrative CLI")

DEFAULT_GROUND_TRUTH_PATH = Path("data/seed/ground_truth.json")


@app.command("init-db")
def init_db() -> None:
    """Run Alembic migrations to head."""
    subprocess.run(["alembic", "upgrade", "head"], check=True)


@app.command("generate-data")
def generate_data(
    accounts: int = typer.Option(500, help="Number of customers/accounts to create"),
    days: int = typer.Option(180, help="Length of the transaction history window"),
    seed: int = typer.Option(42, help="RNG seed — same seed + params reproduce the same dataset"),
    ground_truth_path: Path = typer.Option(DEFAULT_GROUND_TRUTH_PATH, help="Where to write the injected-typology ground truth manifest"),
) -> None:
    """Generate synthetic customers/accounts/transactions with deliberately
    injected AML typologies (blueprint §6) and write a ground-truth manifest."""
    session = SessionLocal()
    try:
        summary = generate_dataset(session, n_accounts=accounts, days=days, seed=seed, ground_truth_path=ground_truth_path)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    typer.echo(json.dumps(summary, indent=2, default=str))


@app.command("seed")
def seed(
    if_empty: bool = typer.Option(True, "--if-empty/--force", help="Skip if the database already has data"),
) -> None:
    """Load a small demo dataset instantly. If a ground-truth manifest is
    already committed at data/seed/ground_truth.json, its (accounts, days,
    seed) config is reproduced exactly — the generator is deterministic, so
    this recreates the same dataset without needing a raw data dump
    committed to the repo. Otherwise falls back to a small fresh generation."""
    session = SessionLocal()
    try:
        existing = session.query(Customer).count()
        if existing and if_empty:
            typer.echo(f"Database already has {existing} customers; skipping seed (--if-empty).")
            return

        if DEFAULT_GROUND_TRUTH_PATH.exists():
            cfg = json.loads(DEFAULT_GROUND_TRUTH_PATH.read_text())["config"]
            accounts, days, seed_val = cfg["accounts"], cfg["days"], cfg["seed"]
            typer.echo(f"Reproducing committed demo dataset (accounts={accounts}, days={days}, seed={seed_val})")
        else:
            accounts, days, seed_val = 50, 90, 42
            typer.echo("No committed seed manifest found; generating a small demo dataset")

        summary = generate_dataset(session, n_accounts=accounts, days=days, seed=seed_val, ground_truth_path=DEFAULT_GROUND_TRUTH_PATH)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    typer.echo(json.dumps(summary, indent=2, default=str))


@app.command("run-detection")
def run_detection_cmd() -> None:
    """Run the detection layer (blueprint §12) against whatever's currently
    in the database: feature engineering -> rule engine + ML ensemble +
    graph analysis -> composite scoring -> persisted Alert rows."""
    session = SessionLocal()
    try:
        summary = run_detection(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    typer.echo(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    app()
