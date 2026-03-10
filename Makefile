.PHONY: help install api-dev worker-dev worker-dev-verbose llm-dev db-up db-down db-migrate db-reset db-revision lint test test-logs backfill-extraction backfill-extraction-dry score-actions capture-riot-fixtures

help:
	@echo "Available targets:"
	@echo "  install      Install all services in dev mode"
	@echo "  api-dev      Start API with hot reload"
	@echo "  worker-dev   Start ARQ background worker"
	@echo "  llm-dev      Start LLM worker"
	@echo "  db-up        Start Postgres + Redis via Docker"
	@echo "  db-down      Stop Docker services"
	@echo "  db-migrate   Apply Alembic migrations"
	@echo "  db-reset     Clear all data and run migrations"
	@echo "  db-revision  Create new Alembic migration"
	@echo "  lint         Run backend + frontend lint gates"
	@echo "  test         Run pytest on all services"
	@echo "  score-actions  Enqueue score_actions_job for a single match (MATCH_ID=...)"
	@echo "  capture-riot-fixtures  Capture live Riot JSON fixtures for tests"

install:
	python3 -m venv .venv || true
	./.venv/bin/python -m pip install --upgrade pip setuptools wheel
	./.venv/bin/python -m pip install -e services/api[dev]
	./.venv/bin/python -m pip install -e services/llm[dev]

api-dev:
	./.venv/bin/uvicorn --app-dir services/api main:app --reload --host 0.0.0.0 --port 8000

worker-dev:
	cd services/api && ../../.venv/bin/arq app.services.background_jobs.WorkerSettings

worker-dev-verbose:
	cd services/api && LOG_LEVEL=DEBUG ../../.venv/bin/arq app.services.background_jobs.WorkerSettings

llm-dev:
	cd services/llm && python main.py

db-up:
	cd infra/compose && docker compose up -d

db-down:
	cd infra/compose && docker compose down

db-migrate:
	cd services/api && ../../.venv/bin/alembic upgrade head

db-reset:
	cd infra/compose && docker compose down -v
	cd infra/compose && docker compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	cd services/api && ../../.venv/bin/alembic upgrade head

db-revision:
	@read -p "Migration message: " msg; \
	cd services/api && ../../.venv/bin/alembic revision --autogenerate -m "$$msg"

lint:
	./.venv/bin/ruff check services/api services/llm

test:
	./.venv/bin/pytest services/api services/llm

test-logs:
	./.venv/bin/pytest services/api services/llm -v -s

backfill-extraction:
	./.venv/bin/python scripts/backfill_extraction.py

backfill-extraction-dry:
	./.venv/bin/python scripts/backfill_extraction.py --dry-run

score-actions:
	@if [ -z "$$MATCH_ID" ]; then \
		echo "Usage: make score-actions MATCH_ID=NA1_1234567890"; \
		exit 1; \
	fi
	./.venv/bin/python scripts/score_actions_for_match.py --match-id "$$MATCH_ID"

training-data-export:
	./.venv/bin/python scripts/export_training_data.py --output data/training.csv --sample-interval 1

win-prob-model-training:
	./.venv/bin/python scripts/train_win_prob_model.py --input data/training.csv --output data/win_prob_model.joblib

capture-riot-fixtures:
	./.venv/bin/python scripts/capture_riot_test_fixtures.py --game-name damanjr --tag-line NA1 --count 40
