.PHONY: help install api-dev worker-dev llm-dev db-up db-down db-migrate db-reset db-revision lint test

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
	@echo "  lint         Run ruff on all services"
	@echo "  test         Run pytest on all services"

install:
	pip install --upgrade pip setuptools wheel
	pip install -e services/api[dev]
	pip install -e services/llm[dev]

api-dev:
	./.venv/bin/uvicorn --app-dir services/api main:app --reload --host 0.0.0.0 --port 8000

worker-dev:
	cd services/api && ../../.venv/bin/arq app.services.background_jobs.WorkerSettings

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
	ruff check services/api services/llm

test:
	pytest services/api services/llm
