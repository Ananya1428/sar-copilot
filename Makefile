.PHONY: up down fresh logs seed detect eval test

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

# TODO(part 3+): evidence pack builder, narrative engine, frontend.
