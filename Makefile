.PHONY: help install api-dev llm-dev db-up db-down db-migrate db-revision lint test

help:
	@echo "Available targets:"
	@echo "  install      Install all services in dev mode"
	@echo "  api-dev      Start API with hot reload"
	@echo "  llm-dev      Start LLM worker"
	@echo "  db-up        Start Postgres + Redis via Docker"
	@echo "  db-down      Stop Docker services"
	@echo "  db-migrate   Apply Alembic migrations"
	@echo "  db-revision  Create new Alembic migration"
	@echo "  lint         Run ruff on all services"
	@echo "  test         Run pytest on all services"

install:
	pip install -e packages/shared
	pip install -e services/api[dev]
	pip install -e services/llm[dev]

api-dev:
	cd services/api && .venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000

llm-dev:
	cd services/llm && python main.py

db-up:
	cd infra/compose && docker compose up -d

db-down:
	cd infra/compose && docker compose down

db-migrate:
	cd services/api && alembic upgrade head

db-revision:
	@read -p "Migration message: " msg; \
	cd services/api && alembic revision --autogenerate -m "$$msg"

lint:
	ruff check packages/shared services/api services/llm

test:
	pytest services/api services/llm
