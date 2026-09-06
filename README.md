# SAR Copilot

Evidence-grounded narrative generation for AML Suspicious Activity Reports.

> Transaction monitoring tells you *that* something is suspicious.
> SAR Copilot tells you *how to write it down* — with every sentence
> traceable to a verified data field, and a hard refusal to emit
> anything it cannot ground.

Full specification: [`SAR-Copilot-Blueprint.md`](./SAR-Copilot-Blueprint.md).

## Status

This repository is being built in parts. See each part's scope before
assuming a component exists.

- **Part 1 (current):** Repository skeleton, Docker Compose (Postgres +
  Redis + FastAPI skeleton), full database schema via Alembic, and a
  synthetic transaction data generator with injected AML typologies and
  a ground-truth record for later precision/recall evaluation.
- **Part 2+:** Detection layer (rules + ML ensemble + graph analysis),
  evidence pack builder, narrative engine, verification pipeline,
  audit ledger, frontend. Not built yet.

## Scope and limitations

This is a demonstrator built on **synthetic data only**. It does not file
to FinCEN or any regulator, has not been validated for production use,
and must never be used with real customer data. See §6 and §26 of the
blueprint for the full scope boundary and ethics discussion.

## Quick start (Part 1)

```bash
cp .env.example .env
make fresh
make up
make seed
```

Then:

```bash
curl localhost:8000/health
```

See [`api/README.md`](./api/README.md) (added in a later part) for API
development details.

## Licence

MIT — see [`LICENSE`](./LICENSE).
