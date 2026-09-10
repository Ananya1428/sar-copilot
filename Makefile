.PHONY: up down fresh logs seed detect eval test assemble evidence narrative eval-modes eval-detection eval-adversarial-real

N ?= 5

up:      ## Start everything: postgres, redis, ollama, api, web, nginx (Part 6c)
	docker compose up -d --build
	@echo "App:    http://localhost:8080"
	@echo "API:    http://localhost:8000  (direct — nginx at :8080 proxies /api/* to this)"
	@echo "Health: http://localhost:8080/health"

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

adversarial: ## Run the ten-case adversarial suite with the deterministic stub (fast; matches designed per-check behavior)
	docker compose exec api python eval/adversarial_cases.py --stub

eval-adversarial-real: ## Same suite against the REAL local NLI model (slower; see LIMITATIONS.md for what this actually finds)
	docker compose exec api python eval/adversarial_cases.py

eval-modes: ## Compare TEMPLATE/HYBRID/FREEFORM over N real seeded cases (default 5; HYBRID/FREEFORM call Ollama for real)
	docker compose exec api python eval/compare_modes.py $(N)

eval-detection: ## Fresh 500-account detection evaluation, isolated + rolled back (never touches the live demo DB)
	docker compose exec api python eval/detection_at_scale.py
