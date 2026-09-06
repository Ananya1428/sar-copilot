.PHONY: up down fresh logs seed detect eval test assemble evidence narrative

up:      ## Start everything (Part 1: postgres, redis, api)
	docker compose up -d --build
	@echo "API:    http://localhost:8000"
	@echo "Health: http://localhost:8000/health"

down:
	docker compose down

fresh:   ## Nuke volumes and rebuild
	docker compose down -v
	docker compose up -d --build

logs:
	docker compose logs -f api

seed:    ## Generate synthetic dataset with injected typologies (per §21/§20)
	docker compose exec api python -m app.cli generate-data --accounts 500 --days 180

detect:  ## Run the detection pipeline (rules + ML ensemble + graph -> Alerts)
	docker compose exec api python -m app.cli run-detection

eval:    ## Score detection against data/seed/ground_truth.json (per-typology precision/recall)
	docker compose exec api python eval/run_eval.py

test:
	docker compose exec api pytest -v

assemble: ## Group fired HIGH/MEDIUM alerts into opened Cases
	docker compose exec api python -m app.cli assemble-cases

evidence: ## Build an EvidencePack for every open case
	docker compose exec api python -m app.cli build-evidence --all

narrative: ## Generate a HYBRID-mode narrative for a case: make narrative CASE=CASE-0001
	docker compose exec api python -m app.cli generate-narrative --case-ref $(CASE) --mode HYBRID

# TODO(part 5+): verification pipeline, audit ledger, frontend.
