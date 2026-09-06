"""Administrative CLI (blueprint §11.1 / §21 Makefile targets).

Usage (inside the api container):
    python -m app.cli init-db
    python -m app.cli generate-data --accounts 500 --days 180
    python -m app.cli seed --if-empty
    python -m app.cli run-detection
    python -m app.cli assemble-cases
    python -m app.cli build-evidence --all
    python -m app.cli generate-narrative --case-ref CASE-0001 --mode HYBRID
"""

import json
import subprocess
import time
from pathlib import Path

import typer
from sqlalchemy import select

from app.database import SessionLocal
from app.domain.detection.orchestrator import run_detection
from app.domain.evidence.builder import build_evidence_pack, persist_evidence_pack
from app.domain.evidence.case_assembly import assemble_cases
from app.domain.evidence.schema import EvidencePack as EvidencePackSchema
from app.domain.ingestion.synthetic import generate_dataset
from app.domain.narrative.engine import NarrativeEngine, persist_narrative
from app.models import Customer
from app.models.case import Case
from app.models.evidence import EvidencePack as EvidencePackRow

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


@app.command("assemble-cases")
def assemble_cases_cmd() -> None:
    """Group fired HIGH/MEDIUM alerts (Part 2) into opened Cases (blueprint
    §8 Journey B). Safe to run repeatedly."""
    session = SessionLocal()
    try:
        summary = assemble_cases(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    typer.echo(json.dumps(summary, indent=2, default=str))


@app.command("build-evidence")
def build_evidence_cmd(
    case_ref: str = typer.Option(None, "--case-ref", help="Build for a single case, e.g. CASE-0001"),
    all_open: bool = typer.Option(False, "--all", help="Build for every OPEN case"),
) -> None:
    """Build and persist an EvidencePack (blueprint §10.2) for one or every
    open case. Each call creates a NEW pack row — packs are immutable."""
    if not case_ref and not all_open:
        typer.echo("Specify --case-ref CASE-0001 or --all", err=True)
        raise typer.Exit(code=1)

    session = SessionLocal()
    try:
        if all_open:
            cases = list(session.scalars(select(Case).where(Case.status == "OPEN")))
        else:
            case = session.scalars(select(Case).where(Case.case_ref == case_ref)).first()
            if case is None:
                typer.echo(f"No case with case_ref={case_ref}", err=True)
                raise typer.Exit(code=1)
            cases = [case]

        built = []
        for case in cases:
            pack = build_evidence_pack(session, case)
            persist_evidence_pack(session, case, pack)
            built.append({"case_ref": case.case_ref, "pack_id": str(pack.pack_id), "content_hash": pack.content_hash})
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    typer.echo(json.dumps({"packs_built": len(built), "details": built}, indent=2, default=str))


@app.command("generate-narrative")
def generate_narrative_cmd(
    case_ref: str = typer.Option(..., "--case-ref", help="e.g. CASE-0001"),
    mode: str = typer.Option("HYBRID", "--mode", help="TEMPLATE | HYBRID | FREEFORM"),
    seed: int = typer.Option(42, "--seed"),
) -> None:
    """Generate a narrative (blueprint §13) for one case, reusing its
    latest EvidencePack if one already exists. Prints the generated text,
    mode actually used (HYBRID can fall back to TEMPLATE_FALLBACK), and
    wall-clock latency."""
    session = SessionLocal()
    try:
        case = session.scalars(select(Case).where(Case.case_ref == case_ref)).first()
        if case is None:
            typer.echo(f"No case with case_ref={case_ref}", err=True)
            raise typer.Exit(code=1)

        pack_row = session.scalars(
            select(EvidencePackRow).where(EvidencePackRow.case_id == case.id).order_by(EvidencePackRow.built_at.desc())
        ).first()
        if pack_row is None:
            pack = build_evidence_pack(session, case)
            pack_row = persist_evidence_pack(session, case, pack)
        else:
            pack = EvidencePackSchema.model_validate(pack_row.payload)

        engine = NarrativeEngine()
        start = time.monotonic()
        result = engine.generate(pack, mode=mode, seed=seed)
        elapsed = time.monotonic() - start

        narrative_row = persist_narrative(session, case, pack_row, result)
        session.commit()
        # Captured before the session closes below — the ORM row is
        # detached after that and its attributes can no longer be
        # lazy-loaded (SQLAlchemy expires attributes on commit by default).
        narrative_id, narrative_version = narrative_row.id, narrative_row.version
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    typer.echo(f"case_ref:         {case_ref}")
    typer.echo(f"narrative_id:     {narrative_id}")
    typer.echo(f"version:          {narrative_version}")
    typer.echo(f"requested_mode:   {mode.upper()}")
    typer.echo(f"actual_mode:      {result.mode}")
    typer.echo(f"model_id:         {result.model_id}")
    typer.echo(f"prompt_version:   {result.prompt_version}")
    typer.echo(f"seed:             {result.seed}")
    typer.echo(f"attempts:         {result.attempts}")
    typer.echo(f"latency_seconds:  {elapsed:.2f}")
    if result.notes:
        typer.echo(f"notes:            {result.notes}")
    typer.echo("")
    typer.echo("--- NARRATIVE ---")
    typer.echo(result.narrative_text)


if __name__ == "__main__":
    app()
